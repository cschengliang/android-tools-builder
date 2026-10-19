import hashlib
import json
import pathlib
import tarfile
import tempfile
import unittest

from release.publish import prepare_assets, validate_run


class ReleaseValidationTests(unittest.TestCase):
    def make_package(self, work, *, corrupt_member=False, arm64=True):
        source = work / "fixture"
        (source / "bin").mkdir(parents=True)
        (source / "licenses").mkdir()
        header = b"\x7fELF\x02\x01" + b"\x00" * 12
        (source / "bin/curl").write_bytes(header + (b"\xb7\x00" if arm64 else b"\x3e\x00"))
        (source / "sources.json").write_text(json.dumps({"curl": {"version": "test"}}))
        (source / "USAGE.txt").write_text("usage")
        (source / "cacert.pem").write_text("fixture CA")
        (source / "licenses/curl.txt").write_text("fixture license")
        files = sorted(file for file in source.rglob("*") if file.is_file())
        (source / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256(file.read_bytes()).hexdigest()}  {file.relative_to(source).as_posix()}\n"
            for file in files))
        if corrupt_member:
            (source / "bin/curl").write_bytes(b"tampered")
        download = work / "download"
        download.mkdir()
        archive = download / "android-arm64-tools.tar.gz"
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
            self.assertIn("licenses.tar.gz", [file.name for file in assets])
            self.assertEqual((work / "assets/curl-android-arm64").read_bytes(),
                             (work / "fixture/bin/curl").read_bytes())

    def test_rejects_package_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            work = pathlib.Path(directory)
            download = self.make_package(work)
            (download / "android-arm64-tools.tar.gz").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "package checksum"):
                prepare_assets(download, work / "assets")

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
            with self.assertRaisesRegex(ValueError, "ARM64 ELF"):
                prepare_assets(download, work / "assets")

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
