#!/usr/bin/env python3
"""Exercise the actual Android ARM64 programs under QEMU user emulation."""
import http.server
import pathlib
import shutil
import ssl
import subprocess
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "dist/android-arm64/bin"
QEMU = shutil.which("qemu-aarch64") or shutil.which("qemu-aarch64-static")
if not QEMU:
    raise SystemExit("Install qemu-user or qemu-user-static to run ARM64 smoke tests")


def run(name, *args, input=None, check=True):
    result = subprocess.run([QEMU, str(BIN / name), *args], input=input,
                            text=True, capture_output=True, timeout=30)
    if check and result.returncode:
        raise RuntimeError(f"{name} failed ({result.returncode}): {result.stderr}")
    return result


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"android_arm64":true}\n'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if (BIN / "curl").exists():
    version = run("curl", "--version").stdout
    print(version, flush=True)
    assert "OpenSSL/" in version and "HTTP2" in version and "https" in version
    with tempfile.TemporaryDirectory(prefix="android-arm64-tls-") as temporary:
        certificate = pathlib.Path(temporary) / "test-ca.pem"
        key = pathlib.Path(temporary) / "test-key.pem"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(certificate), "-days", "1",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_port
        options = ["--fail", "--silent", "--show-error", "--max-time", "15",
                   "--noproxy", "*", "--resolve", f"localhost:{port}:127.0.0.1"]
        try:
            # The built-in public roots must reject this private certificate.
            rejected = run("curl", *options, f"https://localhost:{port}/", check=False)
            assert rejected.returncode == 60, rejected.stderr
            # Explicitly trusting the local CA must permit a verified TLS request.
            response = run("curl", *options, "--cacert", str(certificate),
                           f"https://localhost:{port}/")
            assert response.stdout == '{"android_arm64":true}\n'
            print("PASS: verified HTTPS succeeds; untrusted certificate is rejected", flush=True)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

if (BIN / "jq").exists():
    print(run("jq", "--version").stdout, end="", flush=True)
    assert run("jq", "-r", ".items | map(. * 2) | add",
               input='{"items":[1,2,3]}').stdout.strip() == "12"
    assert run("jq", "-r", '.name | test("^Android [0-9]+$")',
               input='{"name":"Android 10"}').stdout.strip() == "true"
    print("PASS: jq JSON processing and regular expressions", flush=True)
