#!/usr/bin/env python3
import json
import pathlib
import sys

catalog = json.loads((pathlib.Path(__file__).resolve().parent.parent / "build-list.json").read_text())
arch = catalog["architectures"][sys.argv[2]]
with open(sys.argv[1], "rb") as stream:
    header = stream.read(20)
if (header[:4] != b"\x7fELF" or header[4:6] != bytes([arch["elf_class"], 1])
        or int.from_bytes(header[18:20], "little") != arch["machine"]):
    raise SystemExit(f"Incorrect ELF architecture for {sys.argv[1]} (expected {sys.argv[2]})")
