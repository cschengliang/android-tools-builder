#!/usr/bin/env python3
"""Retain the notices supplied with locked Rust dependencies and runtime."""
import json
import pathlib
import shutil
import sys

output = pathlib.Path(sys.argv[1])
for package in json.load(sys.stdin)["packages"]:
    source = pathlib.Path(package["manifest_path"]).parent
    destination = output / f"{package['name']}-{package['version']}"
    for pattern in ("LICENSE*", "COPYING*", "UNLICENSE*", "NOTICE*"):
        for notice in source.glob(pattern):
            destination.mkdir(parents=True, exist_ok=True)
            if notice.is_file():
                shutil.copyfile(notice, destination / notice.name)
            elif notice.is_dir():
                shutil.copytree(notice, destination / notice.name, dirs_exist_ok=True)
runtime = pathlib.Path(sys.argv[2]) / "share/doc/rust"
for name in ("COPYRIGHT", "LICENSE-APACHE", "LICENSE-MIT"):
    if (runtime / name).is_file():
        (output / "runtime").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(runtime / name, output / "runtime" / name)
