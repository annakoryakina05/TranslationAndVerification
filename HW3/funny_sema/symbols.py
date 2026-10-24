"""Таблицы символов и области видимости.

Области видимости Funny (снизу вверх):
  модуль      функции, формулы и встроенная length — одно пространство имён;
              порядок объявления неважен (можно вызывать функцию, объявленную ниже, и рекурсию)
  функция     параметры, возвращаемые значения, локальные переменные (uses);
              блоки { } новых областей НЕ создают — все переменные объявлены в заголовке
  квантор     переменная forall/exists — видна только внутри своего квантора

Внутри функции видимость зависит от того, ГДЕ стоит выражение (порядок частей
заголовка задаёт области — спецификация, «order the clauses ... scopes are obvious»):
  requires            только параметры
  ensures             параметры и возвращаемые значения
  тело, invariant     параметры, возвращаемые значения и локальные
Переменные и функции живут в разных пространствах имён: x — переменная, x(...) — вызов.
"""
from dataclasses import dataclass, field
from typing import Optional

from .types import Type, show

KIND_NAMES = {"param": "параметр", "return": "возвращаемое значение",
              "local": "локальная переменная", "bound": "переменная квантора",
              "function": "функция", "formula": "формула", "builtin": "встроенная функция"}


@dataclass
class Symbol:
    name: str
    kind: str                     # param | return | local | bound
    type: Type
    line: int
    col: int
    declared_type: Optional[str] = None   # как записано в программе (None — без аннотации)
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
    """Область видимости: словарь имя -> Symbol + ссылка на внешнюю область."""

    def __init__(self, kind, parent=None):
        self.kind = kind              # function | quantifier
        self.parent = parent
        self.symbols = {}

    def declare(self, sym):
        """Объявить имя. Если в ЭТОЙ области оно уже есть — вернуть старый символ (ошибка)."""
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
