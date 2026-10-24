"""CLI:  python3 -m funny_sema {check|test} ..."""
import argparse
import json
import sys
from pathlib import Path

from .output import to_json, to_text
from .pipeline import check_program
from .testing import run_all, summarize

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
PHASES = {"lexical": "лексическая", "syntax": "синтаксическая", "sort": "типы",
          "name": "имена", "type": "типы"}


def cmd_check(a):
    if a.file == "-":
        text, name = sys.stdin.read(), "<stdin>"
    else:
        try:
            text, name = Path(a.file).read_text(encoding="utf-8"), a.file
        except FileNotFoundError:
            print(f"Файл не найден: {a.file}", file=sys.stderr)
            return 2
    r = check_program(text, allow_array_locals=a.allow_array_locals)
    if a.json:
        print(to_json(r))
    else:
        for d in r.diags:
            print(f"{name}:{d.line}:{d.col}: ошибка ({PHASES.get(d.phase, d.phase)}): {d.message}",
                  file=sys.stderr)
        if r.diags and not r.tables:
            print("Есть синтаксические ошибки — семантический анализ не выполнялся.", file=sys.stderr)
        elif r.diags:
            print(f"Найдено ошибок: {len(r.diags)}", file=sys.stderr)
        if not r.diags or a.partial:
            print(to_text(r), end="")
        elif r.tables:
            print("Аннотированный AST не выведен (флаг --partial выведет его с ошибками).", file=sys.stderr)
    return 1 if r.diags else 0


def cmd_test(a):
    results = run_all(update=a.update)
    OUT.mkdir(exist_ok=True)
    (OUT / "sema_test_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for r in results:
        if r["status"] == "FAIL" or a.verbose:
            print(f"[{r['status']}] {r['group']:<12} {r['name']}")
            if r["status"] == "FAIL":
                print(f"   ожидалось: {r['expected']!r}\n   получено:  {r['actual']!r}")
                if "detail" in r:
                    print(f"   {r['detail']}")
    print()
    tp = tf = 0
    for g, (p, f) in summarize(results).items():
        tp, tf = tp + p, tf + f
        print(f"  {g:<12} PASS {p:>4}   FAIL {f:>3}")
    print(f"  {'ИТОГО':<12} PASS {tp:>4}   FAIL {tf:>3}")
    print(f"Подробно: {OUT / 'sema_test_results.json'}")
    return 1 if tf else 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="python3 -m funny_sema",
                                description="Семантический анализ и типы языка Funny (HW3)")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="проверить программу и вывести аннотированный AST")
    c.add_argument("file", help="файл с программой или '-' для stdin")
    c.add_argument("--json", action="store_true", help="вывести аннотированный AST, символы и ошибки в JSON")
    c.add_argument("--partial", action="store_true", help="при ошибках всё равно вывести аннотированный AST")
    c.add_argument("--allow-array-locals", action="store_true",
                   help="разрешить локальные переменные типа int[] (расширение спецификации)")
    t = sub.add_parser("test", help="прогнать тесты семантического анализа")
    t.add_argument("-v", "--verbose", action="store_true", help="печатать все тесты")
    t.add_argument("--update", action="store_true", help="перезаписать эталоны *.out / *.err (осторожно!)")
    a = p.parse_args(argv)
    return {"check": cmd_check, "test": cmd_test}[a.cmd](a)
