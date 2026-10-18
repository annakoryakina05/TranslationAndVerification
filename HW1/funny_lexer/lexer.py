import json
from collections import namedtuple

Token = namedtuple("Token", "kind lexeme pos")
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
        s = self.start
        for ch in text:
            s = self.trans[s][self._cls(ch)]
            if s == self.trap:
                return None
        return self.accepting.get(s)

    def tokens(self, text, keep_skip=False):
        pos, n = 0, len(text)
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
                yield Token(ERROR, text[pos], pos)
                pos += 1
                continue
            end, kind = last
            if keep_skip or kind not in self.skip:
                yield Token(kind, text[pos:end], pos)
            pos = end

    def tokenize(self, text, keep_skip=False):
        return list(self.tokens(text, keep_skip))

    def is_error(self, tok):
        return tok.kind in self.errors
