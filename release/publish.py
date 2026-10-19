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
    archive = download / "android-arm64-tools.tar.gz"
    expected = (download / (archive.name + ".sha256")).read_text().split()[0]
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or digest(archive) != expected:
        raise ValueError("Build package checksum mismatch")
    extracted = output.parent / "extracted"
    extracted.mkdir()
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
    output.mkdir()
    versions = json.loads((extracted / "sources.json").read_text())
    tools = {}
    for binary in sorted((extracted / "bin").iterdir()):
        if binary.resolve() not in verified or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._+-]*", binary.name):
            raise ValueError("Unverified or invalid executable")
        header = binary.read_bytes()[:20]
        if header[:6] != b"\x7fELF\x02\x01" or header[18:20] != b"\xb7\x00":
            raise ValueError(f"Not an ARM64 ELF executable: {binary.name}")
        shutil.copyfile(binary, output / f"{binary.name}-android-arm64")
        tools[binary.name] = versions[binary.name]["version"]
    if not tools:
        raise ValueError("Build package has no executables")
    # Publish notices alongside the standalone executables as well as in the full package.
    with tarfile.open(output / "licenses.tar.gz", "w:gz") as notices:
        for name in ("licenses", "sources.json", "USAGE.txt", "cacert.pem"):
            notices.add(extracted / name, arcname=name)
    shutil.copyfile(archive, output / archive.name)
    (output / (archive.name + ".sha256")).write_text(f"{expected}  {archive.name}\n")
    assets = sorted(output.iterdir())
    checksums = output / "SHA256SUMS"
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
            summary.write(f"### Android ARM64 Release\n\n[Download binaries and checksums]({url})\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, type=int)
    args = parser.parse_args()
    repository = os.environ["GH_REPO"]
    run = api(f"repos/{repository}/actions/runs/{args.run_id}")
    validate_run(run, repository)
    tag = f"android-arm64-build-{run['run_number']}"
    existing = api(f"repos/{repository}/releases/tags/{tag}", missing_ok=True)
    if existing:
        if existing["target_commitish"] != run["head_sha"]:
            raise ValueError("Existing release refers to a different source commit")
        if not existing["draft"]:
            report(existing["html_url"])
            return
    with tempfile.TemporaryDirectory(prefix="android-release-") as temporary:
        work = pathlib.Path(temporary)
        download = work / "download"
        subprocess.run(["gh", "run", "download", str(args.run_id), "--repo", repository,
                        "--name", "android-arm64-tools", "--dir", str(download)], check=True)
        assets, tools = prepare_assets(download, work / "assets")
        notes = work / "release-notes.md"
        versions = "\n".join(f"- **{name} {version}**" for name, version in tools.items())
        notes.write_text(
            f"Android 10+ (API 29), ARM64 静态命令行工具。\n\n{versions}\n\n"
            f"由 [GitHub Actions 构建 #{run['run_number']}]({run['html_url']}) 从源码编译，"
            "并通过 ARM64 架构、静态链接及 QEMU 功能测试。\n\n"
            f"源码提交：`{run['head_sha']}`。\n\n"
            "下载完整工具包可同时获得使用说明和许可证；也可以直接下载单个 "
            "`*-android-arm64` 文件。`licenses.tar.gz` 提供对应的许可证和源码版本清单。\n\n"
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
                            "--title", f"Android ARM64 tools · Build {run['run_number']}",
                            "--notes-file", str(notes), *map(str, assets)], check=True)
        subprocess.run(["gh", "release", "edit", tag, "--repo", repository,
                        "--draft=false", "--latest", "--notes-file", str(notes)], check=True)
        report(api(f"repos/{repository}/releases/tags/{tag}")["html_url"])


if __name__ == "__main__":
    main()
