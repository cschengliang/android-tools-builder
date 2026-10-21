import hashlib
import json
import pathlib
import tarfile
import tempfile
import unittest

from release.publish import ELF_TARGETS, prepare_assets, validate_run


class ReleaseValidationTests(unittest.TestCase):
    def make_package(self, work, *, corrupt_member=False, arm64=True, arch="arm64", legacy=False, source_suffixes=(), busybox_metadata=False):
        source = work / "fixture"
        (source / "bin").mkdir(parents=True)
        (source / "licenses").mkdir()
        elf_class, machine = ELF_TARGETS[arch]
        header = b"\x7fELF" + bytes([elf_class, 1]) + b"\x00" * 12
        (source / "bin/curl").write_bytes(header + (machine if arm64 else 999).to_bytes(2, "little"))
        (source / "sources.json").write_text(json.dumps({"curl": {"version": "test"}}))
        if not legacy:
            (source / "build-info.json").write_text(json.dumps({"architecture": arch, "tools": {"curl": {"binary": "curl", "version": "test"}}}))
        (source / "USAGE.txt").write_text("usage")
        (source / "cacert.pem").write_text("fixture CA")
        (source / "licenses/curl.txt").write_text("fixture license")
        if busybox_metadata:
            (source / 'busybox').mkdir()
            for name, content in {'config.txt': 'CONFIG_STATIC=y\n', 'applets.txt': 'ash\nawk\n',
                                  'build.json': '{"applet_count":2}\n'}.items():
                (source / 'busybox' / name).write_text(content)
        for suffix in source_suffixes:
            (source / "sources").mkdir(exist_ok=True)
            (source / "sources" / ("upstream-1.tar." + suffix)).write_bytes(b"fixture source archive")
        files = sorted(file for file in source.rglob("*") if file.is_file())
        (source / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256(file.read_bytes()).hexdigest()}  {file.relative_to(source).as_posix()}\n"
            for file in files))
        if corrupt_member:
            (source / "bin/curl").write_bytes(b"tampered")
        download = work / "download"
        download.mkdir()
        archive = download / f"android-{arch}-tools.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            for file in source.rglob("*"):
                if file.is_file():
                    bundle.add(file, arcname=file.relative_to(source).as_posix())
        (download / (archive.name + ".sha256")).write_text(
            hashlib.sha256(archive.read_bytes()).hexdigest() + "  dist/" + archive.name + "\n")
        return download

    def test_preserves_verified_binary_and_includes_notices(self):
        with tempfile.TemporaryDirectory() as directory:
            work = pathlib.Path(directory)
            download = self.make_package(work)
            assets, tools = prepare_assets(download, work / "assets")
            self.assertEqual(tools, {"curl": "test"})
            self.assertIn("licenses-android-arm64.tar.gz", [file.name for file in assets])
            self.assertIn("cacert.pem", [file.name for file in assets])
            self.assertEqual((work / "assets/cacert.pem").read_bytes(), (work / "fixture/cacert.pem").read_bytes())
            self.assertEqual((work / "assets/curl-android-arm64").read_bytes(),
                             (work / "fixture/bin/curl").read_bytes())

    def test_rejects_package_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            work = pathlib.Path(directory)
            download = self.make_package(work)
            (download / "android-arm64-tools.tar.gz").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "package checksum"):
                prepare_assets(download, work / "assets")

    def test_busybox_config_and_applets_are_preserved_as_release_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            work = pathlib.Path(directory)
            download = self.make_package(work, busybox_metadata=True)
            prepare_assets(download, work / 'assets')
            for name in ('config.txt', 'applets.txt', 'build.json'):
                stem, extension = name.rsplit('.', 1)
                self.assertEqual((work / 'assets' / f'busybox-{stem}-android-arm64.{extension}').read_bytes(),
                                 (work / 'fixture/busybox' / name).read_bytes())
            with tarfile.open(work / 'assets/licenses-android-arm64.tar.gz') as bundle:
                self.assertIn('busybox/config.txt', bundle.getnames())

    def test_source_archives_preserve_all_compression_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            work = pathlib.Path(directory)
            assets, _ = prepare_assets(self.make_package(work, source_suffixes=("gz", "bz2", "xz")), work / "assets")
            names = {file.name for file in assets}
            for suffix in ("gz", "bz2", "xz"):
                self.assertIn("upstream-1-source.tar." + suffix, names)
                self.assertEqual((work / "assets" / ("upstream-1-source.tar." + suffix)).read_bytes(), b"fixture source archive")

    def test_rejects_tampered_member(self):
        with tempfile.TemporaryDirectory() as directory:
            work = pathlib.Path(directory)
            download = self.make_package(work, corrupt_member=True)
            with self.assertRaisesRegex(ValueError, "member checksum"):
                prepare_assets(download, work / "assets")

    def test_rejects_wrong_architecture(self):
        with tempfile.TemporaryDirectory() as directory:
            work = pathlib.Path(directory)
            download = self.make_package(work, arm64=False)
            with self.assertRaisesRegex(ValueError, "arm64 ELF"):
                prepare_assets(download, work / "assets")

    def test_all_architectures_produce_distinct_assets(self):
        for arch in ELF_TARGETS:
            with self.subTest(arch=arch), tempfile.TemporaryDirectory() as directory:
                work = pathlib.Path(directory)
                assets, tools = prepare_assets(self.make_package(work, arch=arch), work / "assets")
                self.assertIn(f"curl-android-{arch}", [file.name for file in assets])
                self.assertIn(f"android-{arch}-tools.tar.gz", [file.name for file in assets])
                self.assertEqual(tools, {"curl": "test"})

    def test_legacy_arm64_artifact_is_still_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            work = pathlib.Path(directory)
            _, tools = prepare_assets(self.make_package(work, legacy=True), work / "assets")
            self.assertEqual(tools, {"curl": "test"})

    def test_rejects_failed_or_foreign_builds(self):
        run = {"status": "completed", "conclusion": "success", "head_branch": "main",
               "head_repository": {"full_name": "owner/repo"}, "head_sha": "a" * 40,
               "path": ".github/workflows/build.yml", "event": "push"}
        validate_run(run, "owner/repo")
        for field, value in (("conclusion", "failure"), ("head_branch", "feature"),
                             ("path", ".github/workflows/other.yml"),
                             ("head_repository", {"full_name": "someone/fork"})):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_run({**run, field: value}, "owner/repo")


if __name__ == "__main__":
    unittest.main()
