#!/usr/bin/env python3
"""Publish a successful build's verified artifacts; never compile on this path."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import tarfile
import tempfile

ELF_TARGETS = {"arm64": (2, 183), "armv7": (1, 40), "x86_64": (2, 62), "x86": (1, 3)}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_run(run, repository):
    if (run["status"], run["conclusion"]) != ("completed", "success"):
        raise ValueError("Only completed, successful builds can be released")
    if run["head_branch"] != "main" or run["head_repository"]["full_name"] != repository:
        raise ValueError("The build must originate from this repository's main branch")
    if run["path"] != ".github/workflows/build.yml" or run["event"] not in ("push", "workflow_dispatch"):
        raise ValueError("Unexpected source build workflow or trigger")
    if not re.fullmatch(r"[0-9a-f]{40}", run["head_sha"]):
        raise ValueError("Invalid source commit SHA")


def prepare_assets(download, output):
    archives = list(download.glob("android-*-tools.tar.gz"))
    if len(archives) != 1:
        raise ValueError("Expected one architecture package")
    archive = archives[0]
    match = re.fullmatch(r"android-(arm64|armv7|x86_64|x86)-tools.tar.gz", archive.name)
    if not match:
        raise ValueError("Unknown package architecture")
    arch = match[1]
    expected = (download / (archive.name + ".sha256")).read_text().split()[0]
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or digest(archive) != expected:
        raise ValueError("Build package checksum mismatch")
    extracted = output.parent / f"{output.name}-extracted"
    extracted.mkdir(parents=True)
    with tarfile.open(archive) as bundle:
        if any(not (member.isfile() or member.isdir()) for member in bundle.getmembers()):
            raise ValueError("Build package may contain only regular files and directories")
        bundle.extractall(extracted, filter="data")
    verified = set()
    for line in (extracted / "SHA256SUMS").read_text().splitlines():
        checksum, name = line.split("  ", 1)
        file = (extracted / name).resolve()
        if not file.is_relative_to(extracted.resolve()) or digest(file) != checksum:
            raise ValueError(f"Package member checksum mismatch: {name}")
        verified.add(file)
    actual = {file.resolve() for file in extracted.rglob("*") if file.is_file() and file.name != "SHA256SUMS"}
    if actual != verified:
        raise ValueError("Package contains unverified files")
    output.mkdir(parents=True)
    versions = json.loads((extracted / "sources.json").read_text())
    info_path = extracted / "build-info.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else {"architecture": "arm64", "tools": {}}
    if info["architecture"] != arch:
        raise ValueError("Package architecture does not match build metadata")
    tools = {}
    for binary in sorted((extracted / "bin").iterdir()):
        if binary.resolve() not in verified or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._+-]*", binary.name):
            raise ValueError("Unverified or invalid executable")
        header = binary.read_bytes()[:20]
        elf_class, machine = ELF_TARGETS[arch]
        if header[:6] != b"\x7fELF" + bytes([elf_class, 1]) or int.from_bytes(header[18:20], "little") != machine:
            raise ValueError(f"Not a {arch} ELF executable: {binary.name}")
        shutil.copyfile(binary, output / f"{binary.name}-android-{arch}")
        identity = next((name for name, value in info["tools"].items() if value["binary"] == binary.name), {"rg": "ripgrep"}.get(binary.name, binary.name))
        tools[identity] = versions[identity]["version"]
    if not tools:
        raise ValueError("Build package has no executables")
    # Publish notices alongside the standalone executables as well as in the full package.
    with tarfile.open(output / f"licenses-android-{arch}.tar.gz", "w:gz") as notices:
        for name in ("licenses", "sources.json", "USAGE.txt", "cacert.pem", "build-info.json", "BUILD-LIST.md", "sources"):
            if (extracted / name).exists():
                notices.add(extracted / name, arcname=name)
    for source in (extracted / "sources").glob("*.tar.gz"):
        shutil.copyfile(source, output / (source.name.removesuffix(".tar.gz") + "-source.tar.gz"))
    shutil.copyfile(archive, output / archive.name)
    (output / (archive.name + ".sha256")).write_text(f"{expected}  {archive.name}\n")
    assets = sorted(output.iterdir())
    checksums = output / f"SHA256SUMS-android-{arch}"
    checksums.write_text("".join(f"{digest(file)}  {file.name}\n" for file in assets))
    return assets + [checksums], tools


def api(path, missing_ok=False):
    result = subprocess.run(["gh", "api", path], text=True, capture_output=True)
    if result.returncode:
        if missing_ok and "HTTP 404" in result.stderr:
            return None
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def report(url):
    print(f"Release: {url}", flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
            summary.write(f"### Android tools Release\n\n[Download binaries and checksums]({url})\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, type=int)
    args = parser.parse_args()
    repository = os.environ["GH_REPO"]
    run = api(f"repos/{repository}/actions/runs/{args.run_id}")
    validate_run(run, repository)
    tag = f"android-tools-build-{run['run_number']}"
    existing = api(f"repos/{repository}/releases/tags/{tag}", missing_ok=True)
    if existing:
        if existing["target_commitish"] != run["head_sha"]:
            raise ValueError("Existing release refers to a different source commit")
        if not existing["draft"]:
            report(existing["html_url"])
            return
    with tempfile.TemporaryDirectory(prefix="android-release-") as temporary:
        work = pathlib.Path(temporary)
        published = work / "assets"
        published.mkdir()
        artifacts = api(f"repos/{repository}/actions/runs/{args.run_id}/artifacts?per_page=100")["artifacts"]
        artifacts = [artifact for artifact in artifacts if not artifact["expired"] and re.fullmatch(r"android-(arm64|armv7|x86_64|x86)-tools", artifact["name"])]
        if not artifacts or len({item["name"] for item in artifacts}) != len(artifacts):
            raise ValueError("Expected unique, available architecture artifacts")
        matrix = {}
        for artifact in sorted(artifacts, key=lambda item: item["name"]):
            arch = artifact["name"][8:-6]
            download = work / "download" / arch
            subprocess.run(["gh", "run", "download", str(args.run_id), "--repo", repository,
                            "--name", artifact["name"], "--dir", str(download)], check=True)
            files, tools = prepare_assets(download, work / "staging" / arch)
            matrix[arch] = tools
            for file in files:
                destination = published / file.name
                if destination.exists() and digest(destination) != digest(file):
                    raise ValueError(f"Conflicting release asset: {file.name}")
                shutil.copyfile(file, destination)
        assets = sorted(published.iterdir())
        checksum = published / "SHA256SUMS"
        checksum.write_text("".join(f"{digest(file)}  {file.name}\n" for file in assets))
        assets.append(checksum)
        notes = work / "release-notes.md"
        arches = [arch for arch in ELF_TARGETS if arch in matrix]
        tool_names = sorted({name for tools in matrix.values() for name in tools})
        versions = "| 工具 | 版本 | " + " | ".join(arches) + " |\n| --- | --- | " + " | ".join(["---"] * len(arches)) + " |\n"
        for name in tool_names:
            pinned = {tools[name] for tools in matrix.values() if name in tools}
            if len(pinned) != 1:
                raise ValueError(f"Inconsistent tool versions: {name}")
            versions += f"| {name} | {pinned.pop()} | " + " | ".join("✓" if name in matrix[arch] else "—" for arch in arches) + " |\n"
        notes.write_text(
            f"Android 10+ (API 29) 多架构静态命令行工具。\n\n{versions}\n\n"
            f"由 [GitHub Actions 构建 #{run['run_number']}]({run['html_url']}) 从源码编译，"
            "并通过各架构 ELF、静态链接及 QEMU 功能测试。\n\n"
            f"源码提交：`{run['head_sha']}`。\n\n"
            "下载完整工具包可同时获得使用说明和许可证；也可以直接下载单个 "
            "`*-android-架构` 文件。`licenses-android-架构.tar.gz` 提供对应的许可证和源码版本清单；stress 的对应源码也作为独立附件提供。\n\n"
            "复制到 Android 有执行权限的目录后：\n\n"
            "```sh\nchmod 755 curl-android-arm64\n./curl-android-arm64 --version\n```\n\n"
            "用 `sha256sum -c SHA256SUMS` 校验全部附件，或使用工具包对应的 `.sha256` 文件。\n",
            encoding="utf-8")
        if existing:
            subprocess.run(["gh", "release", "upload", tag, "--repo", repository,
                            "--clobber", *map(str, assets)], check=True)
        else:
            subprocess.run(["gh", "release", "create", tag, "--repo", repository,
                            "--draft", "--target", run["head_sha"],
                            "--title", f"Android tools · Build {run['run_number']}",
                            "--notes-file", str(notes), *map(str, assets)], check=True)
        subprocess.run(["gh", "release", "edit", tag, "--repo", repository,
                        "--draft=false", "--latest", "--notes-file", str(notes)], check=True)
        report(api(f"repos/{repository}/releases/tags/{tag}")["html_url"])


if __name__ == "__main__":
    main()
