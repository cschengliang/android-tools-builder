#!/usr/bin/env python3
"""Exercise the actual Android programs under architecture-specific QEMU."""
import json
import os
import http.server
import pathlib
import shutil
import ssl
import subprocess
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARCH = os.environ.get("ARCH", "arm64")
CATALOG = json.loads((ROOT / "build-list.json").read_text())
BIN = ROOT / f"dist/android-{ARCH}/bin"
target = CATALOG["architectures"][ARCH]["qemu"]
QEMU = shutil.which(f"qemu-{target}") or shutil.which(f"qemu-{target}-static")
if not QEMU:
    raise SystemExit(f"Install qemu-user to test {ARCH}")


def run(name, *args, input=None, check=True):
    cpu = "cortex-a15" if ARCH == "armv7" else "max"
    result = subprocess.run([QEMU, "-cpu", cpu, str(BIN / name), *args], input=input,
                            text=True, capture_output=True, timeout=30)
    if check and result.returncode:
        raise RuntimeError(f"{name} failed ({result.returncode}): {result.stderr}")
    return result


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"android_tools":true}\n'
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
            assert response.stdout == '{"android_tools":true}\n'
            print("PASS: verified HTTPS succeeds; untrusted certificate is rejected", flush=True)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

if (BIN / "rg").exists():
    print(run("rg", "--version").stdout, end="", flush=True)
    result = run("rg", "--ignore-case", "^android$", input="Android\nandroid\nLinux\n")
    assert result.stdout == "Android\nandroid\n"
    assert run("rg", "系统", input="Android 系统\nLinux\n").stdout == "Android 系统\n"
    print("PASS: ripgrep regular expressions and Unicode", flush=True)

if (BIN / "stress").exists():
    print(run("stress", "--version").stdout, end="", flush=True)
    result = run("stress", "--cpu", "1", "--vm", "1", "--vm-bytes", "1M", "--timeout", "1", "--backoff", "0")
    print(result.stdout, end="", flush=True)
    assert "successful run completed" in result.stdout
    print("PASS: stress bounded CPU and memory workload", flush=True)

print(f"PASS: all selected tools tested on {ARCH}", flush=True)
