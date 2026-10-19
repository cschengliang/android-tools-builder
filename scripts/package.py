#!/usr/bin/env python3
"""Package built tools, notices and checksums; also works on Windows."""
import hashlib
import argparse
import json
import pathlib
import shutil
import tarfile

root = pathlib.Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--arch", required=True)
parser.add_argument("--tools", required=True)
args = parser.parse_args()
catalog = json.loads((root / "build-list.json").read_text())
sources = json.loads((root / "sources.json").read_text())
output = root / f"dist/android-{args.arch}"
tools = args.tools.split()
for tool in tools:
    if not (output / "bin" / catalog["tools"][tool]["binary"]).is_file():
        raise SystemExit(f"Missing executable: {tool}")
(output / "licenses").mkdir(exist_ok=True)
shutil.copyfile(root / "sources.json", output / "sources.json")
shutil.copyfile(root / "docs/USAGE.txt", output / "USAGE.txt")
if (output / "cacert.pem").exists():
    shutil.copyfile(root / "docs/CA-NOTICE.txt", output / "licenses/CA-NOTICE.txt")
shutil.copyfile(root / "BUILD-LIST.md", output / "BUILD-LIST.md")
info = {"architecture": args.arch, "abi": catalog["architectures"][args.arch]["abi"],
        "android_api": catalog["android_api"], "linkage": "static",
        "tools": {tool: {"binary": catalog["tools"][tool]["binary"], "version": sources[tool]["version"]} for tool in tools}}
(output / "build-info.json").write_text(json.dumps(info, indent=2) + "\n")
files = sorted(p for p in output.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
checksums = []
for file in files:
    with file.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    checksums.append(f"{digest}  {file.relative_to(output).as_posix()}")
(output / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8", newline="\n")
files.append(output / "SHA256SUMS")
archive = root / f"dist/android-{args.arch}-tools.tar.gz"
with tarfile.open(archive, "w:gz") as bundle:
    for file in files:
        name = file.relative_to(output).as_posix()
        info = bundle.gettarinfo(str(file), arcname=name)
        info.mode = 0o755 if name.startswith("bin/") else 0o644
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        with file.open("rb") as stream:
            bundle.addfile(info, stream)
print(f"Built package: {archive}")
