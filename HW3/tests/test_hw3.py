"""unittest-обёртка для семантики: python3 -m unittest discover -s tests -v"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from funny_sema.testing import run_all  # noqa: E402


class TestSema(unittest.TestCase):
    def test_all(self):
        for r in run_all():
            with self.subTest(group=r["group"], name=r["name"]):
                self.assertEqual(r["status"], "PASS", r)


if __name__ == "__main__":
    unittest.main()
