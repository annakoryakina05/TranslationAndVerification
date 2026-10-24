from dataclasses import dataclass
from pathlib import Path

from funny_lexer.lexer import TableLexer, Token, line_col

ROOT = Path(__file__).resolve().parent.parent
TABLE_PATH = ROOT / "out" / "dfa.json"
SPEC_PATH = ROOT / "spec" / "funny.tokens"

_lexer = None


@dataclass
class Diagnostic:
    line: int
    col: int
    message: str
    phase: str = "syntax"          # lexical | syntax | sort

    def __str__(self):
        return f"{self.line}:{self.col}: {self.message}"


def get_lexer():
    """Табличный лексер. Берёт out/dfa.json; если его нет или спецификация новее — пересобирает."""
    global _lexer
    if _lexer is None:
        stale = (not TABLE_PATH.exists()
                 or SPEC_PATH.stat().st_mtime > TABLE_PATH.stat().st_mtime)
        if stale:
            from funny_lexer.export import write_all
            from funny_lexer.pipeline import build
            write_all(build(SPEC_PATH), TABLE_PATH.parent)
        _lexer = TableLexer.from_json(TABLE_PATH)
    return _lexer


def describe_char(ch):
    if ch.isprintable() and not ch.isspace():
        return f"'{ch}'"
    return f"U+{ord(ch):04X}"


def tokenize(text, diags):
    """Токены без WS/COMMENT + EOF в конце; лексические ошибки пишутся в diags.

    Восстановление после лексических ошибок:
      * ERROR-символы выбрасываются; подряд идущие (через пробелы, в одной строке)
        дают ОДНО сообщение;
      * non-ASCII внутри комментария обрывает комментарий (алфавит — ASCII, HW1),
        поэтому остаток такой строки пропускается целиком — иначе слова
        комментария превратились бы в лавину синтаксических ошибок;
      * BAD_INT (ведущий ноль) сообщается и превращается в INT.
    """
    out, raw = [], list(get_lexer().tokens(text, keep_skip=True))
    i = 0
    while i < len(raw):
        t = raw[i]
        if t.kind == "ERROR":
            prev = raw[i - 1] if i else None
            if prev is not None and prev.kind == "COMMENT" and prev.pos + len(prev.lexeme) == t.pos:
                diags.append(Diagnostic(t.line, t.col,
                             f"недопустимый символ {describe_char(t.lexeme)} в комментарии "
                             "(допустимы только ASCII-символы); остаток строки пропущен", "lexical"))
                while i < len(raw) and raw[i].line == t.line and "\n" not in raw[i].lexeme \
                        and "\r" not in raw[i].lexeme:
                    i += 1
                continue
            j, last = i, i                      # склеиваем серию ошибок в одной строке
            while j + 1 < len(raw) and raw[j + 1].line == t.line and raw[j + 1].kind in ("ERROR", "WS"):
                j += 1
                if raw[j].kind == "ERROR":
                    last = j
            end = raw[last].pos + len(raw[last].lexeme)
            if last == i:
                msg = f"недопустимый символ {describe_char(t.lexeme)}"
            else:
                msg = f"недопустимые символы '{text[t.pos:end]}'"
            diags.append(Diagnostic(t.line, t.col, msg, "lexical"))
            i = last + 1
            continue
        if t.kind == "BAD_INT":
            diags.append(Diagnostic(t.line, t.col, f"число с ведущим нулём '{t.lexeme}'", "lexical"))
            t = t._replace(kind="INT")
        if t.kind not in ("WS", "COMMENT"):
            out.append(t)
        i += 1
    line, col = line_col(text, len(text))
    out.append(Token("EOF", "", len(text), line, col))
    return out
