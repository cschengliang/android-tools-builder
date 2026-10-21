#!/usr/bin/env python3
"""Exercise Android programs natively on x86 or with QEMU on ARM."""
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
import sys
import platform
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARCH = os.environ.get("ARCH", "arm64")
CATALOG = json.loads((ROOT / "build-list.json").read_text())
BIN = ROOT / f"dist/android-{ARCH}/bin"
target = CATALOG["architectures"][ARCH]["qemu"]
QEMU = shutil.which(f"qemu-{target}") or shutil.which(f"qemu-{target}-static")
NATIVE = (ARCH in {"x86", "x86_64"} and platform.system() == "Linux"
          and platform.machine().lower() in {"x86_64", "amd64"})
if not NATIVE and not QEMU:
    raise SystemExit(f"Install qemu-user to test {ARCH}")

ONLY = os.environ.get("SMOKE_TOOL")
# iperf3 defaults to Android's /data/local/tmp, absent on a Linux CI runner.
# Its documented TMPDIR override lets the actual Android binary use CI storage.
os.environ["TMPDIR"] = tempfile.gettempdir()
if not ONLY:
    # Exercise every program even when one fails, so a matrix run reports all
    # compatibility issues instead of repeatedly stopping at its first tool.
    failed = []
    known = {tool["binary"] for tool in CATALOG["tools"].values()}
    for program in sorted(BIN.iterdir()):
        if program.name not in known:
            raise SystemExit(f"Unknown executable: {program.name}")
        result = subprocess.run([sys.executable, __file__],
                                env={**os.environ, "SMOKE_TOOL": program.name})
        if result.returncode:
            failed.append(program.name)
    if failed:
        raise SystemExit("Failed smoke tests: " + ", ".join(failed))
    print(f"PASS: all selected tools smoke-tested on {ARCH}", flush=True)
    raise SystemExit(0)


def available(name):
    return name == ONLY and (BIN / name).is_file()


def command(name, *args):
    # QEMU's TCP getsockopt translation can truncate strings and TCP_INFO.
    # A Linux x86_64 runner can execute these static Bionic ELFs directly.
    if NATIVE:
        return [str(BIN / name), *args]
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


if available("curl") or available("aria2c"):
    if available("curl"):
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
            if available("curl"):
                rejected = run("curl", *options, f"https://localhost:{port}/", check=False)
                assert rejected.returncode == 60, rejected.stderr
                response = run("curl", *options, "--cacert", str(certificate),
                               f"https://localhost:{port}/")
                assert response.stdout == '{"android_tools":true}\n'
                print("PASS: curl verified HTTPS; untrusted certificate rejected", flush=True)
            if available("aria2c"):
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

if available("rg"):
    print(run("rg", "--version").stdout, end="", flush=True)
    result = run("rg", "--ignore-case", "^android$", input="Android\nandroid\nLinux\n")
    assert result.stdout == "Android\nandroid\n"
    assert run("rg", "系统", input="Android 系统\nLinux\n").stdout == "Android 系统\n"
    print("PASS: ripgrep regular expressions and Unicode", flush=True)

if available("stress"):
    print(run("stress", "--version").stdout, end="", flush=True)
    result = run("stress", "--cpu", "1", "--vm", "1", "--vm-bytes", "1M", "--timeout", "1", "--backoff", "0")
    print(result.stdout, end="", flush=True)
    assert "successful run completed" in result.stdout
    print("PASS: stress bounded CPU and memory workload", flush=True)

if available("jq"):
    payload = '{"items":[{"name":"Android","enabled":true},{"name":"Linux","enabled":false}]}'
    assert run("jq", "-r", '.items[] | select(.enabled) | .name', input=payload).stdout == "Android\n"
    assert run("jq", "-r", 'test("^安卓")', input='"安卓系统"').stdout == "true\n"
    print("PASS: jq JSON filtering and Unicode regular expressions", flush=True)

if available("zstd"):
    payload = b"Android tools compressed round trip\n" * 1024
    compressed = run("zstd", "-q", "-c", input=payload, binary=True).stdout
    assert run("zstd", "-q", "-d", "-c", input=compressed, binary=True).stdout == payload
    print("PASS: zstd compression/decompression round trip", flush=True)

if available("sqlite3"):
    query = ("CREATE TABLE items(value); INSERT INTO items VALUES(21),(21); SELECT sum(value) FROM items; "
             "CREATE VIRTUAL TABLE words USING fts5(text); INSERT INTO words VALUES('android tools'); "
             "SELECT count(*) FROM words WHERE words MATCH 'android';")
    assert run("sqlite3", ":memory:", query).stdout == "42\n1\n"
    print("PASS: sqlite3 SQL and FTS5 queries", flush=True)

if available("socat"):
    assert "WITH_OPENSSL 1" in " ".join(run("socat", "-V").stdout.split())
    assert run("socat", "-u", "-", "STDOUT", input="android data relay\n").stdout == "android data relay\n"
    print("PASS: socat data relay and OpenSSL feature", flush=True)

