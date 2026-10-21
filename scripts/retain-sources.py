#!/usr/bin/env python3
"""Include exact source inputs and build recipes for copyleft executables."""
import json
import pathlib
import shutil
import sys

root = pathlib.Path(__file__).resolve().parent.parent
catalog = json.loads((root / "build-list.json").read_text(encoding="utf-8"))
sources = json.loads((root / "sources.json").read_text())
output = pathlib.Path(sys.argv[1]) / "sources"
names = set()
for name in sys.argv[2:]:
    if name == "stress" or catalog["tools"][name].get("distribute_sources"):
        names.update(catalog["tools"][name]["dependencies"])
for name in sorted(names):
    filename = sources[name]["filename"]
    if ".tar." in filename:
        output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / ".work/downloads" / filename, output / filename)
if names:
    recipes = output / "build-rules"
    shutil.copytree(root / "scripts", recipes / "scripts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    for filename in ("sources.json", "build-list.json", "BUILD-LIST.md"):
        shutil.copyfile(root / filename, recipes / filename)
    shutil.copytree(root / "docs", recipes / "docs", dirs_exist_ok=True)
    shutil.copytree(root / "patches", recipes / "patches", dirs_exist_ok=True)
    metadata = pathlib.Path(sys.argv[1]) / "busybox"
    if metadata.is_dir():
        shutil.copytree(metadata, recipes / "busybox-build", dirs_exist_ok=True)
