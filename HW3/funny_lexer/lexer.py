"""Табличный лексер — runtime-часть для переиспользования в T0.

Зависит ТОЛЬКО от экспортированной таблицы (dfa.json),
а не от кода построения автомата. Файл можно копировать в проект как есть.

Алгоритм: maximal munch. Из текущей позиции идём по ДКА, запоминая последнюю
позицию, где состояние было принимающим. Остановка — при попадании в ловушку
или конце входа. Если принимающих позиций не было — ошибка ERROR на одном
символе (восстановление: пропуск этого символа).

Позиции (HW2): у каждого токена есть смещение pos (с 0) и line/col (с 1).
Перевод строки — '\n', '\r\n' или одиночный '\r' (как в спецификации Funny:
комментарий заканчивается на '\r' или '\n'); '\r\n' считается ОДНИМ переводом.
Столбец считается в символах, таб = 1 столбец.
"""
import json
from collections import namedtuple

Token = namedtuple("Token", "kind lexeme pos line col")
ERROR = "ERROR"


class TableLexer:
    def __init__(self, table):
        if table.get("format") != "funny-dfa/1":
            raise ValueError("неизвестный формат таблицы")
        self.start = table["start"]
        self.trap = table["trap"]
        self.class_of = table["char_classes"]
        self.trans = table["transitions"]
        self.other = table["alphabet"]["other_symbol"]
        self.accepting = {int(s): name for s, name in table["accepting"].items()}
        kinds = {t["name"]: t["kind"] for t in table["tokens"]}
        self.skip = {n for n, k in kinds.items() if k == "skip"}
        self.errors = {n for n, k in kinds.items() if k == "error"} | {ERROR}

    @classmethod
    def from_json(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def _cls(self, ch):
        o = ord(ch)
        return self.class_of[o if o < self.other else self.other]

    def match(self, text):
        """Имя токена, если вся строка — ровно один токен; иначе None."""
        s = self.start
        for ch in text:
            s = self.trans[s][self._cls(ch)]
            if s == self.trap:
                return None
        return self.accepting.get(s)

    def tokens(self, text, keep_skip=False):
        pos, n = 0, len(text)
        line, line_start = 1, 0
        trans, trap, acc = self.trans, self.trap, self.accepting
        while pos < n:
            state, i, last = self.start, pos, None
            while i < n:
                state = trans[state][self._cls(text[i])]
                if state == trap:
                    break
                i += 1
                if state in acc:
                    last = (i, acc[state])
            if last is None:
                end, kind = pos + 1, ERROR
            else:
                end, kind = last
            if keep_skip or kind not in self.skip:
                yield Token(kind, text[pos:end], pos, line, pos - line_start + 1)
            for j in range(pos, end):          # сдвигаем счётчик строк
                if _is_newline(text, j):
                    line, line_start = line + 1, j + 1
            pos = end

    def tokenize(self, text, keep_skip=False):
        return list(self.tokens(text, keep_skip))

    def is_error(self, tok):
        return tok.kind in self.errors


def _is_newline(text, j):
    ch = text[j]
    return ch == "\n" or (ch == "\r" and (j + 1 >= len(text) or text[j + 1] != "\n"))


def line_col(text, offset):
    """(строка, столбец) для смещения offset — по тем же правилам, что и у токенов."""
    line, line_start = 1, 0
    for j in range(min(offset, len(text))):
        if _is_newline(text, j):
            line, line_start = line + 1, j + 1
    return line, offset - line_start + 1
