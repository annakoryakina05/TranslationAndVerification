import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from funny_lexer.export import table_dict  # noqa: E402
from funny_lexer.lexer import TableLexer  # noqa: E402
from funny_lexer.pipeline import build  # noqa: E402
from funny_lexer.regex import RegexError, parse_regex  # noqa: E402
from funny_lexer.spec import SpecError, parse_spec  # noqa: E402
from funny_lexer.testing import run_all  # noqa: E402


class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = build()
        cls.results = run_all(cls.res, ROOT / "tests" / "cases.json")

    def test_all_cases(self):
        for r in self.results:
            with self.subTest(id=r["id"], group=r["group"], input=r["input"]):
                self.assertEqual(r["status"], "PASS", r)

    def test_exported_python_table_roundtrip(self):
        ns = {}
        from funny_lexer.export import write_python
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.py"
            write_python(table_dict(self.res), p)
            exec(p.read_text(encoding="utf-8"), ns)
        self.assertEqual(TableLexer(ns["TABLE"]).match("while"), "KW_WHILE")


class TestSpecErrors(unittest.TestCase):
    def test_bad_regex(self):
        for bad in ["(a", "[a", "*a", '"abc', "[z-a]", "[]", "\\q", "é"]:
            with self.subTest(regex=bad), self.assertRaises(RegexError):
                parse_regex(bad)

    def test_nullable_token_rejected(self):
        with self.assertRaises(SpecError):
            parse_spec("X = a*")

    def test_duplicate_rejected(self):
        with self.assertRaises(SpecError):
            parse_spec("X = a\nX = b")


if __name__ == "__main__":
    unittest.main()
