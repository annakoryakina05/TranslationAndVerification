from dataclasses import dataclass, field
from typing import Optional

from .types import Type, show

KIND_NAMES = {"param": "параметр", "return": "возвращаемое значение",
              "local": "локальная переменная", "bound": "переменная квантора",
              "function": "функция", "formula": "формула", "builtin": "встроенная функция"}


@dataclass
class Symbol:
    name: str
    kind: str                     
    type: Type
    line: int
    col: int
    declared_type: Optional[str] = None  
    node: object = field(default=None, repr=False)

    @property
    def inferred(self):
        return self.declared_type is None and self.kind == "local"

    def describe(self):
        return f"{KIND_NAMES[self.kind]} '{self.name}' ({self.line}:{self.col})"

    def row(self):
        return {"name": self.name, "kind": self.kind, "type": show(self.type),
                "line": self.line, "col": self.col, "inferred": self.inferred}


class Scope:

    def __init__(self, kind, parent=None):
        self.kind = kind             
        self.parent = parent
        self.symbols = {}

    def declare(self, sym):
        old = self.symbols.get(sym.name)
        if old is not None:
            return old
        self.symbols[sym.name] = sym
        return None

    def lookup(self, name):
        s = self
        while s is not None:
            if name in s.symbols:
                return s.symbols[name]
            s = s.parent
        return None

    def visible_names(self):
        names, s = set(), self
        while s is not None:
            names |= set(s.symbols)
            s = s.parent
        return names