if available("iperf3"):
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
            print(f"iperf3 client exit {result.returncode}: {result.stdout!r} {result.stderr!r}", flush=True)
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

if available("tcpdump"):
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

if available("strace"):
    assert "strace" in run("strace", "-V").stdout
    print("PASS: strace starts; ptrace execution needs native-device testing", flush=True)

if available("stress-ng"):
    result = run("stress-ng", "--cpu", "1", "--cpu-method", "sqrt", "--cpu-ops", "10", "--timeout", "5", "--metrics-brief")
    assert "successful run" in result.stdout + result.stderr
    print("PASS: stress-ng bounded CPU workload", flush=True)

if available("busybox"):
    metadata = BIN.parent / 'busybox'
    applets = run('busybox', '--list').stdout.splitlines()
    assert applets == (metadata / 'applets.txt').read_text().splitlines()
    assert len(applets) >= 300, f'Expected a broad BusyBox build, got {len(applets)} applets'
    required = {'ash', 'hush', 'awk', 'sed', 'grep', 'xargs', 'find', 'stat', 'tar',
                'gzip', 'unzip', 'bzip2', 'httpd', 'nc', 'wget', 'crond', 'crontab',
                'vi', 'less', 'ip', 'nslookup', 'ping', 'timeout', 'sha256sum', 'bbconfig', 'bc'}
    assert required <= set(applets), sorted(required - set(applets))
    assert 'CONFIG_STATIC=y' in run('busybox', 'bbconfig').stdout
    assert run('busybox', 'ash', '-c', 'printf "b\\na\\nb\\n" | sort | uniq | tr a-z A-Z').stdout == 'A\nB\n'
    assert run('busybox', 'hush', '-c', 'echo $((20 + 22))').stdout == '42\n'
    assert run('busybox', 'awk', '{total += $1} END {print total}', input='20\n22\n').stdout == '42\n'
    assert run('busybox', 'sed', 's/Android/Linux/g', input='Android tools\n').stdout == 'Linux tools\n'
    payload = b'Android BusyBox archive test\n' * 128
    packed = run('busybox', 'gzip', '-c', input=payload, binary=True).stdout
    assert run('busybox', 'gzip', '-dc', input=packed, binary=True).stdout == payload
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as dns:
        dns.bind(('127.0.0.1', 0))
        dns.settimeout(5)
        dns_port = dns.getsockname()[1]
        def answer_dns():
            query, peer = dns.recvfrom(4096)
            end = 12
            while query[end]:
                end += query[end] + 1
            question = query[12:end + 5]
            response = (query[:2] + struct.pack('!HHHHH', 0x8180, 1, 1, 0, 0)
                        + question + b'\xc0\x0c' + struct.pack('!HHIH', 1, 1, 60, 4)
                        + socket.inet_aton('192.0.2.123'))
            dns.sendto(response, peer)
        responder = threading.Thread(target=answer_dns, daemon=True)
        responder.start()
        result = run('busybox', 'nslookup', '-type=A', f'-port={dns_port}', 'fixture.test', '127.0.0.1')
        responder.join(timeout=5)
        assert '192.0.2.123' in result.stdout, result.stdout + result.stderr
    with tempfile.TemporaryDirectory(prefix='busybox-smoke-') as temporary:
        directory = pathlib.Path(temporary)
        (directory / 'input.txt').write_bytes(payload)
        large_size = 5 * 1024**3 + 17
        with (directory / 'large-sparse-file').open('wb') as sparse:
            sparse.truncate(large_size)
        assert run('busybox', 'stat', '-c', '%s', str(directory / 'large-sparse-file')).stdout.strip() == str(large_size)
        run('busybox', 'tar', '-czf', str(directory / 'test.tar.gz'), '-C', temporary, 'input.txt')
        assert run('busybox', 'tar', '-xOzf', str(directory / 'test.tar.gz'), 'input.txt', binary=True).stdout == payload
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        server = subprocess.Popen(command('busybox', 'httpd', '-f', '-p', f'127.0.0.1:{port}', '-h', temporary),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            url = f'http://127.0.0.1:{port}/input.txt'
            for attempt in range(30):
                try:
                    with opener.open(url, timeout=3) as response:
                        assert response.read() == payload
                    break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError(f'BusyBox httpd exited: {server.communicate()!r}')
                    if attempt == 29:
                        raise
                    time.sleep(0.1)
            assert run('busybox', 'wget', '-qO-', url, binary=True).stdout == payload
        finally:
            server.terminate()
            server.communicate(timeout=10)
    print(f'PASS: BusyBox {len(applets)} applets, ash/hush, awk/sed, gzip/tar and HTTP server/client', flush=True)

print(f"PASS: {ONLY} smoke-tested on {ARCH}", flush=True)
