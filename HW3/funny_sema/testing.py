import json
import random
import re
from pathlib import Path

from funny_parser import ast as A

from . import types as T
from .output import to_json, to_text
from .pipeline import check_program

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests" / "sema"


def _res(group, name, expected, actual, detail=None, ok=None):
    r = {"group": group, "name": name, "expected": expected, "actual": actual,
         "status": "PASS" if (expected == actual if ok is None else ok) else "FAIL"}
    if detail:
        r["detail"] = detail
    return r


def flags_of(text):
    first = text.split("\n", 1)[0]
    return {"allow_array_locals": "allow-array-locals" in first} if first.startswith("// sema:") else {}


def run_file(path):
    text = path.read_text(encoding="utf-8")
    return check_program(text, **flags_of(text))


def diag_lines(diags):
    return [f"{d.line}:{d.col}: [{d.phase}] {d.message}" for d in diags]


def run_positive(update=False):
    out = []
    for src in sorted((TESTS / "positive").glob("*.fn")):
        r = run_file(src)
        actual = to_text(r) if not r.diags else "ОШИБКИ:\n" + "\n".join(diag_lines(r.diags)) + "\n"
        snap = src.with_suffix(".out")
        if update and not r.diags:
            snap.write_text(actual, encoding="utf-8")
        expected = snap.read_text(encoding="utf-8") if snap.exists() else "<нет эталона>"
        out.append(_res("positive", src.name, expected, actual))
    return out


def run_negative(update=False):
    out = []
    for src in sorted((TESTS / "negative").glob("*.fn")):
        r = run_file(src)
        actual = diag_lines(r.diags)
        snap = src.with_suffix(".err")
        if update:
            snap.write_text("\n".join(actual) + "\n", encoding="utf-8")
        expected = snap.read_text(encoding="utf-8").splitlines() if snap.exists() else ["<нет эталона>"]
        out.append(_res("negative", src.name, expected, actual, ok=bool(actual) and expected == actual))
    return out


def run_diagnostics():
    out = []
    total = 0
    for src in sorted((TESTS / "negative").glob("*.fn")):
        r = run_file(src)
        lines = src.read_text(encoding="utf-8").split("\n")
        bad = [str(d) for d in r.diags
               if d.line < 1 or d.col < 1 or d.line > len(lines) + 1 or len(d.message) < 15]
        total += len(r.diags)
        out.append(_res("diagnostics", f"{src.name}: позиции и текст", [], bad))
    many = run_file(TESTS / "negative" / "20_many_errors.fn")
    out.append(_res("diagnostics", "20_many_errors.fn: не останавливается после первой ошибки",
                    True, len(many.diags) >= 8, detail=f"найдено ошибок: {len(many.diags)}"))
    return out


def run_unify():
    cases = []

    def case(name, fn):
        try:
            cases.append(_res("unify", name, True, bool(fn())))
        except Exception as e:  # noqa: BLE001
            cases.append(_res("unify", name, True, False, detail=repr(e)))

    case("int ~ int", lambda: T.unify(T.INT, T.INT))
    case("int !~ bool", lambda: not T.unify(T.INT, T.BOOL))
    case("int[] ~ int[] (структурно)", lambda: T.unify(T.Array(T.INT), T.Array(T.INT)))
    case("int[] !~ int", lambda: not T.unify(T.Array(T.INT), T.INT))

    def tvar_binds():
        v = T.TVar()
        return T.unify(v, T.INT, (3, 5)) and T.resolve(v) is T.INT and T.binding_origin(v) == (3, 5)
    case("?a ~ int связывает ?a := int и запоминает место", tvar_binds)

    def tvar_chain():
        a, b = T.TVar(), T.TVar()
        return T.unify(a, b) and T.unify(b, T.Array(T.INT), (7, 1)) and T.show(a) == "int[]" \
            and T.binding_origin(a) == (7, 1)
    case("?a ~ ?b, ?b ~ int[]  =>  ?a = int[]", tvar_chain)

    def tvar_conflict():
        v = T.TVar()
        return T.unify(v, T.INT) and not T.unify(v, T.Array(T.INT))
    case("?a := int, затем ?a ~ int[] — противоречие", tvar_conflict)

    def tvar_elem():
        v = T.TVar()
        return T.unify(T.Array(v), T.Array(T.INT)) and T.resolve(v) is T.INT
    case("?a[] ~ int[]  =>  ?a = int", tvar_elem)

    def occurs():
        v = T.TVar()
        return not T.unify(v, T.Array(v))
    case("occurs check: ?a !~ ?a[]", occurs)
    case("ERR совместим со всем", lambda: T.unify(T.ERR, T.INT) and T.unify(T.Array(T.INT), T.ERR))
    case("неизвестный тип показывается как ?", lambda: T.show(T.TVar()) == "?")
    return cases


