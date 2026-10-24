import itertools
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


class Type:
    pass


class Prim(Type):
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


INT = Prim("int")
BOOL = Prim("bool")


class Array(Type):
    def __init__(self, elem):
        self.elem = elem

    def __repr__(self):
        return f"{show(self.elem)}[]"


class ErrorType(Type):
    def __repr__(self):
        return "<ошибка>"


ERR = ErrorType()
_ids = itertools.count(1)


class TVar(Type):

    def __init__(self, name=None):
        self.id = next(_ids)
        self.ref: Optional[Type] = None
        self.origin: Optional[Tuple[int, int]] = None
        self.name = name

    def __repr__(self):
        return f"?{self.name or self.id}"


def resolve(t):
    while isinstance(t, TVar) and t.ref is not None:
        t = t.ref
    return t


def deep(t):
    t = resolve(t)
    if isinstance(t, Array):
        return Array(deep(t.elem))
    return t


def show(t):
    t = deep(t)
    if isinstance(t, Array):
        return f"{show(t.elem)}[]"
    if isinstance(t, TVar):
        return "?"
    return repr(t)


def occurs(v, t):
    t = resolve(t)
    if t is v:
        return True
    return isinstance(t, Array) and occurs(v, t.elem)


def unify(a, b, where=None):
    a, b = resolve(a), resolve(b)
    if a is b:
        return True
    if a is ERR or b is ERR:
        return True
    if isinstance(a, TVar):
        return _bind(a, b, where)
    if isinstance(b, TVar):
        return _bind(b, a, where)
    if isinstance(a, Prim) and isinstance(b, Prim):
        return a.name == b.name
    if isinstance(a, Array) and isinstance(b, Array):
        return unify(a.elem, b.elem, where)
    return False


def _bind(v, t, where):
    if occurs(v, t):
        return False
    v.ref = t
    if isinstance(t, TVar):
        if t.origin is None:
            t.origin = v.origin
    elif v.origin is None:
        v.origin = where
    return True


def binding_origin(t):
    last = None
    while isinstance(t, TVar):
        if t.origin is not None:
            last = t.origin
        if t.ref is None:
            break
        t = t.ref
    return last


def from_annotation(s):
    if s is None:
        return TVar()
    return Array(INT) if s == "int[]" else INT


@dataclass
class Signature:
    name: str
    kind: str                         
    params: List[Type]
    returns: List[Type] = field(default_factory=list)  
    line: int = 0
    col: int = 0

    def __str__(self):
        ps = ", ".join(show(p) for p in self.params)
        if self.kind == "formula":
            return f"formula ({ps}) -> bool"
        rs = ", ".join(show(r) for r in self.returns)
        return f"({ps}) -> ({rs})"
