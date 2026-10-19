#!/usr/bin/env python3
"""Single source of truth for the build matrix and its human-readable table."""
import argparse
import json
import os
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load():
    return json.loads((ROOT / "build-list.json").read_text(encoding="utf-8"))


def selection(value, available):
    names = list(available) if value.strip() == "all" else re.split(r"[\s,]+", value.strip())
    if not names or any(name not in available for name in names) or len(set(names)) != len(names):
        raise ValueError(f"Invalid selection {value!r}; choose from {', '.join(available)} or all")
    return names


def table():
    catalog = load()
    sources = json.loads((ROOT / "sources.json").read_text())
    arches = list(catalog["architectures"])
    lines = ["| 工具 | 程序名 | 固定版本 | 用途 | " + " | ".join(arches) + " |",
             "| --- | --- | --- | --- | " + " | ".join(["---"] * len(arches)) + " |"]
    for name, tool in catalog["tools"].items():
        lines.append(f"| [{name}]({tool['homepage']}) | `{tool['binary']}` | {sources[name]['version']} | {tool['description']} | " + " | ".join(["✓"] * len(arches)) + " |")
    lines += ["", "✓ 表示纳入 Actions 构建和测试矩阵；成功结果以 Actions 和 Release 为准。所有架构面向 Android 10+（API 29），不要求额外第三方动态库。"]
    return "\n".join(lines) + "\n"


def document():
    catalog = load()
    result = "# 编译列表\n\n由 `build-list.json` 和 `sources.json` 生成。\n\n" + table()
    result += "\n## 架构对照\n\n| 架构标识 | Android ABI | 用途 |\n| --- | --- | --- |\n"
    for name, arch in catalog["architectures"].items():
        result += f"| `{name}` | `{arch['abi']}` | {arch['description']} |\n"
    result += "\n## 功能\n\n"
    for name, tool in catalog["tools"].items():
        result += f"- **{name}**：{tool['features']}。\n"
    result += "\n维护清单后执行 `python3 scripts/catalog.py write` 更新表格；Actions 会检查表格与规则一致。实际编译和发布均在 GitHub 运行器上执行。\n"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["write", "check", "plan", "dependencies", "arch", "rust-version"])
    parser.add_argument("--tools", default="all")
    parser.add_argument("--architectures", default="all")
    parser.add_argument("--arch", default="arm64")
    parser.add_argument("--field")
    args = parser.parse_args()
    catalog = load()
    if args.command in ("write", "check"):
        expected = document()
        readme = ROOT / "README.md"
        old = readme.read_text(encoding="utf-8")
        updated, count = re.subn(r"(?s)(<!-- build-list:start -->\n).*?(<!-- build-list:end -->)", lambda match: match[1] + table() + match[2], old)
        if count != 1:
            raise SystemExit("README must contain exactly one build-list marker pair")
        if args.command == "write":
            (ROOT / "BUILD-LIST.md").write_text(expected, encoding="utf-8", newline="\n")
            readme.write_text(updated, encoding="utf-8", newline="\n")
        elif (ROOT / "BUILD-LIST.md").read_text(encoding="utf-8") != expected or updated != old:
            raise SystemExit("Build list is stale; run python3 scripts/catalog.py write")
    elif args.command == "arch":
        print(catalog["architectures"][args.arch][args.field])
    elif args.command == "rust-version":
        print(catalog["rust_toolchain"])
    else:
        tools = selection(args.tools, catalog["tools"])
        if args.command == "dependencies":
            print(" ".join(dict.fromkeys(["ndk"] + [dep for name in tools for dep in catalog["tools"][name]["dependencies"]])))
        else:
            arches = selection(args.architectures, catalog["architectures"])
            matrix = {"include": [{"arch": arch, "tools": " ".join(tools)} for arch in arches]}
            encoded = json.dumps(matrix, separators=(",", ":"))
            print(encoded)
            if os.environ.get("GITHUB_OUTPUT"):
                with open(os.environ["GITHUB_OUTPUT"], "a") as output:
                    output.write(f"matrix={encoded}\n")
            if os.environ.get("GITHUB_STEP_SUMMARY"):
                with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as output:
                    output.write(table())


if __name__ == "__main__":
    main()
