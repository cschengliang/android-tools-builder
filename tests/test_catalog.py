import unittest

from scripts.catalog import load, selection


class CatalogTests(unittest.TestCase):
    def test_current_matrix_covers_requested_tools_and_android_abis(self):
        catalog = load()
        self.assertEqual(set(selection("all", catalog["tools"])), {"ripgrep", "stress", "curl"})
        self.assertEqual({value["abi"] for value in catalog["architectures"].values()},
                         {"arm64-v8a", "armeabi-v7a", "x86_64", "x86"})
        self.assertEqual(selection("ripgrep,curl", catalog["tools"]), ["ripgrep", "curl"])

    def test_unknown_empty_and_duplicate_inputs_are_rejected(self):
        for value in ("", "curl curl", "curl; echo bad", "not-a-tool"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                selection(value, load()["tools"])
