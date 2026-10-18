import csv
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GRAMMAR = ROOT / "grammar" / "funny.ll1"
EPS = "ε"
END = "$"

EXPECTED_CONFLICTS = {("else_opt", "KW_ELSE")}


class GrammarError(ValueError):
    pass


@dataclass
class Grammar:
    start: str
    rules: dict          

    @property
    def nonterminals(self):
        return list(self.rules)

    @property
    def terminals(self):
        ts = []
        for alts in self.rules.values():
            for alt in alts:
                for s in alt:
                    if s not in self.rules and s not in ts:
                        ts.append(s)
        return ts


def parse_grammar(text, source="<grammar>"):
    rules, order, current = {}, [], None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("|"):
            if current is None:
                raise GrammarError(f"{source}:{lineno}: '|' без правила")
            body = line[1:]
        else:
            if "->" not in line:
                raise GrammarError(f"{source}:{lineno}: ожидалось 'нетерминал -> ...'")
            head, body = line.split("->", 1)
            current = head.strip()
            if not current.islower():
                raise GrammarError(f"{source}:{lineno}: нетерминал должен быть строчным: {current!r}")
            if current in rules:
                raise GrammarError(f"{source}:{lineno}: повторное правило {current}")
            rules[current] = []
            order.append(current)
        for alt in body.split("|"):
            syms = alt.split()
            if syms == [EPS]:
                syms = []
            elif not syms or EPS in syms:
                raise GrammarError(f"{source}:{lineno}: пустая альтернатива или ε внутри")
            rules[current].append(syms)
    if not order:
        raise GrammarError(f"{source}: нет правил")
    g = Grammar(order[0], rules)
    for alts in rules.values():
        for alt in alts:
            for s in alt:
                if s not in rules and not s.isupper():
                    raise GrammarError(f"{source}: неопределённый нетерминал {s!r}")
    return g


def load_grammar(path=None):
    path = Path(path) if path else DEFAULT_GRAMMAR
    return parse_grammar(path.read_text(encoding="utf-8"), str(path))


def first_sets(g):
    first = {a: set() for a in g.rules}
    changed = True
    while changed:
        changed = False
        for a, alts in g.rules.items():
            for alt in alts:
                f = first_of_seq(alt, first, g)
                if not f <= first[a]:
                    first[a] |= f
                    changed = True
    return first


def first_of_seq(seq, first, g):
    out = set()
    for s in seq:
        if s not in g.rules:          
            out.add(s)
            return out
        out |= first[s] - {EPS}
        if EPS not in first[s]:
            return out
    out.add(EPS)
    return out


def follow_sets(g, first):
    follow = {a: set() for a in g.rules}
    follow[g.start].add(END)
    changed = True
    while changed:
        changed = False
        for a, alts in g.rules.items():
            for alt in alts:
                for i, s in enumerate(alt):
                    if s not in g.rules:
                        continue
                    rest = first_of_seq(alt[i + 1:], first, g)
                    add = (rest - {EPS}) | (follow[a] if EPS in rest else set())
                    if not add <= follow[s]:
                        follow[s] |= add
                        changed = True
    return follow


def ll1_table(g, first, follow):
    table = {}
    for a, alts in g.rules.items():
        for k, alt in enumerate(alts):
            f = first_of_seq(alt, first, g)
            look = (f - {EPS}) | (follow[a] if EPS in f else set())
            for t in look:
                table.setdefault((a, t), []).append(k)
    return table


@dataclass
class Analysis:
    grammar: Grammar
    first: dict
    follow: dict
    table: dict
    conflicts: list          
    unknown_terminals: list  
    unreachable: list

    @property
    def unexpected_conflicts(self):
        return [(a, t, k) for a, t, k in self.conflicts if (a, t) not in EXPECTED_CONFLICTS]


def analyze(g, token_names=None):
    first = first_sets(g)
    follow = follow_sets(g, first)
    table = ll1_table(g, first, follow)
    conflicts = sorted((a, t, ks) for (a, t), ks in table.items() if len(ks) > 1)
    unknown = [t for t in g.terminals if token_names is not None and t not in token_names]
    seen, stack = {g.start}, [g.start]
    while stack:
        for alt in g.rules[stack.pop()]:
            for s in alt:
                if s in g.rules and s not in seen:
                    seen.add(s)
                    stack.append(s)
    unreachable = [a for a in g.rules if a not in seen]
    return Analysis(g, first, follow, table, conflicts, unknown, unreachable)


def alt_str(alt):
    return " ".join(alt) if alt else EPS


def write_reports(an, outdir):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    g = an.grammar
    lines = []
    for a in g.nonterminals:
        lines.append(f"{a}")
        lines.append(f"  FIRST  = {{ {' '.join(sorted(an.first[a]))} }}")
        lines.append(f"  FOLLOW = {{ {' '.join(sorted(an.follow[a]))} }}")
    (out / "ll1_first_follow.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    terms = sorted(g.terminals) + [END]
    with open(out / "ll1_table.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["nonterminal"] + terms)
        for a in g.nonterminals:
            row = [a]
            for t in terms:
                ks = an.table.get((a, t), [])
                row.append(" / ".join(alt_str(g.rules[a][k]) for k in ks))
            w.writerow(row)
