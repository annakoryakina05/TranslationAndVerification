"""Узлы AST языка Funny и их вывод (текстовое дерево и JSON).

У каждого узла есть line/col — позиция его первого токена (с 1).
Формат JSON:  {"node": "<Класс>", "line": L, "col": C, <поля>...}
Подробное описание — AST.md.
"""
import json
from dataclasses import dataclass, field, fields
from typing import List, Optional


@dataclass
class Node:
    line: int = field(default=0, kw_only=True)
    col: int = field(default=0, kw_only=True)
    # --- аннотации семантического анализа (HW3, funny_sema); до анализа = None ---
    ty: Optional[str] = field(default=None, kw_only=True)    # тип выражения: int, bool, int[], ...
    ref: Optional[str] = field(default=None, kw_only=True)   # к чему относится имя: param/return/local/bound/function/formula/builtin


ANNOTATION_FIELDS = ("ty", "ref", "inferred")


# ------------------------------------------------------------- объявления
@dataclass
class VarDef(Node):
    name: str
    type: Optional[str]            # "int" | "int[]" | None (тип не указан — только в uses, HW3)
    inferred: Optional[str] = field(default=None, kw_only=True)  # HW3: "строка:столбец", откуда выведен тип


@dataclass
class Function(Node):
    name: str
    params: List[VarDef]
    requires: Optional[Node]
    returns: List[VarDef]
    ensures: Optional[Node]
    uses: List[VarDef]
    body: Node


@dataclass
class Formula(Node):
    name: str
    params: List[VarDef]
    body: Node


@dataclass
class Module(Node):
    decls: list


# ---------------------------------------------------------------- операторы
@dataclass
class Block(Node):
    stmts: list


@dataclass
class Assign(Node):
    targets: List[str]             # одно имя или несколько (кортежное присваивание)
    value: Node


@dataclass
class If(Node):
    cond: Node
    then: Node
    otherwise: Optional[Node]


@dataclass
class While(Node):
    cond: Node
    invariant: Optional[Node]
    body: Node


@dataclass
class Assert(Node):
    pred: Node


@dataclass
class Assume(Node):
    pred: Node


# --------------------------------------------------------------- выражения
@dataclass
class IntLit(Node):
    value: int


@dataclass
class BoolLit(Node):
    value: bool


@dataclass
class Var(Node):
    name: str


@dataclass
class Index(Node):                 # чтение a[i]
    array: str
    index: Node


@dataclass
class ArrayStore(Node):            # a[i] = v  ==>  a = store(a, i, v)
    array: str
    index: Node
    value: Node


@dataclass
class Call(Node):                  # вызов функции (в т.ч. length)
    name: str
    args: list


@dataclass
class FormulaRef(Node):            # ссылка на формулу (только в предикатах)
    name: str
    args: list


@dataclass
class Neg(Node):                   # унарный минус
    operand: Node


@dataclass
class Binary(Node):                # + - * /
    op: str
    left: Node
    right: Node


@dataclass
class Compare(Node):               # == != < <= > >=
    op: str
    left: Node
    right: Node


@dataclass
class Not(Node):
    operand: Node


@dataclass
class Logical(Node):               # and, or, ->
    op: str
    left: Node
    right: Node


@dataclass
class Quantifier(Node):
    quant: str                     # "forall" | "exists"
    var: VarDef
    body: Node


BOOL_NODES = (BoolLit, Compare, Not, Logical, Quantifier, FormulaRef)


# ------------------------------------------------------------------- JSON
def to_dict(node):
    if isinstance(node, Node):
        d = {"node": type(node).__name__, "line": node.line, "col": node.col}
        for f in fields(node):
            if f.name in ("line", "col", "ty"):
                continue
            v = getattr(node, f.name)
            if f.name in ANNOTATION_FIELDS and v is None:
                continue                       # аннотации пишем, только если они есть
            d[f.name] = to_dict(v)
        if node.ty is not None:
            d["type"] = node.ty                # тип выражения (HW3)
        return d
    if isinstance(node, list):
        return [to_dict(x) for x in node]
    return node