def _expr_nodes(node, acc):
    if isinstance(node, A.Node):
        if not isinstance(node, (A.Module, A.Function, A.Formula, A.VarDef, A.Block, A.Assign,
                                 A.If, A.While, A.Assert, A.Assume)):
            acc.append(node)
        for v in vars(node).values():
            _expr_nodes(v, acc)
    elif isinstance(node, list):
        for x in node:
            _expr_nodes(x, acc)
    return acc


def run_json():
    out = []
    for src in sorted((TESTS / "positive").glob("*.fn")):
        r = run_file(src)
        data = json.loads(to_json(r))
        untyped = [f"{type(n).__name__}@{n.line}:{n.col}" for n in _expr_nodes(r.module, []) if not n.ty]
        ok = data["format"] == "funny-typed-ast/1" and not untyped and not data["diagnostics"]
        out.append(_res("json", f"{src.name}: тип у каждого выражения", True, ok,
                        detail=f"без типа: {untyped}" if untyped else None))
    return out


IDENT_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*\b")
KEYWORDS = {"function", "returns", "while", "if", "else", "assert", "assume", "invariant", "length",
            "requires", "ensures", "uses", "int", "true", "false", "not", "and", "or", "forall", "exists"}


def mutate(rng, text):
    for _ in range(rng.randint(1, 3)):
        idents = sorted({m.group() for m in IDENT_RE.finditer(text)} - KEYWORDS)
        op = rng.random()
        if op < 0.45 and idents:                        
            a = rng.choice(idents)
            b = rng.choice(idents + ["zz", "length"])
            spots = [m for m in re.finditer(rf"\b{a}\b", text)]
            m = rng.choice(spots)
            text = text[:m.start()] + b + text[m.end():]
        elif op < 0.65:                                  
            spots = [m for m in re.finditer(r"\bint\b(\[\])?", text)]
            if spots:
                m = rng.choice(spots)
                text = text[:m.start()] + ("int" if m.group(1) else "int[]") + text[m.end():]
        elif op < 0.8:                                  
            spots = [m for m in re.finditer(r"\b\d+\b", text)]
            if spots:
                m = rng.choice(spots)
                text = text[:m.start()] + rng.choice(["true", "99999999999", "x"]) + text[m.end():]
        else:                                            
            text = re.sub(r"(uses[^{]*?\b[A-Za-z][A-Za-z0-9]*)\s*:\s*int(\[\])?", r"\1", text, count=1)
    return text


def run_fuzz(samples=400, seed=2026):
    rng = random.Random(seed)
    progs = [p.read_text(encoding="utf-8") for p in sorted((TESTS / "positive").glob("*.fn"))]
    crash = nopos = None
    sem_errors = 0
    for _ in range(samples):
        text = mutate(rng, rng.choice(progs))
        try:
            r = check_program(text)
            sem_errors += any(d.phase in ("name", "type") for d in r.diags)
            if any(d.line < 1 or d.col < 1 for d in r.diags) and nopos is None:
                nopos = text
        except Exception as e:  
            crash = crash or f"{type(e).__name__}: {e} на входе {text!r}"
    return [
        _res("fuzz", "анализатор не падает", f"{samples} мутаций, seed={seed}", None, crash, ok=crash is None),
        _res("fuzz", "у всех ошибок есть позиция", None, nopos,
             detail=f"мутаций с семантическими ошибками: {sem_errors} из {samples}"),
    ]


def run_all(update=False):
    return (run_positive(update) + run_negative(update) + run_diagnostics() + run_unify()
            + run_json() + run_fuzz())


def summarize(results):
    groups = {}
    for r in results:
        g = groups.setdefault(r["group"], [0, 0])
        g[0 if r["status"] == "PASS" else 1] += 1
    return groups
