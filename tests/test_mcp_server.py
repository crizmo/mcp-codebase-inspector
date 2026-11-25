"""Checks for the read-only trust boundary. Run: python -m unittest discover -s tests -t ."""
from pathlib import Path
import tempfile
import unittest

import mcp_server as s


class ConfinementTests(unittest.TestCase):
    def test_paths_cannot_escape_root(self):
        for bad in ("../outside", "/etc/passwd"):
            with self.assertRaises(ValueError):
                s._path(bad)
        self.assertIn("MCP_ROOT", s.project_summary(path="../outside"))

    def test_symlink_outside_root_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "inside.txt").write_text("ok")
            (root / "leak.txt").symlink_to("/etc/passwd")
            original = s.ROOT
            s.ROOT = root
            try:
                self.assertEqual([f.name for f in s._files(root)], ["inside.txt"])
            finally:
                s.ROOT = original

    def test_search_result_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "hits.txt").write_text("TODO\na\nTODO\nb\nTODO\n")
            original = s.ROOT
            s.ROOT = root
            try:
                out = s.search_code("TODO", max_results=2)
                self.assertIn("capped at 2 results", out)
            finally:
                s.ROOT = original

    def test_read_file_caps_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "long.txt").write_text("a\nb\nc\n")
            original = s.ROOT
            s.ROOT = root
            try:
                out = s.read_file("long.txt", start_line=2, max_lines=1)
                self.assertIn("2 | b", out)
                self.assertIn("truncated", out)
            finally:
                s.ROOT = original


if __name__ == "__main__":
    unittest.main()