def to_json(node, indent=2):
    return json.dumps(to_dict(node), ensure_ascii=False, indent=indent)


# ------------------------------------------- выражение как S-выражение
def sexpr(e):
    if e is None:
        return "—"
    if isinstance(e, IntLit):
        return str(e.value)
    if isinstance(e, BoolLit):
        return "true" if e.value else "false"
    if isinstance(e, Var):
        return e.name
    if isinstance(e, Index):
        return f"(index {e.array} {sexpr(e.index)})"
    if isinstance(e, ArrayStore):
        return f"(store {e.array} {sexpr(e.index)} {sexpr(e.value)})"
    if isinstance(e, Call):
        return "(call " + " ".join([e.name] + [sexpr(a) for a in e.args]) + ")"
    if isinstance(e, FormulaRef):
        return "(formula " + " ".join([e.name] + [sexpr(a) for a in e.args]) + ")"
    if isinstance(e, Neg):
        return f"(neg {sexpr(e.operand)})"
    if isinstance(e, Not):
        return f"(not {sexpr(e.operand)})"
    if isinstance(e, (Binary, Compare, Logical)):
        return f"({e.op} {sexpr(e.left)} {sexpr(e.right)})"
    if isinstance(e, Quantifier):
        return f"({e.quant} ({e.var.name} {e.var.type}) {sexpr(e.body)})"
    raise TypeError(type(e).__name__)


# ----------------------------------------------- текстовое дерево
def _vars(vs):
    return ", ".join(f"{v.name}: {v.type or '?'}" for v in vs) if vs else "—"


def _pos(n):
    return f"  @{n.line}:{n.col}"


def to_text(node):
    out = []
    _emit(node, 0, out)
    return "\n".join(out) + "\n"


def _emit(n, d, out):
    ind = "  " * d
    if isinstance(n, Module):
        out.append(ind + "Module")
        for x in n.decls:
            _emit(x, d + 1, out)
    elif isinstance(n, Function):
        out.append(f"{ind}Function {n.name}{_pos(n)}")
        out.append(f"{ind}  params:   {_vars(n.params)}")
        out.append(f"{ind}  requires: {sexpr(n.requires)}")
        out.append(f"{ind}  returns:  {_vars(n.returns)}")
        out.append(f"{ind}  ensures:  {sexpr(n.ensures)}")
        out.append(f"{ind}  uses:     {_vars(n.uses)}")
        out.append(f"{ind}  body:")
        _emit(n.body, d + 2, out)
    elif isinstance(n, Formula):
        out.append(f"{ind}Formula {n.name}{_pos(n)}")
        out.append(f"{ind}  params: {_vars(n.params)}")
        out.append(f"{ind}  body:   {sexpr(n.body)}")
    elif isinstance(n, Block):
        out.append(f"{ind}Block{_pos(n)}")
        for s in n.stmts:
            _emit(s, d + 1, out)
    elif isinstance(n, Assign):
        out.append(f"{ind}Assign {', '.join(n.targets)} = {sexpr(n.value)}{_pos(n)}")
    elif isinstance(n, If):
        out.append(f"{ind}If {sexpr(n.cond)}{_pos(n)}")
        out.append(f"{ind}  then:")
        _emit(n.then, d + 2, out)
        if n.otherwise is not None:
            out.append(f"{ind}  else:")
            _emit(n.otherwise, d + 2, out)
    elif isinstance(n, While):
        out.append(f"{ind}While {sexpr(n.cond)}{_pos(n)}")
        out.append(f"{ind}  invariant: {sexpr(n.invariant)}")
        out.append(f"{ind}  body:")
        _emit(n.body, d + 2, out)
    elif isinstance(n, Assert):
        out.append(f"{ind}Assert {sexpr(n.pred)}{_pos(n)}")
    elif isinstance(n, Assume):
        out.append(f"{ind}Assume {sexpr(n.pred)}{_pos(n)}")
    else:
        out.append(ind + sexpr(n))
