"""Типы языка Funny и унификация.

Типы значений:
    int        32-битное целое
    int[]      массив int            (Array(INT); тип элемента — тоже тип, unify структурный)
    bool       логическое значение   (условия, предикаты; переменных типа bool в Funny нет)
Типы «вызываемых» имён (сигнатуры):
    function   (типы параметров) -> (типы результатов)
    formula    (типы параметров) -> bool        — только в предикатах
    builtin    length: (int[]) -> (int)
Служебные:
    TVar       переменная типа — тип ещё неизвестен (локальная без аннотации, бонус)
    ERR        «тип ошибки»: подставляется после уже сообщённой ошибки и совместим
               со всем — так одна ошибка не порождает лавину следующих.

Унификация unify(a, b): делает два типа равными, связывая переменные типов.
Хранение — union-find: TVar.ref указывает на тип, которым переменная стала.
"""
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
    """Переменная типа. origin — (строка, столбец), где ей впервые был назначен тип."""

    def __init__(self, name=None):
        self.id = next(_ids)
        self.ref: Optional[Type] = None
        self.origin: Optional[Tuple[int, int]] = None
        self.name = name

    def __repr__(self):
        return f"?{self.name or self.id}"


def resolve(t):
    """Пройти по цепочке связанных переменных типа до конечного типа."""
    while isinstance(t, TVar) and t.ref is not None:
        t = t.ref
    return t


def deep(t):
    """Полностью раскрыть тип (в т.ч. внутри массива)."""
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
    """True, если типы удалось сделать равными; where=(строка, столбец) запоминается
    как место, где переменная типа впервые получила тип (для сообщений)."""
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
    """Где переменная типа (или цепочка связанных) получила конкретный тип."""
    last = None
    while isinstance(t, TVar):
        if t.origin is not None:
            last = t.origin
        if t.ref is None:
            break
        t = t.ref
    return last


def from_annotation(s):
    """'int' | 'int[]' | None -> Type."""
    if s is None:
        return TVar()
    return Array(INT) if s == "int[]" else INT


@dataclass
class Signature:
    """Сигнатура функции, формулы или встроенной функции."""
    name: str
    kind: str                         # function | formula | builtin
    params: List[Type]
    returns: List[Type] = field(default_factory=list)   # у формулы пусто (результат bool)
    line: int = 0
    col: int = 0

    def __str__(self):
        ps = ", ".join(show(p) for p in self.params)
        if self.kind == "formula":
            return f"formula ({ps}) -> bool"
        rs = ", ".join(show(r) for r in self.returns)
        return f"({ps}) -> ({rs})"
