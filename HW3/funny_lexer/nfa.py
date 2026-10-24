from .regex import to_symbols


class NFA:
    def __init__(self):
        self.eps = []        # eps[s]   -> [t, ...]
        self.edges = []      # edges[s] -> [(frozenset(symbols), t), ...]
        self.accept = {}     # state -> priority токена
        self.start = None

    def new_state(self):
        self.eps.append([])
        self.edges.append([])
        return len(self.eps) - 1

    # ---------- конструкция Томпсона ----------
    def fragment(self, node):
        k = node[0]
        if k == "eps":
            s, e = self.new_state(), self.new_state()
            self.eps[s].append(e)
            return s, e
        if k == "set":
            s, e = self.new_state(), self.new_state()
            self.edges[s].append((node[1], e))
            return s, e
        if k == "cat":
            s1, e1 = self.fragment(node[1])
            s2, e2 = self.fragment(node[2])
            self.eps[e1].append(s2)
            return s1, e2
        if k == "alt":
            s = self.new_state()
            s1, e1 = self.fragment(node[1])
            s2, e2 = self.fragment(node[2])
            e = self.new_state()
            self.eps[s] += [s1, s2]
            self.eps[e1].append(e)
            self.eps[e2].append(e)
            return s, e
        if k == "star":
            s = self.new_state()
            s1, e1 = self.fragment(node[1])
            e = self.new_state()
            self.eps[s] += [s1, e]
            self.eps[e1] += [s1, e]
            return s, e
        if k == "plus":
            s = self.new_state()
            s1, e1 = self.fragment(node[1])
            e = self.new_state()
            self.eps[s].append(s1)
            self.eps[e1] += [s1, e]
            return s, e
        if k == "opt":
            s = self.new_state()
            s1, e1 = self.fragment(node[1])
            e = self.new_state()
            self.eps[s] += [s1, e]
            self.eps[e1].append(e)
            return s, e
        raise ValueError(f"неизвестный узел {k}")

    # ---------- статистика ----------
    @property
    def num_states(self):
        return len(self.eps)

    @property
    def num_eps_edges(self):
        return sum(map(len, self.eps))

    @property
    def num_char_edges(self):
        return sum(map(len, self.edges))

    def edge_sets(self):
        seen = {}
        for row in self.edges:
            for cs, _ in row:
                seen.setdefault(cs, None)
        return list(seen)

    # ---------- симуляция (эталон для тестов) ----------
    def eclose(self, states):
        result = set(states)
        stack = list(states)
        while stack:
            for t in self.eps[stack.pop()]:
                if t not in result:
                    result.add(t)
                    stack.append(t)
        return frozenset(result)

    def step(self, states, sym):
        return self.eclose({t for s in states for cs, t in self.edges[s] if sym in cs})

    def label(self, states):
        return min((self.accept[s] for s in states if s in self.accept), default=None)

    def match(self, text):
        """Приоритет токена, если ВСЯ строка — один токен, иначе None."""
        cur = self.eclose({self.start})
        for sym in to_symbols(text):
            cur = self.step(cur, sym)
            if not cur:
                return None
        return self.label(cur)


def build_nfa(tokens):
    nfa = NFA()
    nfa.start = nfa.new_state()
    for tok in tokens:
        s, e = nfa.fragment(tok.ast)
        nfa.eps[nfa.start].append(s)
        nfa.accept[e] = tok.priority
    return nfa
