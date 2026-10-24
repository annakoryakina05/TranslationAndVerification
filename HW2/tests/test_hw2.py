"""unittest-обёртка для парсера: python3 -m unittest discover -s tests -v"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from funny_parser.testing import run_all  


class TestParser(unittest.TestCase):
    def test_all(self):
        for r in run_all():
            with self.subTest(group=r["group"], name=r["name"]):
                self.assertEqual(r["status"], "PASS", r)


if __name__ == "__main__":
    unittest.main()
