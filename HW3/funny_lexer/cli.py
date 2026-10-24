"""CLI:  python -m funny_lexer {build|test|lex|report|all} ..."""
import argparse
import json
import sys
from pathlib import Path

from .export import table_dict, write_all
from .lexer import TableLexer
from .pipeline import build
from .report import render
from .spec import SpecError
from .testing import run_all, summarize

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = ROOT / "tests" / "cases.json"
DEFAULT_OUT = ROOT / "out"


def print_stats(st):
    print(f"НКА (Томпсон):        {st['nfa_states']} состояний, "
          f"{st['nfa_eps_edges']} ε-рёбер, {st['nfa_char_edges']} рёбер по символам")
    print(f"Классы символов:      {st['alphabet_size']} символов -> {st['char_classes']} классов")
    print(f"ДКА (подмножества):   {st['dfa_states']} состояний ({st['dfa_accepting']} принимающих)")
    print(f"Мин. ДКА (Хопкрофт):  {st['min_dfa_states']} состояний ({st['min_dfa_accepting']} принимающих), "
          f"ловушка = {st['min_dfa_trap']}")
    print(f"Проверки:             Мур={st['moore_check_states']}, "
          f"эквивалентен={st['min_equivalent_to_dfa']}, минимален={st['min_is_minimal']}")


def cmd_build(a):
    res = build(a.spec)
    files = write_all(res, a.out)
    print_stats(res.stats)
    print(f"Записано в {a.out}: {', '.join(files)}")
    return 0


def _run_tests(a, res):
    results = run_all(res, a.cases)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "test_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return results


def cmd_test(a):
    res = build(a.spec)
    results = _run_tests(a, res)
    for r in results:
        if r["status"] == "FAIL" or a.verbose:
            print(f"[{r['status']}] {r['group']:<12} {r['id']:<8} {r['input']!r}")
            if r["status"] == "FAIL":
                print(f"         ожидалось: {r['expected']}\n         получено:  {r['actual']}")
                if "detail" in r:
                    print(f"         {r['detail']}")
    print()
    total_p = total_f = 0
    for g, (p, f) in summarize(results).items():
        total_p, total_f = total_p + p, total_f + f
        print(f"  {g:<12} PASS {p:>4}   FAIL {f:>3}")
    print(f"  {'ИТОГО':<12} PASS {total_p:>4}   FAIL {total_f:>3}")
    print(f"Подробно: {Path(a.out) / 'test_results.json'}")
    return 1 if total_f else 0


def cmd_report(a):
    res = build(a.spec)
    results = _run_tests(a, res)
    Path(a.report).write_text(render(res, results), encoding="utf-8")
    print(f"Отчёт записан: {a.report}")
    return 0


def cmd_lex(a):
    lexer = TableLexer.from_json(a.table) if a.table else TableLexer(table_dict(build(a.spec)))
    try:
        text = sys.stdin.read() if a.file == "-" else Path(a.file).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Файл не найден: {a.file}", file=sys.stderr)
        return 2
    errors = 0
    for t in lexer.tokens(text, keep_skip=a.keep_skip):
        errors += lexer.is_error(t)
        print(f"{t.line:>4}:{t.col:<4} {t.kind:<14} {t.lexeme!r}")
    return 1 if errors else 0


def cmd_all(a):
    rc = cmd_build(a)
    print()
    rc |= cmd_test(a)
    cmd_report(a)
    return rc


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m funny_lexer",
                                description="Регулярные выражения -> НКА -> ДКА -> мин. ДКА для языка Funny")
    p.add_argument("--spec", default=None, help="файл спецификации токенов (по умолчанию spec/funny.tokens)")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="каталог для артефактов (по умолчанию out/)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("build", help="построить автоматы и экспортировать таблицы")
    t = sub.add_parser("test", help="прогнать тесты")
    t.add_argument("--cases", default=str(DEFAULT_CASES))
    t.add_argument("-v", "--verbose", action="store_true", help="печатать все тесты, а не только упавшие")
    r = sub.add_parser("report", help="сгенерировать REPORT.md")
    r.add_argument("--cases", default=str(DEFAULT_CASES))
    r.add_argument("--report", default=str(ROOT / "REPORT.md"))
    lx = sub.add_parser("lex", help="разбить файл на токены")
    lx.add_argument("file", help="путь к файлу или '-' для stdin")
    lx.add_argument("--table", help="готовая таблица dfa.json (иначе строится из спецификации)")
    lx.add_argument("--keep-skip", action="store_true", help="показывать WS и COMMENT")
    al = sub.add_parser("all", help="build + test + report")
    al.add_argument("--cases", default=str(DEFAULT_CASES))
    al.add_argument("--report", default=str(ROOT / "REPORT.md"))
    al.add_argument("-v", "--verbose", action="store_true")

    a = p.parse_args(argv)
    try:
        return {"build": cmd_build, "test": cmd_test, "report": cmd_report,
                "lex": cmd_lex, "all": cmd_all}[a.cmd](a)
    except SpecError as e:
        print(f"Ошибка спецификации: {e}", file=sys.stderr)
        return 2
