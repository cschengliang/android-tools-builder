#!/usr/bin/env python3
"""Download the exact upstream inputs recorded in sources.json."""
import argparse
import hashlib
import json
import pathlib
import subprocess
import tarfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="+")
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parent.parent
    sources = json.loads((root / "sources.json").read_text(encoding="utf-8"))
    cache = root / ".work" / "downloads"
    cache.mkdir(parents=True, exist_ok=True)
    for name in args.names:
        source = sources[name]
        archive = cache / source["filename"]
        algorithm, expected = source["checksum"].split(":", 1)

        def digest():
            with archive.open("rb") as stream:
                return hashlib.file_digest(stream, algorithm).hexdigest()

        if not archive.exists() or digest() != expected:
            temporary = archive.with_name(archive.name + ".part")
            subprocess.run([
                "curl", "--fail", "--location", "--retry", "3",
                "--connect-timeout", "30", "--proto", "=https", "--tlsv1.2",
                "--output", str(temporary), source["url"],
            ], check=True)
            temporary.replace(archive)
        if digest() != expected:
            raise SystemExit(f"Checksum mismatch: {archive.name}")
        if "directory" not in source:
            continue
        destination = root / ".work" / source["directory"]
        marker = destination / ".verified-source"
        if marker.exists() and marker.read_text() == source["checksum"]:
            continue
        parent = destination.parent
        parent.mkdir(parents=True, exist_ok=True)
        if archive.suffix == ".zip":
            # The official NDK ZIP contains Unix executable and symlink modes.
            subprocess.run(["unzip", "-qo", str(archive), "-d", str(parent)], check=True)
        else:
            with tarfile.open(archive) as bundle:
                bundle.extractall(parent, filter="data")
        if not destination.is_dir():
            raise SystemExit(f"Expected source directory was not extracted: {destination}")
        marker.write_text(source["checksum"])
        print(f"Verified and extracted {name} {source['version']}", flush=True)


if __name__ == "__main__":
    main()
