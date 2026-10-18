"""НКА → ДКА (subset construction) → минимальный ДКА (Хопкрофт).

Алфавит из 129 символов (ASCII + OTHER) сначала разбивается на классы
эквивалентности: два символа в одном классе, если ни одно ребро НКА их не
различает. Переходы ДКА строятся по классам — это точная (без потерь)
компрессия таблицы.

ДКА всегда полный: пустое множество НКА-состояний — это явная «ловушка»
(trap) с петлями по всем классам. В неё ведут все непокрытые символы,
в том числе любой non-ASCII (символ OTHER).
"""
from collections import deque

from .regex import ALPHABET_SIZE, to_symbols


class DFA:
    def __init__(self, class_of, trans, labels, start, trap):
        self.class_of = list(class_of)   # символ (0..128) -> класс
        self.trans = trans               # trans[state][class] -> state
        self.labels = labels             # labels[state] -> priority | None
        self.start = start
        self.trap = trap

    @property
    def num_states(self):
        return len(self.trans)

    @property
    def num_classes(self):
        return len(self.trans[0]) if self.trans else 0

    @property
    def num_accepting(self):
        return sum(l is not None for l in self.labels)

    def match(self, text):
        s = self.start
        for sym in to_symbols(text):
            s = self.trans[s][self.class_of[sym]]
            if s == self.trap:
                return None
        return self.labels[s]


# ---------------------------------------------------------------- классы
def compute_char_classes(nfa):
    """Разбиение алфавита по «сигнатуре» — в каких множествах рёбер НКА символ встречается."""
    sets = nfa.edge_sets()
    sig_to_class, reps = {}, []
    class_of = [0] * ALPHABET_SIZE
    for sym in range(ALPHABET_SIZE):
        sig = tuple(i for i, cs in enumerate(sets) if sym in cs)
        if sig not in sig_to_class:
            sig_to_class[sig] = len(reps)
            reps.append(sym)
        class_of[sym] = sig_to_class[sig]
    return class_of, reps


# ---------------------------------------------------- subset construction
def subset_construction(nfa, class_of, reps):
    start = nfa.eclose({nfa.start})
    index, sets, trans = {start: 0}, [start], []
    i = 0
    while i < len(sets):
        S = sets[i]
        row = []
        for r in reps:
            T = nfa.step(S, r)
            if T not in index:
                index[T] = len(sets)
                sets.append(T)
            row.append(index[T])
        trans.append(row)
        i += 1
    labels = [nfa.label(S) for S in sets]
    trap = index.get(frozenset())
    if trap is None:  # на всякий случай: гарантируем полноту автомата
        trap = len(trans)
        trans.append([trap] * len(reps))
        labels.append(None)
        sets.append(frozenset())
    return DFA(class_of, trans, labels, 0, trap), sets


# ------------------------------------------------------------- Хопкрофт
def hopcroft_partition(dfa):
    """Возвращает block_of[state] — номер класса эквивалентности."""
    n, k = dfa.num_states, dfa.num_classes
    inv = [[[] for _ in range(n)] for _ in range(k)]
    for s in range(n):
        for c, t in enumerate(dfa.trans[s]):
            inv[c][t].append(s)

    # Начальное разбиение: по метке (не-принимающие отдельно,
    # принимающие — по ТОКЕНУ, иначе слились бы IDENT и KW_IF).
    groups = {}
    for s in range(n):
        groups.setdefault(dfa.labels[s], set()).add(s)
    P = list(groups.values())
    block_of = [0] * n
    for b, block in enumerate(P):
        for s in block:
            block_of[s] = b
    W = set(range(len(P)))

    while W:
        A = set(P[W.pop()])  # фиксируем сплиттер
        for c in range(k):
            X = set()
            for t in A:
                X.update(inv[c][t])
            if not X:
                continue
            touched = {}
            for s in X:
                touched.setdefault(block_of[s], set()).add(s)
            for b, inter in touched.items():
                Y = P[b]
                if len(inter) == len(Y):
                    continue
                diff = Y - inter
                P[b] = inter
                P.append(diff)
                nb = len(P) - 1
                for s in diff:
                    block_of[s] = nb
                if b in W:
                    W.add(nb)
                else:
                    W.add(nb if len(diff) <= len(inter) else b)
    return block_of, len(P)


def canonical(dfa):
    """BFS-перенумерация: старт = 0, ловушка — последнее состояние."""
    order, seen = [], {dfa.start, dfa.trap}
    q = deque([dfa.start])
    while q:
        s = q.popleft()
        order.append(s)
        for t in dfa.trans[s]:
            if t not in seen:
                seen.add(t)
                q.append(t)
    order.append(dfa.trap)
    new = {old: i for i, old in enumerate(order)}
    trans = [[new[t] for t in dfa.trans[s]] for s in order]
    labels = [dfa.labels[s] for s in order]
    return DFA(dfa.class_of, trans, labels, new[dfa.start], new[dfa.trap])


def minimize(dfa):
    block_of, nb = hopcroft_partition(dfa)
    trans, labels = [None] * nb, [None] * nb
    for s in range(dfa.num_states):
        b = block_of[s]
        if trans[b] is None:
            trans[b] = [block_of[t] for t in dfa.trans[s]]
            labels[b] = dfa.labels[s]
    q = DFA(dfa.class_of, trans, labels, block_of[dfa.start], block_of[dfa.trap])
    return canonical(q)


# ------------------------------------------------- независимые проверки
def moore_count(dfa):
    """Число классов эквивалентности по алгоритму Мура (для сверки с Хопкрофтом)."""
    keys = {}
    part = [keys.setdefault(l, len(keys)) for l in dfa.labels]
    while True:
        sig = {}
        new = [sig.setdefault((part[s], tuple(part[t] for t in row)), len(sig))
               for s, row in enumerate(dfa.trans)]
        if len(sig) == len(set(part)):
            return len(sig)
        part = new


def equivalent(a, b):
    """Проверка эквивалентности двух ДКА (с одинаковыми классами) обходом произведения."""
    seen = {(a.start, b.start)}
    q = deque(seen)
    while q:
        x, y = q.popleft()
        if a.labels[x] != b.labels[y]:
            return False
        for c in range(a.num_classes):
            p = (a.trans[x][c], b.trans[y][c])
            if p not in seen:
                seen.add(p)
                q.append(p)
    return True
