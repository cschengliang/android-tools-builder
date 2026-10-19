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
import struct
import socket
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARCH = os.environ.get("ARCH", "arm64")
CATALOG = json.loads((ROOT / "build-list.json").read_text())
BIN = ROOT / f"dist/android-{ARCH}/bin"
target = CATALOG["architectures"][ARCH]["qemu"]
QEMU = shutil.which(f"qemu-{target}") or shutil.which(f"qemu-{target}-static")
if not QEMU:
    raise SystemExit(f"Install qemu-user to test {ARCH}")


def command(name, *args):
    cpu = "cortex-a15" if ARCH == "armv7" else "max"
    return [QEMU, "-cpu", cpu, str(BIN / name), *args]


def run(name, *args, input=None, check=True, binary=False):
    result = subprocess.run(command(name, *args), input=input,
                            text=not binary, capture_output=True, timeout=30)
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


if (BIN / "curl").exists() or (BIN / "aria2c").exists():
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
            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
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
            if (BIN / "curl").exists():
                rejected = run("curl", *options, f"https://localhost:{port}/", check=False)
                assert rejected.returncode == 60, rejected.stderr
                response = run("curl", *options, "--cacert", str(certificate),
                               f"https://localhost:{port}/")
                assert response.stdout == '{"android_tools":true}\n'
                print("PASS: curl verified HTTPS; untrusted certificate rejected", flush=True)
            if (BIN / "aria2c").exists():
                version = run("aria2c", "--version").stdout
                print(version, flush=True)
                assert "HTTPS" in version and "BitTorrent" in version
                options = ["--no-conf", "--all-proxy=", "--no-proxy=*", "--max-tries=1",
                           "--timeout=5", "--split=1", "--file-allocation=none",
                           "--dir=" + temporary, "--out=download.json", "--allow-overwrite=true",
                           "--auto-file-renaming=false"]
                url = f"https://127.0.0.1:{port}/test.json"
                rejected = run("aria2c", *options, url, check=False)
                assert rejected.returncode != 0, "aria2 accepted an untrusted certificate"
                run("aria2c", *options, "--ca-certificate=" + str(certificate), url)
                assert (pathlib.Path(temporary) / "download.json").read_text() == '{"android_tools":true}\n'
                print("PASS: aria2 verified HTTPS download; untrusted certificate rejected", flush=True)
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

if (BIN / "jq").exists():
    payload = '{"items":[{"name":"Android","enabled":true},{"name":"Linux","enabled":false}]}'
    assert run("jq", "-r", '.items[] | select(.enabled) | .name', input=payload).stdout == "Android\n"
    assert run("jq", "-r", 'test("^安卓")', input='"安卓系统"').stdout == "true\n"
    print("PASS: jq JSON filtering and Unicode regular expressions", flush=True)

if (BIN / "zstd").exists():
    payload = b"Android tools compressed round trip\n" * 1024
    compressed = run("zstd", "-q", "-c", input=payload, binary=True).stdout
    assert run("zstd", "-q", "-d", "-c", input=compressed, binary=True).stdout == payload
    print("PASS: zstd compression/decompression round trip", flush=True)

if (BIN / "sqlite3").exists():
    query = ("CREATE TABLE items(value); INSERT INTO items VALUES(21),(21); SELECT sum(value) FROM items; "
             "CREATE VIRTUAL TABLE words USING fts5(text); INSERT INTO words VALUES('android tools'); "
             "SELECT count(*) FROM words WHERE words MATCH 'android';")
    assert run("sqlite3", ":memory:", query).stdout == "42\n1\n"
    print("PASS: sqlite3 SQL and FTS5 queries", flush=True)

if (BIN / "socat").exists():
    assert "WITH_OPENSSL" in run("socat", "-V").stdout
    assert run("socat", "-u", "-", "STDOUT", input="android data relay\n").stdout == "android data relay\n"
    print("PASS: socat data relay and OpenSSL feature", flush=True)

if (BIN / "iperf3").exists():
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = str(reservation.getsockname()[1])
    server = subprocess.Popen(command("iperf3", "-s", "-1", "-B", "127.0.0.1", "-p", port),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        for attempt in range(20):
            result = run("iperf3", "-c", "127.0.0.1", "-p", port, "-t", "1", "-J", check=False)
            if result.returncode == 0:
                break
            if server.poll() is not None:
                raise RuntimeError("iperf3 server exited: " + str(server.communicate()))
            time.sleep(0.1)
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)["end"]["sum_received"]["bytes"] > 0
        server.communicate(timeout=10)
        assert server.returncode == 0
    finally:
        if server.poll() is None:
            server.kill()
            server.communicate()
    print("PASS: iperf3 actual TCP client/server transfer", flush=True)

if (BIN / "tcpdump").exists():
    with tempfile.TemporaryDirectory(prefix="android-pcap-") as temporary:
        packet = (bytes.fromhex("ffffffffffff0011223344550800")
                  + bytes.fromhex("450000200000000040110000c0000201c6336402")
                  + struct.pack("!HHHH", 12345, 54321, 12, 0) + b"test")
        fixture = pathlib.Path(temporary) / "test.pcap"
        fixture.write_bytes(struct.pack("<IHHIIII", 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1)
                            + struct.pack("<IIII", 0, 0, len(packet), len(packet)) + packet)
        result = run("tcpdump", "-n", "-r", str(fixture))
        assert "192.0.2.1.12345" in result.stdout and "UDP" in result.stdout
    print("PASS: tcpdump offline Ethernet/IPv4/UDP pcap decoding", flush=True)

if (BIN / "strace").exists():
    assert "strace" in run("strace", "-V").stdout
    print("PASS: strace starts; ptrace execution needs native-device testing", flush=True)

if (BIN / "stress-ng").exists():
    result = run("stress-ng", "--cpu", "1", "--cpu-method", "sqrt", "--cpu-ops", "10", "--timeout", "5", "--metrics-brief")
    assert "successful run" in result.stdout + result.stderr
    print("PASS: stress-ng bounded CPU workload", flush=True)

print(f"PASS: all selected tools smoke-tested on {ARCH}", flush=True)
