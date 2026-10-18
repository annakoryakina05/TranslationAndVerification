import json
import random
import string

from .dfa import equivalent, moore_count
from .export import table_dict
from .lexer import ERROR, TableLexer
from .regex import to_symbols

#1. кейсы
def run_cases(lexer, cases):
    results = []
    for i, c in enumerate(cases.get("match", [])):
        actual = lexer.match(c["input"])
        results.append(_res(f"m{i:03d}", c["group"], "match", c["input"], c["expect"], actual))
    for i, c in enumerate(cases.get("tokens", [])):
        toks = lexer.tokenize(c["input"], keep_skip=c.get("keep_skip", False))
        actual = [[t.kind, t.lexeme] for t in toks]
        results.append(_res(f"t{i:03d}", c["group"], "tokens", c["input"], c["expect"], actual,
                            name=c.get("name")))
    return results


def _res(id_, group, mode, inp, expected, actual, name=None):
    r = {"id": id_, "group": group, "mode": mode, "input": inp,
         "expected": expected, "actual": actual,
         "status": "PASS" if expected == actual else "FAIL"}
    if name:
        r["name"] = name
    return r


#2. покрытие алфавита
SINGLE_OPS = {"(": "LPAREN", ")": "RPAREN", "[": "LBRACKET", "]": "RBRACKET",
              "{": "LBRACE", "}": "RBRACE", ",": "COMMA", ";": "SEMI",
              "+": "PLUS", "-": "MINUS", "*": "STAR", "/": "SLASH",
              "<": "LT", ">": "GT", "=": "ASSIGN", ":": "COLON", "|": "BAR"}
NON_ASCII_SAMPLES = ["\u0080", "\u00a0", "é", "п", "€", "\u2028", "\U0001F600"]


def expected_single(ch):
    if ch in string.ascii_letters:            
        return "IDENT"
    if ch in string.digits:
        return "INT"
    if ch in " \t\r\n":
        return "WS"
    return SINGLE_OPS.get(ch, ERROR)


def run_alphabet(lexer):
    results = []
    for ch in [chr(i) for i in range(128)] + NON_ASCII_SAMPLES:
        exp = [[expected_single(ch), ch]]
        act = [[t.kind, t.lexeme] for t in lexer.tokenize(ch, keep_skip=True)]
        results.append(_res(f"a{ord(ch):05x}", "alphabet", "tokens", ch, exp, act))
    return results


#3. свойства
PIECES = ["if", "else", "while", "function", "returns", "length", "invariant", "assume",
          "assert", "x", "_", "0", "1", "9", "00", " ", "\t", "\r\n", "\n", "/", "//", "=",
          "==", "!", "!=", "<", "<=", ">", ">=", "(", "]", "é", "@", "a1", ";",
          "int", "and", "or", "not", "true", "->", "=>", ":", "|", "\u2192"]


def nfa_tokenize(nfa, tokens, text, keep_skip=False):
    syms, out, pos = to_symbols(text), [], 0
    while pos < len(text):
        cur, i, last = nfa.eclose({nfa.start}), pos, None
        while i < len(text):
            cur = nfa.step(cur, syms[i])
            if not cur:
                break
            i += 1
            l = nfa.label(cur)
            if l is not None:
                last = (i, l)
        if last is None:
            out.append([ERROR, text[pos]])
            pos += 1
            continue
        end, l = last
        if keep_skip or tokens[l].kind != "skip":
            out.append([tokens[l].name, text[pos:end]])
        pos = end
    return out


def random_string(rng):
    parts = []
    for _ in range(rng.randint(0, 6)):
        if rng.random() < 0.3:
            parts.append(chr(rng.choice(list(range(128)) + [0xE9, 0x43F])))
        else:
            parts.append(rng.choice(PIECES))
    return "".join(parts)


def run_properties(result, lexer, samples=1500, seed=2026):
    rng = random.Random(seed)
    nfa, dfa, mdfa = result.nfa, result.dfa, result.min_dfa
    res = []

    def prop(name, ok, detail):
        res.append({"id": f"p-{name}", "group": "property", "mode": "property", "input": name,
                    "expected": True, "actual": ok, "status": "PASS" if ok else "FAIL",
                    "detail": detail})

    prop("hopcroft_equals_moore", moore_count(dfa) == mdfa.num_states,
         f"Мур: {moore_count(dfa)}, Хопкрофт: {mdfa.num_states}")
    prop("min_dfa_is_minimal", moore_count(mdfa) == mdfa.num_states,
         "в мин. ДКА нет эквивалентных состояний")
    prop("min_dfa_equivalent", equivalent(dfa, mdfa), "обход произведения ДКА × мин. ДКА")
    trap_ok = all(t == mdfa.trap for t in mdfa.trans[mdfa.trap]) and mdfa.labels[mdfa.trap] is None
    prop("trap_is_sink", trap_ok, "ловушка непринимающая и замкнута на себя")

    bad_match = bad_lex = None
    for _ in range(samples):
        s = random_string(rng)
        a, b, c = nfa.match(s), dfa.match(s), mdfa.match(s)
        if not (a == b == c) and bad_match is None:
            bad_match = {"input": s, "nfa": a, "dfa": b, "min": c}
        ref = nfa_tokenize(nfa, result.tokens, s, keep_skip=True)
        got = [[t.kind, t.lexeme] for t in lexer.tokenize(s, keep_skip=True)]
        if ref != got and bad_lex is None:
            bad_lex = {"input": s, "nfa_lexer": ref, "table_lexer": got}
    prop("nfa_dfa_min_agree", bad_match is None,
         bad_match or f"{samples} случайных строк, seed={seed}")
    prop("table_lexer_equals_nfa_lexer", bad_lex is None,
         bad_lex or f"{samples} случайных строк, seed={seed}")
    return res


# всё вместе
def run_all(result, cases_path):
    lexer = TableLexer(table_dict(result))
    with open(cases_path, encoding="utf-8") as f:
        cases = json.load(f)
    return run_cases(lexer, cases) + run_alphabet(lexer) + run_properties(result, lexer)


def summarize(results):
    groups = {}
    for r in results:
        g = groups.setdefault(r["group"], [0, 0])
        g[0 if r["status"] == "PASS" else 1] += 1
    return groups
