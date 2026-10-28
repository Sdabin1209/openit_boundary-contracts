"""directory_hash는 심볼릭 링크를 거부한다(CONVENTIONS 8절, 2.2.0). 기대값은 계약 문서의 규칙이다."""
import os
import tempfile
import unittest
from pathlib import Path

from boundary_contracts import BoundaryError
from boundary_contracts.canonical import directory_hash


class DirectoryHashSymlink(unittest.TestCase):
    def _tree(self):
        d = tempfile.TemporaryDirectory()
        root = Path(d.name)
        (root / "a.txt").write_text("A")
        (root / "sub").mkdir()
        (root / "sub" / "b.txt").write_text("B")
        return d, root

    def test_regular_tree_still_hashes(self):
        d, root = self._tree()
        with d:
            self.assertTrue(directory_hash(root).startswith("sha256:"))

    def test_file_symlink_is_rejected(self):
        d, root = self._tree()
        with d:
            os.symlink(root / "a.txt", root / "link.txt")
            with self.assertRaises(BoundaryError) as cm:
                directory_hash(root)
            self.assertEqual(cm.exception.code, "INTEGRITY_ERROR")
            self.assertIn("link.txt", str(cm.exception))

    def test_directory_symlink_is_rejected(self):
        d, root = self._tree()
        with d:
            os.symlink(root / "sub", root / "sublink")
            with self.assertRaises(BoundaryError):
                directory_hash(root)


if __name__ == "__main__":
    unittest.main()
