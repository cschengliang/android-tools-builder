#!/usr/bin/env python3
"""Package built tools, notices and checksums; also works on Windows."""
import hashlib
import pathlib
import shutil
import tarfile

root = pathlib.Path(__file__).resolve().parent.parent
output = root / "dist/android-arm64"
if not (output / "bin/curl").is_file():
    raise SystemExit("Build curl before packaging")
(output / "licenses").mkdir(exist_ok=True)
shutil.copyfile(root / "sources.json", output / "sources.json")
shutil.copyfile(root / "docs/USAGE.txt", output / "USAGE.txt")
shutil.copyfile(root / "docs/CA-NOTICE.txt", output / "licenses/CA-NOTICE.txt")
files = sorted(p for p in output.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
checksums = []
for file in files:
    with file.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    checksums.append(f"{digest}  {file.relative_to(output).as_posix()}")
(output / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8", newline="\n")
files.append(output / "SHA256SUMS")
archive = root / "dist/android-arm64-tools.tar.gz"
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
