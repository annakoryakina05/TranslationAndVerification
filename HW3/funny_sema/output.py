"""Вывод аннотированного AST: текстовое дерево с типами и JSON."""
import json

from funny_parser import ast as A
from funny_parser.ast import to_dict

from .symbols import KIND_NAMES


def tsexpr(e):
    """S-выражение с типами: переменные и составные узлы помечены ':тип'."""
    if e is None:
        return "—"
    t = f":{e.ty}" if e.ty else ""
    if isinstance(e, A.IntLit):
        return str(e.value)
    if isinstance(e, A.BoolLit):
        return "true" if e.value else "false"
    if isinstance(e, A.Var):
        return f"{e.name}{t}"
    if isinstance(e, A.Index):
        return f"(index {e.array} {tsexpr(e.index)}){t}"
    if isinstance(e, A.ArrayStore):
        return f"(store {e.array} {tsexpr(e.index)} {tsexpr(e.value)}){t}"
    if isinstance(e, A.Call):
        return "(call " + " ".join([e.name] + [tsexpr(a) for a in e.args]) + f"){t}"
    if isinstance(e, A.FormulaRef):
        return "(formula " + " ".join([e.name] + [tsexpr(a) for a in e.args]) + f"){t}"
    if isinstance(e, A.Neg):
        return f"(neg {tsexpr(e.operand)}){t}"
    if isinstance(e, A.Not):
        return f"(not {tsexpr(e.operand)}){t}"
    if isinstance(e, (A.Binary, A.Compare, A.Logical)):
        return f"({e.op} {tsexpr(e.left)} {tsexpr(e.right)}){t}"
    if isinstance(e, A.Quantifier):
        return f"({e.quant} ({e.var.name} {e.var.type}) {tsexpr(e.body)}){t}"
    return "?"


def _sig(defs):
    return ", ".join(f"{v.name}: {v.type}" for v in defs)


def to_text(result):
    out = ["Module"]
    for d in result.module.decls:
        if d.name not in result.tables:          # объявление пропущено (дубликат имени)
            continue
        if isinstance(d, A.Formula):
            out.append(f"  Formula {d.name}({_sig(d.params)}) -> bool  @{d.line}:{d.col}")
        else:
            out.append(f"  Function {d.name}({_sig(d.params)}) -> ({_sig(d.returns)})  @{d.line}:{d.col}")
        out.append("    symbols:")
        for s in result.tables[d.name]:
            note = ""
            if s.inferred:
                o = s.node.inferred
                note = f"  (тип выведен{' из ' + o if o else ''})"
            out.append(f"      {s.name:<8} {KIND_NAMES[s.kind]:<22} {str(s.node.type or '?'):<6} "
                       f"@{s.line}:{s.col}{note}")
        if isinstance(d, A.Formula):
            out.append(f"    body: {tsexpr(d.body)}")
            continue
        out.append(f"    requires: {tsexpr(d.requires)}")
        out.append(f"    ensures:  {tsexpr(d.ensures)}")
        out.append("    body:")
        _stmt(d.body, 3, out)
    return "\n".join(out) + "\n"


def _stmt(s, depth, out):
    ind = "  " * depth
    pos = f"  @{s.line}:{s.col}"
    if isinstance(s, A.Block):
        out.append(f"{ind}Block{pos}")
        for st in s.stmts:
            _stmt(st, depth + 1, out)
    elif isinstance(s, A.Assign):
        out.append(f"{ind}Assign {', '.join(s.targets)} = {tsexpr(s.value)}{pos}")
    elif isinstance(s, A.If):
        out.append(f"{ind}If {tsexpr(s.cond)}{pos}")
        out.append(f"{ind}  then:")
        _stmt(s.then, depth + 2, out)
        if s.otherwise is not None:
            out.append(f"{ind}  else:")
            _stmt(s.otherwise, depth + 2, out)
    elif isinstance(s, A.While):
        out.append(f"{ind}While {tsexpr(s.cond)}{pos}")
        out.append(f"{ind}  invariant: {tsexpr(s.invariant)}")
        out.append(f"{ind}  body:")
        _stmt(s.body, depth + 2, out)
    elif isinstance(s, (A.Assert, A.Assume)):
        out.append(f"{ind}{type(s).__name__} {tsexpr(s.pred)}{pos}")


def to_json(result, indent=2):
    data = {
        "format": "funny-typed-ast/1",
        "module": to_dict(result.module),
        "symbols": {name: [s.row() for s in syms] for name, syms in result.tables.items()},
        "signatures": {n: {"kind": s.kind, "signature": str(s)}
                       for n, s in result.signatures.items()},
        "diagnostics": [{"line": d.line, "col": d.col, "phase": d.phase, "message": d.message}
                        for d in result.diags],
    }
    return json.dumps(data, ensure_ascii=False, indent=indent)
