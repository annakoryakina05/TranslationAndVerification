import json
import random
from pathlib import Path

from funny_lexer.spec import load_spec

from . import ll1
from .ast import sexpr, to_json, to_text
from .parser import InternalLoopError, parse_expression, parse_program
from .tokens import get_lexer, tokenize

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests" / "parser"


def _res(group, name, inp, expected, actual, detail=None):
    r = {"group": group, "name": name, "input": inp, "expected": expected, "actual": actual,
         "status": "PASS" if expected == actual else "FAIL"}
    if detail:
        r["detail"] = detail
    return r


def diag_lines(diags):
    return [str(d) for d in diags]


def run_positive(update=False):
    out = []
    for src in sorted((TESTS / "positive").glob("*.fn")):
        text = src.read_text(encoding="utf-8")
        module, diags = parse_program(text)
        actual = to_text(module) if not diags else "ОШИБКИ:\n" + "\n".join(diag_lines(diags)) + "\n"
        snap = src.with_suffix(".ast")
        if update and not diags:
            snap.write_text(actual, encoding="utf-8")
        expected = snap.read_text(encoding="utf-8") if snap.exists() else "<нет эталона>"
        out.append(_res("positive", src.name, str(src.relative_to(ROOT)), expected, actual))
    return out


def run_negative(update=False):
    out = []
    for src in sorted((TESTS / "negative").glob("*.fn")):
        text = src.read_text(encoding="utf-8")
        _, diags = parse_program(text)
        actual = diag_lines(diags)
        snap = src.with_suffix(".err")
        if update:
            snap.write_text("\n".join(actual) + "\n", encoding="utf-8")
        expected = snap.read_text(encoding="utf-8").splitlines() if snap.exists() else ["<нет эталона>"]
        r = _res("negative", src.name, str(src.relative_to(ROOT)), expected, actual)
        if not actual:
            r["status"] = "FAIL"
            r["detail"] = "ожидалась хотя бы одна ошибка"
        out.append(r)
    return out


def run_expr_cases():
    cases = json.loads((TESTS / "expr_cases.json").read_text(encoding="utf-8"))["cases"]
    out = []
    for c in cases:
        node, diags = parse_expression(c["input"], c.get("mode", "expr"))
        if diags:
            actual = {"error": diag_lines(diags)}
        else:
            actual = sexpr(node)
        exp = c["expect"]
        if isinstance(exp, dict):            
            ok = "error" in actual and exp["error"] in actual["error"][0]
            r = _res("expr", c["input"], c["input"], exp, actual)
            r["status"] = "PASS" if ok else "FAIL"
        else:
            r = _res("expr", c["input"], c["input"], exp, actual)
        r["mode"] = c.get("mode", "expr")
        out.append(r)
    return out


POSITION_CASES = [
    ("x", [("IDENT", 1, 1), ("EOF", 1, 2)]),
    ("  x\n y", [("IDENT", 1, 3), ("IDENT", 2, 2), ("EOF", 2, 3)]),
    ("a\r\nb", [("IDENT", 1, 1), ("IDENT", 2, 1), ("EOF", 2, 2)]),
    ("a\rb", [("IDENT", 1, 1), ("IDENT", 2, 1), ("EOF", 2, 2)]),
    ("a\n\n\nb", [("IDENT", 1, 1), ("IDENT", 4, 1), ("EOF", 4, 2)]),
    ("\tif(x)", [("KW_IF", 1, 2), ("LPAREN", 1, 4), ("IDENT", 1, 5), ("RPAREN", 1, 6), ("EOF", 1, 7)]),
    ("x // c\ny", [("IDENT", 1, 1), ("IDENT", 2, 1), ("EOF", 2, 2)]),
    ("x // c\r\n  y", [("IDENT", 1, 1), ("IDENT", 2, 3), ("EOF", 2, 4)]),
    ("", [("EOF", 1, 1)]),
]


def run_positions():
    out = []
    for text, exp in POSITION_CASES:
        toks = tokenize(text, [])
        act = [(t.kind, t.line, t.col) for t in toks]
        out.append(_res("positions", repr(text), text, [list(e) for e in exp], [list(a) for a in act]))
    return out


def run_grammar():
    g = ll1.load_grammar()
    spec = load_spec()
    an = ll1.analyze(g, {t.name for t in spec})
    used = set(g.terminals)
    need = {t.name for t in spec if t.kind == "token"}
    conf = sorted((a, t) for a, t, _ in an.conflicts)
    return [
        _res("grammar", "конфликты LL(1) только ожидаемые", "", sorted(ll1.EXPECTED_CONFLICTS), conf),
        _res("grammar", "терминалы = токены лексера", "", [], an.unknown_terminals),
        _res("grammar", "все токены лексера используются", "", [], sorted(need - used)),
        _res("grammar", "нет недостижимых нетерминалов", "", [], an.unreachable),
    ]


def run_json():
    out = []
    for src in sorted((TESTS / "positive").glob("*.fn")):
        module, _ = parse_program(src.read_text(encoding="utf-8"))
        data = json.loads(to_json(module))
        ok = data.get("node") == "Module" and len(data["decls"]) == len(module.decls)
        out.append(_res("json", src.name, src.name, True, ok))
    return out


FUZZ_POOL = ["(", ")", "{", "}", "[", "]", ";", ",", "=", "==", "if", "else", "while", "returns",
             "requires", "x", "1", "+", "-", "*", "and", "not", "forall", "|", ":", "int", "=>", "->", "é"]


def mutate(rng, lexemes):
    toks = list(lexemes)
    for _ in range(rng.randint(1, 4)):
        op = rng.random()
        if not toks or op < 0.3:
            toks.insert(rng.randint(0, len(toks)), rng.choice(FUZZ_POOL))
        elif op < 0.6:
            del toks[rng.randrange(len(toks))]
        elif op < 0.8:
            i = rng.randrange(len(toks))
            toks.insert(i, toks[i])
        else:
            i = rng.randrange(len(toks))
            j = rng.randrange(len(toks))
            toks[i], toks[j] = toks[j], toks[i]
    return " ".join(toks)


def run_fuzz(samples=600, seed=2026):
    rng = random.Random(seed)
    lexer = get_lexer()
    progs = [[t.lexeme for t in lexer.tokens(p.read_text(encoding="utf-8"))]
             for p in sorted((TESTS / "positive").glob("*.fn"))]
    crash = loop = None
    with_errors = 0
    for _ in range(samples):
        text = mutate(rng, rng.choice(progs))
        try:
            _, diags = parse_program(text)
            with_errors += bool(diags)
        except InternalLoopError:
            loop = loop or text
        except Exception as e:         
            crash = crash or f"{type(e).__name__}: {e} на входе {text!r}"
    return [
        _res("fuzz", "парсер не падает", f"{samples} мутаций, seed={seed}", None, crash),
        _res("fuzz", "парсер не зацикливается", f"{samples} мутаций, seed={seed}", None, loop,
             detail=f"с ошибками: {with_errors} из {samples}"),
    ]


def run_all(update=False):
    return (run_positive(update) + run_negative(update) + run_expr_cases() + run_positions()
            + run_grammar() + run_json() + run_fuzz())


def summarize(results):
    groups = {}
    for r in results:
        g = groups.setdefault(r["group"], [0, 0])
        g[0 if r["status"] == "PASS" else 1] += 1
    return groups
