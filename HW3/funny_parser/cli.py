"""CLI:  python3 -m funny_parser {parse|tokens|grammar|test|all} ..."""
import argparse
import json
import sys
from pathlib import Path

from . import ll1
from .ast import to_json, to_text
from .parser import parse_program
from .testing import run_all, summarize
from .tokens import tokenize

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"


def read_input(path):
    if path == "-":
        return sys.stdin.read(), "<stdin>"
    try:
        return Path(path).read_text(encoding="utf-8"), path
    except FileNotFoundError:
        print(f"Файл не найден: {path}", file=sys.stderr)
        sys.exit(2)


def cmd_parse(a):
    text, name = read_input(a.file)
    module, diags = parse_program(text)
    for d in diags:
        print(f"{name}:{d.line}:{d.col}: ошибка: {d.message}", file=sys.stderr)
    if diags and not a.partial:
        print(f"Найдено ошибок: {len(diags)}; AST не выведен (флаг --partial покажет частичное дерево)",
              file=sys.stderr)
        return 1
    print(to_json(module) if a.json else to_text(module), end="" if not a.json else "\n")
    return 1 if diags else 0


def cmd_tokens(a):
    text, name = read_input(a.file)
    diags = []
    for t in tokenize(text, diags):
        print(f"{t.line:>4}:{t.col:<4} {t.kind:<14} {t.lexeme!r}")
    for d in diags:
        print(f"{name}:{d.line}:{d.col}: ошибка: {d.message}", file=sys.stderr)
    return 1 if diags else 0


def cmd_grammar(a):
    from funny_lexer.spec import load_spec
    g = ll1.load_grammar()
    an = ll1.analyze(g, {t.name for t in load_spec()})
    ll1.write_reports(an, OUT)
    print(f"Грамматика: {len(g.rules)} нетерминалов, {len(g.terminals)} терминалов, "
          f"{sum(len(v) for v in g.rules.values())} продукций")
    print(f"Конфликтов LL(1): {len(an.conflicts)}")
    for nt, t, ks in an.conflicts:
        alts = " | ".join(ll1.alt_str(g.rules[nt][k]) for k in ks)
        mark = "ожидаемый" if (nt, t) in ll1.EXPECTED_CONFLICTS else "НЕОЖИДАННЫЙ"
        print(f"  [{mark}] {nt} при {t}: {alts}")
    if an.unknown_terminals:
        print(f"Терминалы, которых нет в лексере: {an.unknown_terminals}")
    if an.unreachable:
        print(f"Недостижимые нетерминалы: {an.unreachable}")
    if a.verbose:
        for nt in g.nonterminals:
            print(f"{nt}\n  FIRST  = {sorted(an.first[nt])}\n  FOLLOW = {sorted(an.follow[nt])}")
    print(f"FIRST/FOLLOW: {OUT / 'll1_first_follow.txt'}\nТаблица разбора: {OUT / 'll1_table.csv'}")
    bad = an.unexpected_conflicts or an.unknown_terminals or an.unreachable
    return 1 if bad else 0


def cmd_test(a):
    results = run_all(update=a.update)
    OUT.mkdir(exist_ok=True)
    (OUT / "parser_test_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for r in results:
        if r["status"] == "FAIL" or a.verbose:
            print(f"[{r['status']}] {r['group']:<10} {r['name']}")
            if r["status"] == "FAIL":
                print(f"   ожидалось: {r['expected']!r}\n   получено:  {r['actual']!r}")
                if "detail" in r:
                    print(f"   {r['detail']}")
    print()
    tp = tf = 0
    for g, (p, f) in summarize(results).items():
        tp, tf = tp + p, tf + f
        print(f"  {g:<10} PASS {p:>4}   FAIL {f:>3}")
    print(f"  {'ИТОГО':<10} PASS {tp:>4}   FAIL {tf:>3}")
    print(f"Подробно: {OUT / 'parser_test_results.json'}")
    return 1 if tf else 0


def cmd_all(a):
    rc = cmd_grammar(a)
    print()
    return rc | cmd_test(a)


def main(argv=None):
    p = argparse.ArgumentParser(prog="python3 -m funny_parser",
                                description="LL(1)-парсер языка Funny (HW2)")
    sub = p.add_subparsers(dest="cmd", required=True)
    pa = sub.add_parser("parse", help="разобрать программу и вывести AST")
    pa.add_argument("file", help="файл с программой или '-' для stdin")
    pa.add_argument("--json", action="store_true", help="вывести AST в JSON (по умолчанию — текстовое дерево)")
    pa.add_argument("--partial", action="store_true", help="при ошибках всё равно вывести частичное AST")
    tk = sub.add_parser("tokens", help="показать токены с позициями (строка:столбец)")
    tk.add_argument("file")
    gr = sub.add_parser("grammar", help="проверить LL(1): FIRST/FOLLOW, таблица, конфликты")
    gr.add_argument("-v", "--verbose", action="store_true", help="напечатать FIRST/FOLLOW всех нетерминалов")
    te = sub.add_parser("test", help="прогнать тесты парсера")
    te.add_argument("-v", "--verbose", action="store_true", help="печатать все тесты, а не только упавшие")
    te.add_argument("--update", action="store_true", help="перезаписать эталоны *.ast / *.err (осторожно!)")
    al = sub.add_parser("all", help="grammar + test")
    al.add_argument("-v", "--verbose", action="store_true")
    al.add_argument("--update", action="store_true", help=argparse.SUPPRESS)
    a = p.parse_args(argv)
    return {"parse": cmd_parse, "tokens": cmd_tokens, "grammar": cmd_grammar,
            "test": cmd_test, "all": cmd_all}[a.cmd](a)
