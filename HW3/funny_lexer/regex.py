ASCII_SIZE = 128
OTHER = 128              # один символ-представитель для ЛЮБОГО non-ASCII кода
ALPHABET_SIZE = 129      # 0..127 + OTHER
ASCII_ALL = frozenset(range(ASCII_SIZE))

DIGITS = frozenset(range(ord("0"), ord("9") + 1))
LETTERS = frozenset(list(range(ord("A"), ord("Z") + 1)) + list(range(ord("a"), ord("z") + 1)))
WORD = DIGITS | LETTERS | {ord("_")}
SPACE = frozenset(map(ord, " \t\r\n\f\v"))

_SIMPLE_ESCAPES = {"n": 10, "t": 9, "r": 13, "f": 12, "v": 11, "0": 0}
_CLASS_ESCAPES = {"d": DIGITS, "w": WORD, "s": SPACE}


class RegexError(ValueError):
    pass


def to_symbols(text):
    """Строка → список символов алфавита (non-ASCII → OTHER)."""
    return [o if o < ASCII_SIZE else OTHER for o in map(ord, text)]


def parse_regex(text):
    return _Parser(text).parse()


def nullable(node):
    """Распознаёт ли выражение пустую строку."""
    k = node[0]
    if k in ("eps", "star", "opt"):
        return True
    if k == "set":
        return False
    if k == "cat":
        return nullable(node[1]) and nullable(node[2])
    if k == "alt":
        return nullable(node[1]) or nullable(node[2])
    if k == "plus":
        return nullable(node[1])
    raise ValueError(k)


def _concat(parts):
    if not parts:
        return ("eps",)
    node = parts[0]
    for p in parts[1:]:
        node = ("cat", node, p)
    return node


class _Parser:
    def __init__(self, text):
        self.s = text
        self.i = 0

    def peek(self):
        return self.s[self.i] if self.i < len(self.s) else None

    def error(self, msg):
        return RegexError(f"{msg} (позиция {self.i} в {self.s!r})")

    @staticmethod
    def _code(ch):
        o = ord(ch)
        if o >= ASCII_SIZE:
            raise RegexError(f"символ {ch!r} вне алфавита ASCII")
        return o

    # alt := concat ('|' concat)*
    def parse(self):
        node = self._alt()
        if self.i != len(self.s):
            raise self.error(f"неожиданный символ {self.peek()!r}")
        return node

    def _alt(self):
        node = self._concat()
        while self.peek() == "|":
            self.i += 1
            node = ("alt", node, self._concat())
        return node

    # concat := repeat*
    def _concat(self):
        items = []
        while self.peek() not in (None, "|", ")"):
            items.append(self._repeat())
        return _concat(items)

    # repeat := atom ('*' | '+' | '?')*
    def _repeat(self):
        node = self._atom()
        ops = {"*": "star", "+": "plus", "?": "opt"}
        while self.peek() in ops:
            node = (ops[self.peek()], node)
            self.i += 1
        return node

    def _atom(self):
        c = self.peek()
        if c == "(":
            self.i += 1
            node = self._alt()
            if self.peek() != ")":
                raise self.error("ожидалась ')'")
            self.i += 1
            return node
        if c == "[":
            return self._char_class()
        if c == '"':
            return self._literal()
        if c == ".":
            self.i += 1
            return ("set", ASCII_ALL - {10})
        if c == "\\":
            return ("set", self._escape())
        if c in ("*", "+", "?"):
            raise self.error(f"нечего повторять перед {c!r}")
        self.i += 1
        return ("set", frozenset({self._code(c)}))

    def _escape(self):
        self.i += 1  # '\'
        c = self.peek()
        if c is None:
            raise self.error("одиночный '\\' в конце")
        self.i += 1
        if c in _SIMPLE_ESCAPES:
            return frozenset({_SIMPLE_ESCAPES[c]})
        if c in _CLASS_ESCAPES:
            return _CLASS_ESCAPES[c]
        if c == "x":
            h = self.s[self.i:self.i + 2]
            if len(h) != 2 or any(ch not in "0123456789abcdefABCDEF" for ch in h):
                raise self.error("ожидалось \\xHH")
            self.i += 2
            v = int(h, 16)
            if v >= ASCII_SIZE:
                raise self.error("\\xHH вне ASCII")
            return frozenset({v})
        if c.isalnum():
            raise self.error(f"неизвестная escape-последовательность \\{c}")
        return frozenset({self._code(c)})

    def _class_item(self):
        c = self.peek()
        if c == "\\":
            return self._escape()
        self.i += 1
        return frozenset({self._code(c)})

    def _char_class(self):
        self.i += 1  # '['
        negate = False
        if self.peek() == "^":
            negate = True
            self.i += 1
        members = set()
        first = True
        while True:
            c = self.peek()
            if c is None:
                raise self.error("незакрытый '['")
            if c == "]" and not first:
                self.i += 1
                break
            first = False
            lo = self._class_item()
            nxt = self.s[self.i + 1] if self.i + 1 < len(self.s) else None
            if self.peek() == "-" and nxt not in (None, "]"):
                self.i += 1
                hi = self._class_item()
                if len(lo) != 1 or len(hi) != 1:
                    raise self.error("границы диапазона должны быть одиночными символами")
                a, b = next(iter(lo)), next(iter(hi))
                if a > b:
                    raise self.error("перевёрнутый диапазон")
                members.update(range(a, b + 1))
            else:
                members.update(lo)
        result = (ASCII_ALL - members) if negate else frozenset(members)
        if not result:
            raise self.error("пустой класс символов")
        return ("set", frozenset(result))

    def _literal(self):
        self.i += 1  # '"'
        parts = []
        while True:
            c = self.peek()
            if c is None:
                raise self.error("незакрытая строка")
            if c == '"':
                self.i += 1
                break
            if c == "\\":
                parts.append(("set", self._escape()))
            else:
                self.i += 1
                parts.append(("set", frozenset({self._code(c)})))
        return _concat(parts)
