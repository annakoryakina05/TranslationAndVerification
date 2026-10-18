import re
from dataclasses import dataclass, field
from pathlib import Path

from .regex import RegexError, nullable, parse_regex

DEFAULT_SPEC = Path(__file__).resolve().parent.parent / "spec" / "funny.tokens"
RESERVED = {"ERROR", "EOF"}
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SpecError(ValueError):
    pass


@dataclass
class TokenSpec:
    name: str
    regex: str
    kind: str          # "token" | "skip" | "error"
    priority: int      # индекс в файле; меньше = важнее
    ast: tuple = field(repr=False, default=None)


def parse_spec(text, source="<spec>"):
    tokens, seen = [], set()
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        where = f"{source}:{lineno}"
        if "=" not in line:
            raise SpecError(f"{where}: ожидалось 'ИМЯ = regex'")
        head, regex = line.split("=", 1)
        regex = regex.strip()
        parts = head.split()
        kind = "token"
        if parts and parts[0].startswith("@"):
            flag = parts.pop(0)[1:]
            if flag not in ("skip", "error"):
                raise SpecError(f"{where}: неизвестный флаг @{flag}")
            kind = flag
        if len(parts) != 1 or not _NAME_RE.match(parts[0]):
            raise SpecError(f"{where}: некорректное имя токена {head.strip()!r}")
        name = parts[0]
        if name in RESERVED:
            raise SpecError(f"{where}: имя {name} зарезервировано")
        if name in seen:
            raise SpecError(f"{where}: повторное объявление {name}")
        seen.add(name)
        try:
            ast = parse_regex(regex)
        except RegexError as e:
            raise SpecError(f"{where}: {name}: {e}") from None
        if nullable(ast):
            raise SpecError(f"{where}: {name} допускает пустую строку")
        tokens.append(TokenSpec(name, regex, kind, len(tokens), ast))
    if not tokens:
        raise SpecError(f"{source}: нет ни одного токена")
    return tokens


def load_spec(path=None):
    path = Path(path) if path else DEFAULT_SPEC
    return parse_spec(path.read_text(encoding="utf-8"), str(path))
