"""Генераторы заданий.

Принцип устойчивости к распространению заданий (подробно — docs/DOCUMENTATION.md, §4):
  * задание — не текст, а *параметризованный шаблон* (семейство × уровень сложности);
    параметры (числа, данные, код, порядок вариантов) определяются сидом конкретной попытки;
  * правильный ответ вычисляется кодом (выполнением сгенерированной программы, SQL в sqlite,
    модулем ipaddress и т.п.), а не берётся из шаблона — поэтому утечка «задания и ответа»
    бесполезна: у следующего кандидата другие данные и другой ответ;
  * сложность задаётся не нейросетью «на глаз», а уровнем семейства и структурой блюпринта
    (см. engine.py) — все кандидаты одного грейда получают один и тот же набор
    (семейство, уровень), различаются лишь параметры.

Типы заданий: choice (один вариант из четырёх) и number (числовой ответ, допуск tol).
"""
import ipaddress
import itertools
import math
import random
import re
import sqlite3
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Callable, Optional
import heapq


# --------------------------------------------------------------------------- вспомогательное
def _code(src: str, lang: str = "python") -> str:
    return f"```{lang}\n{src.strip()}\n```"


def run_py(src: str) -> str:
    """Выполняет СГЕНЕРИРОВАННЫЙ нами код (только целые числа и безопасные builtins) и возвращает вывод."""
    out: list[str] = []
    safe = {"range": range, "len": len, "sum": sum, "min": min, "max": max, "abs": abs, "sorted": sorted,
            "enumerate": enumerate, "zip": zip, "set": set, "list": list, "dict": dict, "print": lambda *a: out.append(" ".join(map(str, a)))}
    exec(src, {"__builtins__": safe}, {})
    return "\n".join(out).strip()


def number(prompt: str, value, *, family: str, topic: str, level: int, tol: float = 0.0, unit: str = "",
           explanation: str = "") -> dict:
    return {"family": family, "topic": topic, "level": level, "kind": "number", "prompt": prompt,
            "answer": value, "tol": tol, "unit": unit, "explanation": explanation}


def choice(rng: random.Random, prompt: str, correct: str, wrongs: list[str], *, family: str, topic: str, level: int,
           explanation: str = "") -> dict:
    wrongs = [w for i, w in enumerate(wrongs) if w != correct and w not in wrongs[:i]][:3]
    options = [correct] + wrongs
    rng.shuffle(options)
    return {"family": family, "topic": topic, "level": level, "kind": "choice", "prompt": prompt,
            "options": options, "answer": options.index(correct), "explanation": explanation}


def _near(rng: random.Random, v: int, k: int = 3, lo: Optional[int] = None) -> list[int]:
    """Правдоподобные неверные числа вокруг v (ошибки «на единицу», удвоение и т.п.)."""
    cands = {v + 1, v - 1, v + 2, v - 2, v * 2, max(v // 2, 0), v + 10, v - 10}
    cands.discard(v)
    if lo is not None:
        cands = {c for c in cands if c >= lo}
    cands = sorted(cands)
    rng.shuffle(cands)
    return cands[:k]


# =========================================================================== ОБЩИЕ СЕМЕЙСТВА
def g_py_trace(rng, level):
    if level == 1:
        a, b, k = rng.randint(1, 9), rng.randint(10, 40), rng.randint(2, 12)
        src = f"total = 0\nfor i in range({a}, {b}):\n    total += i * {k}\nprint(total)"
    elif level == 2:
        a, b, m, d = rng.randint(1, 6), rng.randint(14, 45), rng.randint(2, 7), rng.randint(1, 4)
        src = (f"total = 0\nfor i in range({a}, {b}):\n    if i % {m} == 0:\n        total += i\n    else:\n"
               f"        total -= {d}\nprint(total)")
    elif level == 3:
        data = [rng.randint(0, 6) for _ in range(rng.randint(9, 12))]
        src = (f"data = {data}\nseen = set()\ndup = 0\nfor x in data:\n    if x in seen:\n        dup += 1\n"
               f"    else:\n        seen.add(x)\nprint(dup * 10 + len(seen))")
    else:
        data = [rng.randint(1, 15) for _ in range(rng.randint(11, 14))]
        s, off = rng.choice([2, 3]), rng.randint(0, 2)
        src = f"data = {data}\nres = [x * x for x in data[{off}::{s}] if x % 2]\nprint(sum(res) - len(res))"
    val = int(run_py(src))
    return number("Что выведет программа?\n\n" + _code(src), val, family="py_trace", topic="python", level=level)


def g_big_o_ops(rng, level):
    if level == 1:
        n, s = rng.randint(30, 90), rng.randint(2, 5)
        src = f"c = 0\nfor i in range(0, {n}, {s}):\n    c += 1\nprint(c)"
    elif level == 2:
        a, b, m = rng.randint(4, 14), rng.randint(5, 14), rng.randint(2, 4)
        src = (f"c = 0\nfor i in range({a}):\n    for j in range({b}):\n        if (i + j) % {m} == 0:\n"
               f"            c += 1\nprint(c)")
    elif level == 3:
        n, s, w = rng.randint(9, 28), rng.randint(1, 3), rng.randint(1, 4)
        src = f"c = 0\nfor i in range({n}):\n    for j in range(0, i, {s}):\n        c += {w}\nprint(c)"
    else:
        n, w = rng.randint(40, 300), rng.randint(1, 3)
        src = f"c = 0\ni = 1\nwhile i < {n}:\n    for j in range(i):\n        c += {w}\n    i *= 2\nprint(c)"
    return number("Сколько раз выполнится `c += 1`, т.е. какое значение выведет программа?\n\n" + _code(src),
                  int(run_py(src)), family="big_o_ops", topic="algorithms", level=level)


def g_binsearch(rng, level):
    n = {2: rng.randint(12, 18), 3: rng.randint(15, 22), 4: rng.randint(16, 24)}.get(level, 12)
    data = sorted(rng.sample(range(1, 120), n))
    if level == 4:  # с дубликатами и поиском первого вхождения
        data = sorted(rng.choices(range(1, 25), k=n))
    target = rng.choice(data) if level != 3 else rng.choice([x for x in range(1, 120) if x not in data])
    if level == 4:
        body = ("lo, hi, steps = 0, len(data), 0\nwhile lo < hi:\n    steps += 1\n    mid = (lo + hi) // 2\n"
                "    if data[mid] < target:\n        lo = mid + 1\n    else:\n        hi = mid\nprint(steps * 100 + lo)")
        ask = "Что выведет программа (поиск первого вхождения)?"
    else:
        body = ("lo, hi, steps = 0, len(data) - 1, 0\nwhile lo <= hi:\n    steps += 1\n    mid = (lo + hi) // 2\n"
                "    if data[mid] == target:\n        break\n    elif data[mid] < target:\n        lo = mid + 1\n"
                "    else:\n        hi = mid - 1\nprint(steps)")
        ask = "Сколько итераций цикла выполнит бинарный поиск (что выведет программа)?"
    src = f"data = {data}\ntarget = {target}\n{body}"
    return number(ask + "\n\n" + _code(src), int(run_py(src)), family="binsearch", topic="algorithms", level=level)


def g_sort_count(rng, level):
    if level in (1, 2):
        n = 5 if level == 1 else 7
        arr = rng.sample(range(1, 30), n)
        src = (f"a = {arr}\nswaps = 0\nfor i in range(len(a)):\n    for j in range(len(a) - 1 - i):\n"
               f"        if a[j] > a[j + 1]:\n            a[j], a[j + 1] = a[j + 1], a[j]\n            swaps += 1\nprint(swaps)")
        return number("Сколько обменов выполнит пузырьковая сортировка (что выведет программа)?\n\n" + _code(src),
                      int(run_py(src)), family="sort_count", topic="algorithms", level=level)
    if level == 3:
        arr = rng.sample(range(1, 40), 8)
        src = (f"a = {arr}\nshifts = 0\nfor i in range(1, len(a)):\n    key = a[i]\n    j = i - 1\n"
               f"    while j >= 0 and a[j] > key:\n        a[j + 1] = a[j]\n        j -= 1\n        shifts += 1\n"
               f"    a[j + 1] = key\nprint(shifts)")
        return number("Сколько сдвигов элементов выполнит сортировка вставками?\n\n" + _code(src),
                      int(run_py(src)), family="sort_count", topic="algorithms", level=level)
    arr = rng.sample(range(1, 50), 10)
    inv = sum(1 for i in range(10) for j in range(i + 1, 10) if arr[i] > arr[j])
    return number(f"Сколько инверсий в массиве `{arr}`? (инверсия — пара индексов i < j, где a[i] > a[j])",
                  inv, family="sort_count", topic="algorithms", level=level)


def g_struct_sim(rng, level):
    if level == 1:
        ops, s = [], []
        lines = ["s = []"]
        for _ in range(rng.randint(6, 8)):
            if s and rng.random() < 0.4:
                lines.append("s.pop()")
                s.pop()
            else:
                v = rng.randint(1, 9)
                lines.append(f"s.append({v})")
                s.append(v)
        if not s:
            lines.append("s.append(1)"); s.append(1)
        lines.append("print(s[-1] + len(s))")
        src = "\n".join(lines)
        return number("Что выведет программа?\n\n" + _code(src), s[-1] + len(s),
                      family="struct_sim", topic="python", level=level)
    if level == 2:
        lines, d = ["from collections import deque", "d = deque()"], deque()
        for _ in range(rng.randint(7, 9)):
            r = rng.random()
            if d and r < 0.3:
                lines.append("d.popleft()"); d.popleft()
            elif d and r < 0.45:
                lines.append("d.pop()"); d.pop()
            elif r < 0.75:
                v = rng.randint(1, 9); lines.append(f"d.append({v})"); d.append(v)
            else:
                v = rng.randint(1, 9); lines.append(f"d.appendleft({v})"); d.appendleft(v)
        if not d:
            lines.append("d.append(5)"); d.append(5)
        lines.append("print(sum(d) * 10 + len(d))")
        return number("Что выведет программа?\n\n" + _code("\n".join(lines)), sum(d) * 10 + len(d),
                      family="struct_sim", topic="algorithms", level=level)
    if level == 3:
        data = rng.sample(range(1, 50), rng.randint(7, 9))
        k = rng.randint(3, 4)
        h = list(data); heapq.heapify(h)
        popped = [heapq.heappop(h) for _ in range(k)]
        src = (f"import heapq\nh = []\nfor x in {data}:\n    heapq.heappush(h, x)\ntotal = 0\n"
               f"for _ in range({k}):\n    total += heapq.heappop(h)\nprint(total)")
        return number("Что выведет программа (min-куча)?\n\n" + _code(src), sum(popped),
                      family="struct_sim", topic="algorithms", level=level)
    cap, seq = rng.randint(3, 4), [rng.randint(1, 6) for _ in range(rng.randint(14, 17))]
    cache, hits = OrderedDict(), 0
    for key in seq:
        if key in cache:
            hits += 1; cache.move_to_end(key)
        else:
            if len(cache) >= cap:
                cache.popitem(last=False)
            cache[key] = 1
    return number(f"Кэш LRU ёмкостью {cap} изначально пуст. Последовательность обращений к ключам: `{seq}`. "
                  f"Сколько обращений окажутся попаданиями (hit)?", hits, family="struct_sim", topic="backend_arch", level=level)


_NAMES = ["Anna", "Boris", "Vera", "Gleb", "Dina"]
_CITIES = ["Kazan", "Perm", "Omsk", "Tula"]


def g_sql_exec(rng, level):
    names = _NAMES[:rng.randint(4, 5)]
    orders = [(i + 1, rng.choice(names[:-1] if level == 4 else names), rng.randrange(100, 951, 50),
               rng.choice(["paid", "paid", "new", "cancel"])) for i in range(rng.randint(8, 12))]
    custs = [(n, rng.choice(_CITIES)) for n in names]
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE orders(id INTEGER, customer TEXT, amount INTEGER, status TEXT)")
    con.execute("CREATE TABLE customers(name TEXT, city TEXT)")
    con.executemany("INSERT INTO orders VALUES (?,?,?,?)", orders)
    con.executemany("INSERT INTO customers VALUES (?,?)", custs)
    thr = rng.randrange(200, 700, 50)
    who, city = rng.choice(names), rng.choice(sorted({c for _, c in custs}))
    if level == 1:
        sql = f"SELECT COUNT(*) FROM orders WHERE status = 'paid' AND amount > {thr};"
    elif level == 2:
        sql = f"SELECT SUM(amount) FROM orders WHERE customer = '{who}' AND status <> 'cancel';"
    elif level == 3:
        sql = (f"SELECT COUNT(DISTINCT o.customer) FROM orders o JOIN customers c ON c.name = o.customer\n"
               f"WHERE c.city = '{city}' AND o.status = 'paid';")
    else:
        sql = ("SELECT COUNT(*) FROM customers c\nLEFT JOIN orders o ON o.customer = c.name AND o.status = 'paid'\n"
               "WHERE o.id IS NULL;") if rng.random() < 0.5 else \
              "SELECT COUNT(*) FROM orders\nWHERE amount > (SELECT AVG(amount) FROM orders WHERE status = 'paid');"
    val = con.execute(sql.rstrip(";")).fetchone()[0] or 0
    con.close()
    t_orders = "| id | customer | amount | status |\n|---|---|---|---|\n" + "\n".join(
        f"| {a} | {b} | {c} | {d} |" for a, b, c, d in orders)
    t_cust = "| name | city |\n|---|---|\n" + "\n".join(f"| {n} | {c} |" for n, c in custs)
    prompt = (f"Таблица `orders`:\n\n{t_orders}\n\nТаблица `customers`:\n\n{t_cust}\n\n"
              f"Какое число вернёт запрос?\n\n{_code(sql, 'sql')}")
    return number(prompt, int(val), family="sql_exec", topic="sql", level=level)


_WORDS = ["alpha", "Beta", "gamma", "Delta", "x1", "node7", "Test", "data", "Rust", "go", "Java", "py3"]


def g_regex(rng, level):
    if level == 1:
        toks = [rng.choice(["a", "bb", "7", "42", "x9", "105", "k", "3z"]) for _ in range(rng.randint(8, 11))]
        text = " ".join(toks)
        pat = r"\d+"
        val = len(re.findall(pat, text))
        prompt = f"Сколько совпадений вернёт `re.findall(r\"{pat}\", s)` для строки `s = \"{text}\"`?"
    elif level == 2:
        words = rng.choices(_WORDS, k=rng.randint(8, 10))
        pat = r"^[A-Z][a-z]+$"
        val = sum(1 for w in words if re.fullmatch(pat, w))
        prompt = f"Для скольких элементов списка `{words}` выражение `re.fullmatch(r\"{pat}\", w)` вернёт совпадение?"
    elif level == 3:
        users = ["ann", "bob", "k9", "x_y", "dev", "q"]
        doms = ["mail.ru", "ya.ru", "site.com", "corp.com", "x.org"]
        mails = [f"{rng.choice(users)}@{rng.choice(doms)}" for _ in range(rng.randint(8, 10))]
        text = ", ".join(mails)
        pat = r"\w+@\w+\.com"
        val = len(re.findall(pat, text))
        prompt = f"Сколько совпадений вернёт `re.findall(r\"{pat}\", s)` для `s = \"{text}\"`?"
    else:
        toks = [f"{rng.choice([12, 34, 56])}-{rng.choice([12, 34, 56])}" for _ in range(rng.randint(9, 12))]
        text = " ".join(toks)
        pat = r"\b(\d{2})-\1\b"
        val = len(re.findall(pat, text))
        prompt = f"Сколько совпадений вернёт `re.findall(r\"{pat}\", s)` для `s = \"{text}\"`?"
    return number(prompt, val, family="regex", topic="python", level=level)


def g_bits(rng, level):
    a, b = rng.randint(5, 60), rng.randint(5, 60)
    if level == 1:
        op = rng.choice(["&", "|", "^"])
        expr, val = f"{a} {op} {b}", eval(f"{a} {op} {b}")
    elif level == 2:
        s = rng.randint(1, 3)
        expr, val = f"({a} << {s}) ^ {b}", (a << s) ^ b
    elif level == 3:
        s, t = rng.randint(1, 3), rng.randint(1, 3)
        expr, val = f"({a} << {s}) | ({b} >> {t})", (a << s) | (b >> t)
    else:
        n = rng.randint(100, 900)
        x, cnt = n, 0
        while x:
            x &= x - 1
            cnt += 1
        src = f"n = {n}\ncnt = 0\nwhile n:\n    n &= n - 1\n    cnt += 1\nprint(cnt)"
        return number("Что выведет программа?\n\n" + _code(src), cnt, family="bits", topic="algorithms", level=level)
    return number(f"Чему равно значение выражения Python `{expr}`?", val, family="bits", topic="algorithms", level=level)


def _rand_graph(rng, n, extra):
    edges = set()
    nodes = list(range(1, n + 1))
    rng.shuffle(nodes)
    for i in range(1, n):
        edges.add(tuple(sorted((nodes[i], nodes[rng.randrange(i)]))))
    while extra > 0:
        a, b = rng.sample(range(1, n + 1), 2)
        e = tuple(sorted((a, b)))
        if e not in edges:
            edges.add(e); extra -= 1
    return sorted(edges)


def g_graph(rng, level):
    if level == 2:
        n = rng.randint(6, 8)
        edges = _rand_graph(rng, n, rng.randint(2, 3))
        s, t = rng.sample(range(1, n + 1), 2)
        adj = {i: [] for i in range(1, n + 1)}
        for a, b in edges:
            adj[a].append(b); adj[b].append(a)
        dist, dq = {s: 0}, deque([s])
        while dq:
            u = dq.popleft()
            for v in adj[u]:
                if v not in dist:
                    dist[v] = dist[u] + 1; dq.append(v)
        return number(f"Неориентированный граф с рёбрами: {edges}. Какова длина (в рёбрах) кратчайшего пути от вершины {s} до {t}?",
                      dist[t], family="graph", topic="algorithms", level=level)
    if level == 3:
        n = rng.randint(10, 15)
        k = rng.randint(2, 6)
        cuts = sorted(rng.sample(range(1, n), k - 1))
        verts = list(range(1, n + 1))
        rng.shuffle(verts)
        groups = [verts[a:b] for a, b in zip([0] + cuts, cuts + [n])]
        edges = set()
        for g in groups:
            for i in range(1, len(g)):
                edges.add(tuple(sorted((g[i], g[rng.randrange(i)]))))
            if len(g) >= 3 and rng.random() < 0.6:
                a, b = rng.sample(g, 2)
                edges.add(tuple(sorted((a, b))))
        edges = sorted(edges)
        if rng.random() < 0.5:
            return number(f"Неориентированный граф на вершинах 1..{n} с рёбрами: {edges}. Сколько в нём компонент связности (изолированные вершины считаются)?",
                          k, family="graph", topic="algorithms", level=level)
        return number(f"Неориентированный граф на вершинах 1..{n} с рёбрами: {edges}. Сколько вершин в самой большой компоненте связности?",
                      max(len(g) for g in groups), family="graph", topic="algorithms", level=level)
    n = rng.randint(6, 7)
    base = _rand_graph(rng, n, rng.randint(3, 5))
    wedges = [(a, b, rng.randint(1, 9)) for a, b in base]
    s, t = 1, n
    dist = {i: math.inf for i in range(1, n + 1)}
    dist[s] = 0
    pq = [(0, s)]
    adj = {i: [] for i in range(1, n + 1)}
    for a, b, w in wedges:
        adj[a].append((b, w)); adj[b].append((a, w))
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]:
            continue
        for v, w in adj[u]:
            if d + w < dist[v]:
                dist[v] = d + w; heapq.heappush(pq, (dist[v], v))
    return number(f"Взвешенный неориентированный граф, рёбра в формате (u, v, вес): {wedges}. Какова длина кратчайшего пути от вершины {s} до вершины {t}?",
                  int(dist[t]), family="graph", topic="algorithms", level=4 if level >= 4 else level)


def g_dp(rng, level):
    if level == 2:
        if rng.random() < 0.5:
            steps = rng.choice([(1, 2), (1, 3), (2, 3), (1, 2, 3)])
            n = rng.randint(7, 16)
            ways = [1] + [0] * n
            for i in range(1, n + 1):
                ways[i] = sum(ways[i - s] for s in steps if i >= s)
            sl = ", ".join(map(str, steps))
            return number(f"Лестница из {n} ступеней. За один шаг можно подняться ровно на k ступеней, где k ∈ {{{sl}}}. Сколькими способами можно подняться на вершину?",
                          ways[n], family="dp", topic="algorithms", level=level)
        h, w = rng.randint(4, 6), rng.randint(4, 6)
        cells = [(r, c) for r in range(h) for c in range(w) if (r, c) not in ((0, 0), (h - 1, w - 1))]
        blocked = set(rng.sample(cells, rng.randint(2, 4)))
        g = [[0] * w for _ in range(h)]
        g[0][0] = 1
        for r in range(h):
            for c in range(w):
                if (r, c) in blocked or (r, c) == (0, 0):
                    continue
                g[r][c] = (g[r - 1][c] if r else 0) + (g[r][c - 1] if c else 0)
        return number(f"Сетка {h}×{w}. Робот идёт из левого верхнего угла в правый нижний, двигаясь только вправо или вниз. "
                      f"Клетки (строка, столбец; нумерация с 0) {sorted(blocked)} заблокированы. Сколько существует маршрутов?",
                      g[h - 1][w - 1], family="dp", topic="algorithms", level=level)
    if level == 3:
        coins = sorted(rng.sample([1, 2, 3, 4, 5, 6, 7, 9, 10, 12, 15], 3))
        if 1 not in coins:
            coins[0] = 1
        amount = rng.randint(18, 59)
        dp = [0] + [10 ** 9] * amount
        for x in range(1, amount + 1):
            for c in coins:
                if c <= x:
                    dp[x] = min(dp[x], dp[x - c] + 1)
        return number(f"Монеты номиналами {coins} (каждого номинала — неограниченно). Какое минимальное число монет нужно, чтобы набрать сумму {amount}?",
                      dp[amount], family="dp", topic="algorithms", level=level)
    items = [(rng.randint(2, 8), rng.randint(3, 15)) for _ in range(5)]
    cap = rng.randint(10, 15)
    dp = [0] * (cap + 1)
    for w, v in items:
        for c in range(cap, w - 1, -1):
            dp[c] = max(dp[c], dp[c - w] + v)
    return number(f"Задача о рюкзаке 0/1. Предметы (вес, ценность): {items}. Вместимость рюкзака — {cap}. Какова максимальная суммарная ценность?",
                  dp[cap], family="dp", topic="algorithms", level=4 if level >= 4 else level)


def g_cidr(rng, level):
    if level == 1:
        p = rng.randint(17, 30)
        t = rng.choice(["hosts", "total", "mask"])
        if t == "hosts":
            return number(f"Сколько адресов хостов (без адреса сети и широковещательного) в подсети /{p}?",
                          2 ** (32 - p) - 2, family="cidr", topic="networks", level=level)
        if t == "total":
            return number(f"Сколько всего IPv4-адресов (включая сетевой и широковещательный) в подсети /{p}?",
                          2 ** (32 - p), family="cidr", topic="networks", level=level)
        p = rng.randint(24, 30)
        return number(f"Маска подсети /{p} в десятичной записи имеет вид 255.255.255.X. Чему равно X?",
                      256 - 2 ** (32 - p), family="cidr", topic="networks", level=level)
    if level == 2:
        p = rng.randint(22, 27)
        base = ipaddress.ip_network(f"10.{rng.randint(0, 200)}.{rng.randint(0, 255)}.0/{p}", strict=False)
        inside = rng.random() < 0.5
        hosts = list(itertools.islice(base.hosts(), 0, 600))
        ip = rng.choice(hosts) if inside else ipaddress.ip_address(int(base.network_address) + base.num_addresses + rng.randint(1, 40))
        if not inside and rng.random() < 0.5:
            ip = ipaddress.ip_address(int(base.network_address) - rng.randint(1, 40))
        return choice(rng, f"Принадлежит ли адрес {ip} сети {base}?",
                      "Да" if ip in base else "Нет", ["Нет" if ip in base else "Да", "Только как адрес шлюза", "Зависит от маски шлюза"],
                      family="cidr", topic="networks", level=level)
    if level == 3:
        p = rng.randint(16, 24)
        q = rng.randint(p + 2, 29)
        if rng.random() < 0.5:
            return number(f"Сеть /{p} нужно разбить на равные подсети /{q}. Сколько подсетей получится?",
                          2 ** (q - p), family="cidr", topic="networks", level=level)
        return number(f"Сеть /{p} разбита на равные подсети /{q}. Сколько адресов хостов (без сетевого и широковещательного) в каждой подсети?",
                      2 ** (32 - q) - 2, family="cidr", topic="networks", level=level)
    p = rng.randint(26, 29)
    net = ipaddress.ip_network(f"192.168.{rng.randint(0, 255)}.{rng.randint(1, 250)}/{p}", strict=False)
    ip = ipaddress.ip_address(int(net.network_address) + rng.randint(1, net.num_addresses - 2))
    return number(f"Хост имеет адрес {ip}/{p}. Чему равен последний октет широковещательного адреса его подсети?",
                  int(net.broadcast_address) & 255, family="cidr", topic="networks", level=level)


# =========================================================================== BACKEND
def g_token_bucket(rng, level):
    cap, rate = rng.randint(3, 6), rng.randint(1, 3)
    times = sorted(rng.choices(range(0, 13), k=rng.randint(10, 14)))
    tokens, last, allowed = float(cap), 0, 0
    for t in times:
        tokens = min(cap, tokens + (t - last) * rate)
        last = t
        if tokens >= 1:
            tokens -= 1; allowed += 1
    return number(f"Ограничитель запросов «token bucket»: ёмкость {cap} токенов, пополнение {rate} токен(а) в секунду "
                  f"(непрерывное, не выше ёмкости), в начале бакет полон. Каждый запрос тратит 1 токен; без токена запрос отклоняется. "
                  f"Запросы пришли в секунды: `{times}`. Сколько запросов будет принято?",
                  allowed, family="token_bucket", topic="backend_arch", level=level)


def g_cache_latency(rng, level):
    h, c, d = rng.randint(50, 99), rng.randint(1, 10), rng.randrange(20, 205, 5)
    if level <= 2:
        val = h / 100 * c + (1 - h / 100) * d
        return number(f"Доля попаданий в кэш — {h}%. Время ответа кэша — {c} мс, базы данных — {d} мс. "
                      f"Каково среднее время ответа (мс)? Округлите до сотых.", round(val, 2), tol=0.011,
                      family="cache_latency", topic="backend_arch", level=level)
    h2 = rng.randint(30, 70)
    c2 = rng.randint(5, 15)
    val = h / 100 * c + (1 - h / 100) * (h2 / 100 * c2 + (1 - h2 / 100) * d)
    return number(f"Двухуровневый кэш: L1 — попадание {h}% ({c} мс); при промахе запрос идёт в L2 — попадание {h2}% ({c2} мс); "
                  f"при промахе L2 — в БД ({d} мс). Среднее время ответа (мс), округлить до сотых?",
                  round(val, 2), tol=0.011, family="cache_latency", topic="backend_arch", level=level)


def g_shards(rng, level):
    n = rng.randint(3, 5)
    keys = rng.sample(range(10, 500), rng.randint(10, 13))
    k = rng.randrange(n)
    if level <= 2:
        cnt = sum(1 for x in keys if x % n == k)
        return number(f"Ключи распределяются по {n} шардам по формуле `shard = key % {n}`. Сколько ключей из `{keys}` попадёт на шард №{k}?",
                      cnt, family="shards", topic="backend_arch", level=level)
    a, b = rng.randint(3, 9), rng.randint(1, 9)
    cnt = sum(1 for x in keys if (x * a + b) % n == k)
    return number(f"Шард выбирается по формуле `shard = (key * {a} + {b}) % {n}`. Сколько ключей из `{keys}` попадёт на шард №{k}?",
                  cnt, family="shards", topic="backend_arch", level=level)


def g_backoff(rng, level):
    base, f, r = rng.randrange(50, 1001, 25), rng.choice([2, 3]), rng.randint(4, 8)
    if level <= 2:
        total = sum(base * f ** i for i in range(r))
        return number(f"Клиент повторяет неуспешный запрос с экспоненциальной задержкой: первая пауза {base} мс, каждая следующая в {f} раза больше. "
                      f"Сколько всего миллисекунд клиент прождёт между {r + 1} попытками (всего {r} пауз)?",
                      total, family="backoff", topic="web", level=level)
    cap = base * f ** rng.randint(1, 2)
    total = sum(min(base * f ** i, cap) for i in range(r + 2))
    return number(f"Экспоненциальная задержка: первая пауза {base} мс, множитель {f}, но каждая пауза не превышает {cap} мс. "
                  f"Сколько мс клиент прождёт суммарно за {r + 2} паузы?", total, family="backoff", topic="web", level=level)


def g_little(rng, level):
    lam, w = rng.randrange(30, 301, 10), rng.randrange(20, 301, 10)
    conc = lam * w / 1000
    if level <= 3:
        return number(f"Сервис обрабатывает {lam} запросов в секунду, среднее время обработки — {w} мс. "
                      f"Сколько запросов в среднем одновременно находится в системе (закон Литтла)? Округлите до десятых.",
                      round(conc, 1), tol=0.11, family="little", topic="backend_arch", level=level)
    util = rng.choice([0.5, 0.8])
    workers = math.ceil(conc / util)
    return number(f"Нагрузка {lam} запросов/с, среднее время обработки {w} мс, один воркер обрабатывает один запрос за раз. "
                  f"Сколько воркеров нужно, чтобы средняя загрузка не превышала {int(util * 100)}%? (округлить вверх)",
                  workers, family="little", topic="backend_arch", level=level)


# =========================================================================== FRONTEND
def _spec(parts):
    return (parts[0], parts[1], parts[2])


_SEL = [("#nav .item", (1, 1, 0)), ("div p", (0, 0, 2)), (".card.active", (0, 2, 0)), ("ul li.active", (0, 1, 2)),
        ("#app", (1, 0, 0)), ("body main .btn", (0, 1, 2)), ("a:hover", (0, 1, 1)), ("input[type=\"text\"]", (0, 1, 1)),
        (".list > li:first-child", (0, 2, 1)), ("#hero h1", (1, 0, 1)), ("p", (0, 0, 1)), (".btn.primary:hover", (0, 3, 0)),
        ("section article p.note", (0, 1, 3)), ("#a #b", (2, 0, 0)), (":not(#x) p", (1, 0, 1))]


def g_specificity(rng, level):
    k = 4
    pool = _SEL if level >= 3 else [s for s in _SEL if ":" not in s[0] and "[" not in s[0] and ">" not in s[0]]
    for _ in range(50):
        pick = rng.sample(pool, k)
        top = max(p[1] for p in pick)
        if sum(1 for p in pick if p[1] == top) == 1:
            break
    win = next(p[0] for p in pick if p[1] == top)
    return choice(rng, "К одному и тому же элементу подходят все четыре селектора ниже (`!important` нет, стили подключены "
                       "в произвольном порядке). Какой из селекторов победит по специфичности?", f"`{win}`",
                  [f"`{p[0]}`" for p in pick if p[0] != win], family="specificity", topic="css", level=level)


def g_boxmodel(rng, level):
    w, p, b, m = rng.randrange(120, 421, 10), rng.randrange(8, 31, 2), rng.randint(1, 8), rng.randrange(0, 41, 5)
    if level == 1:
        return number(f"Блок: `width: {w}px; padding: {p}px; border: {b}px solid; box-sizing: content-box;`. Какую ширину (px) он займёт без учёта margin?",
                      w + 2 * p + 2 * b, family="boxmodel", topic="css", level=level)
    bs = rng.choice(["content-box", "border-box"])
    total = (w + 2 * p + 2 * b if bs == "content-box" else w) + 2 * m
    return number(f"Блок: `width: {w}px; padding: {p}px; border: {b}px solid; margin: 0 {m}px; box-sizing: {bs};`. "
                  f"Сколько горизонтального места (px) он занимает вместе с margin?", total, family="boxmodel", topic="css", level=level)


def g_js_array(rng, level):
    arr = [rng.randint(1, 20) for _ in range(rng.randint(6, 9))]
    if level == 1:
        m, r, kk = rng.randint(2, 4), 0, rng.randint(2, 4)
        code = f"[{', '.join(map(str, arr))}]\n  .filter(x => x % {m} === {r})\n  .map(x => x * {kk})\n  .reduce((s, x) => s + x, 0)"
        val = sum(x * kk for x in arr if x % m == r)
        return number("Чему равно значение выражения JavaScript?\n\n" + _code(code, "javascript"), val,
                      family="js_array", topic="javascript", level=level)
    if level == 2:
        a, b = rng.randint(1, 3), rng.randint(5, 8)
        code = f"const a = [{', '.join(map(str, arr))}];\nconst r = a.slice({a}, {b}).some(x => x > 12) ? a.length : a.indexOf({arr[0]});"
        sl = arr[a:b]
        val = len(arr) if any(x > 12 for x in sl) else arr.index(arr[0])
        return number("Чему равна переменная `r`?\n\n" + _code(code, "javascript"), val, family="js_array",
                      topic="javascript", level=level)
    if level == 3:
        arr = rng.sample([1, 2, 3, 5, 9, 10, 11, 25, 100, 20, 30, 7], 6)
        idx = rng.randint(0, 5)
        srt = sorted(arr, key=str)
        return number(f"Что вернёт `[{', '.join(map(str, arr))}].sort()[{idx}]` в JavaScript? "
                      f"(напомним: `sort()` без аргумента сравнивает элементы как строки)", int(srt[idx]),
                      family="js_array", topic="javascript", level=level)
    n, kw, mult = rng.randint(3, 12), rng.choice(["var", "let"]), rng.randint(1, 9)
    code = (f"const out = [];\nfor ({kw} i = 0; i < {n}; i++) {{\n  setTimeout(() => out.push(i * {mult}), 0);\n}}\n"
            f"// после выполнения всех таймеров\nconsole.log(out.reduce((s, x) => s + x, 0));")
    val = (n * n if kw == "var" else n * (n - 1) // 2) * mult
    return number("Что будет выведено в консоль?\n\n" + _code(code, "javascript"), val, family="js_array",
                  topic="javascript", level=level)


def g_event_loop(rng, level):
    labels = rng.sample("ABCDEFGH", 5 if level == 3 else 6)
    items = []
    code = []
    sync_labels, micro, timers = [], [], []
    li = iter(labels)
    a = next(li); code.append(f"console.log('{a}');"); sync_labels.append(a)
    b = next(li); d_b = rng.choice([0, 0, 10])
    code.append(f"setTimeout(() => console.log('{b}'), {d_b});"); timers.append((d_b, len(timers), b))
    c = next(li); code.append(f"Promise.resolve().then(() => console.log('{c}'));"); micro.append(c)
    d = next(li); code.append(f"setTimeout(() => console.log('{d}'), 0);"); timers.append((0, len(timers), d))
    e = next(li); code.append(f"console.log('{e}');"); sync_labels.append(e)
    micro_order = list(micro)
    if level == 4:
        f = next(li)
        g = rng.choice([x for x in "XYZW" if x not in labels])
        code.insert(3, f"Promise.resolve().then(() => {{ console.log('{f}'); queueMicrotask(() => console.log('{g}')); }});")
        micro_order = [c, f, g]
    # порядок: синхронные -> микротаски (включая вложенные) -> таймеры по (delay, порядок)
    order = sync_labels + micro_order + [t[2] for t in sorted(timers)]
    answer = " → ".join(order)
    wrongs = set()
    attempts = 0
    while len(wrongs) < 3 and attempts < 40:
        attempts += 1
        w = list(order)
        i, j = rng.sample(range(len(w)), 2)
        w[i], w[j] = w[j], w[i]
        s = " → ".join(w)
        if s != answer:
            wrongs.add(s)
    return choice(rng, "В каком порядке выведутся строки в консоль (Node.js / браузер)?\n\n" + _code("\n".join(code), "javascript"),
                  answer, sorted(wrongs), family="event_loop", topic="javascript", level=level)


# =========================================================================== DATA
def g_stats(rng, level):
    data = [rng.randint(1, 20) for _ in range(rng.choice([7, 9, 11]))]
    srt = sorted(data)
    if level == 1:
        what = rng.choice(["mean", "median"])
        if what == "mean":
            while sum(data) % len(data):
                data[rng.randrange(len(data))] += 1
            return number(f"Чему равно среднее арифметическое выборки `{data}`?", sum(data) // len(data),
                          family="stats", topic="statistics", level=level)
        return number(f"Чему равна медиана выборки `{data}`?", srt[len(srt) // 2], family="stats", topic="statistics", level=level)
    if level == 2:
        mean = sum(data) / len(data)
        var = sum((x - mean) ** 2 for x in data) / len(data)
        return number(f"Чему равна дисперсия (генеральная, деление на n) выборки `{data}`? Округлите до сотых.",
                      round(var, 2), tol=0.011, family="stats", topic="statistics", level=level)
    mean = sum(data) / len(data)
    sd = math.sqrt(sum((x - mean) ** 2 for x in data) / (len(data) - 1))
    return number(f"Чему равно выборочное стандартное отклонение (деление на n−1) для `{data}`? Округлите до сотых.",
                  round(sd, 2), tol=0.021, family="stats", topic="statistics", level=3 if level == 3 else level)


def g_confusion(rng, level):
    tp, fp, fn, tn = rng.randint(20, 90), rng.randint(5, 40), rng.randint(5, 40), rng.randint(30, 150)
    which = rng.choice(["precision", "recall"] if level == 2 else ["f1", "precision", "recall"])
    p, r = tp / (tp + fp), tp / (tp + fn)
    val = {"precision": p, "recall": r, "f1": 2 * p * r / (p + r)}[which]
    names = {"precision": "precision (точность)", "recall": "recall (полноту)", "f1": "F1-меру"}
    return number(f"Матрица ошибок бинарного классификатора: TP = {tp}, FP = {fp}, FN = {fn}, TN = {tn}. Чему равна {names[which]}? "
                  f"Округлите до сотых.", round(val, 2), tol=0.011, family="confusion", topic="ml", level=level)


def g_bayes(rng, level):
    prev, sens, spec = rng.choice([0.5, 1, 1.5, 2, 3, 4, 5, 8, 10]), rng.randint(80, 99), rng.randint(80, 99)
    p, se, sp = prev / 100, sens / 100, spec / 100
    val = se * p / (se * p + (1 - sp) * (1 - p)) * 100
    return number(f"Заболевание встречается у {prev}% населения. Тест выявляет больных с вероятностью {sens}% (чувствительность) и "
                  f"даёт верный отрицательный результат у здоровых с вероятностью {spec}% (специфичность). "
                  f"Какова вероятность (в %), что человек с положительным тестом действительно болен? Округлите до десятых.",
                  round(val, 1), tol=0.11, family="bayes", topic="statistics", level=level)


def g_scaling(rng, level):
    lo, hi = rng.randint(0, 20), rng.randint(60, 120)
    x = rng.randint(lo + 5, hi - 5)
    if level == 1:
        return number(f"Признак принимает значения от {lo} до {hi}. Чему равно значение {x} после min-max нормализации в [0, 1]? Округлите до сотых.",
                      round((x - lo) / (hi - lo), 2), tol=0.011, family="scaling", topic="ml", level=level)
    mu, sd = rng.randint(40, 70), rng.choice([5, 8, 10, 12])
    return number(f"Признак имеет среднее {mu} и стандартное отклонение {sd}. Чему равно z-значение для x = {x}? Округлите до сотых.",
                  round((x - mu) / sd, 2), tol=0.011, family="scaling", topic="ml", level=2 if level == 2 else level)


# =========================================================================== DEVOPS
def _expand(field: str, lo: int, hi: int) -> set:
    vals = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, st = part.split("/"); step = int(st)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, b = map(int, part.split("-"))
        else:
            a = b = int(part)
            if step != 1:
                b = hi
        vals.update(range(a, b + 1, step))
    return vals


def g_cron(rng, level):
    steps = [5, 6, 8, 10, 12, 15, 20, 25, 30]
    if level == 2:
        mins = rng.choice([f"*/{n}" for n in (5, 10, 12, 15, 20, 30)] + [str(m) for m in range(0, 60, 5)] + ["0,30", "15,45"])
        a = rng.randint(0, 12)
        hrs = rng.choice(["*", f"{a}-{a + rng.randint(2, 9)}", f"*/{rng.randint(2, 8)}"])
        dow = "*"
    elif level == 3:
        mins = rng.choice([f"*/{n}" for n in steps] + ["0,30", "10,40", "5,25,45"])
        a = rng.randint(0, 14)
        hrs = rng.choice(["*", f"{a}-{a + rng.randint(2, 9)}", f"*/{rng.randint(2, 8)}", f"{a},{a + 6}"])
        dow = rng.choice(["*", "1-5", "0,6", "1,3,5"])
    else:
        mins = rng.choice(["*/7", "*/9", "*/11", "*/13", "*/17", "*/25", "*/40", "*/45"])
        a = rng.randint(0, 14)
        hrs = rng.choice(["*", f"{a}-{a + rng.randint(2, 9)}", f"*/{rng.randint(3, 8)}"])
        dow = rng.choice(["*", "1-5", "1,3,5"])
    per_day = len(_expand(mins, 0, 59)) * len(_expand(hrs, 0, 23))
    if level == 2:
        return number(f"Сколько раз в сутки сработает cron-выражение `{mins} {hrs} * * *`?", per_day, family="cron", topic="linux", level=level)
    days = len(_expand(dow, 0, 6)) if dow != "*" else 7
    return number(f"Сколько раз за неделю (7 суток) сработает cron-выражение `{mins} {hrs} * * {dow}`?", per_day * days,
                  family="cron", topic="linux", level=level)


def _sym(octal: int) -> str:
    out = ""
    for digit in str(octal):
        d = int(digit)
        out += ("r" if d & 4 else "-") + ("w" if d & 2 else "-") + ("x" if d & 1 else "-")
    return out


def g_chmod(rng, level):
    if level <= 2:
        o = int("".join(str(rng.choice([4, 5, 6, 7, 0, 1])) for _ in range(3)))
        mode = _sym(o)
        wrongs = []
        for _ in range(8):
            w = int("".join(str(rng.choice([4, 5, 6, 7, 0, 1])) for _ in range(3)))
            if w != o:
                wrongs.append(_sym(w))
        return choice(rng, f"Какому символьному представлению соответствует `chmod {o:03d}`?", mode, wrongs,
                      family="chmod", topic="linux", level=level)
    base = rng.choice([666, 777, 644, 755])
    um = int("".join(str(rng.randint(0, 7)) for _ in range(3)))
    res = int("".join(str(int(b) & ~int(u) & 7) for b, u in zip(str(base), f"{um:03d}")))
    return number(f"Процесс создаёт файл с правами {base} при `umask {um:03d}`. Какие права (восьмеричное число, например 644) получит файл?",
                  res, family="chmod", topic="linux", level=level)


def g_sla(rng, level):
    a = round(rng.uniform(98.0, 99.99), 2)
    if level <= 2:
        days = rng.randint(28, 31)
        return number(f"SLA доступности {a}%. Сколько минут простоя допускается за {days} суток? Округлите до десятых.",
                      round(days * 24 * 60 * (1 - a / 100), 1), tol=0.11, family="sla", topic="devops", level=level)
    a2 = round(rng.uniform(98.5, 99.9), 2)
    if level == 3:
        return number(f"Сервис зависит последовательно от двух компонентов с доступностью {a}% и {a2}%. Какова общая доступность (%)? Округлите до сотых.",
                      round(a * a2 / 100, 2), tol=0.011, family="sla", topic="devops", level=level)
    a3 = round(rng.uniform(90.0, 99.0), 1)
    return number(f"Два независимых экземпляра сервиса работают параллельно (достаточно одного), доступность каждого {a3}%. Какова общая доступность (%)? Округлите до сотых.",
                  round((1 - (1 - a3 / 100) ** 2) * 100, 2), tol=0.011, family="sla", topic="devops", level=level)


def g_rollout(rng, level):
    r = rng.randint(4, 40)
    if level == 3:
        s, u = rng.randint(1, 5), rng.randint(0, 4)
        which = rng.choice(["max", "min"])
        return number(f"Deployment на {r} реплик, стратегия RollingUpdate: maxSurge = {s}, maxUnavailable = {u}. "
                      f"{'Какое максимальное число подов может существовать одновременно' if which == 'max' else 'Какое минимальное число доступных подов гарантируется'} в ходе обновления?",
                      r + s if which == "max" else r - u, family="rollout", topic="devops", level=level)
    ps, pu = rng.randrange(10, 61, 5), rng.randrange(10, 61, 5)
    r = rng.randint(5, 40)
    surge, unav = math.ceil(r * ps / 100), math.floor(r * pu / 100)
    which = rng.choice(["max", "min"])
    return number(f"Deployment на {r} реплик, RollingUpdate: maxSurge = {ps}%, maxUnavailable = {pu}% "
                  f"(Kubernetes округляет surge вверх, unavailable вниз). "
                  f"{'Какое максимальное число подов может существовать одновременно' if which == 'max' else 'Какое минимальное число доступных подов гарантируется'}?",
                  r + surge if which == "max" else r - unav, family="rollout", topic="devops", level=4)


def g_grep(rng, level):
    lv, svc = ["INFO", "WARN", "ERROR"], ["db", "api", "auth", "cache"]
    msgs = ["timeout", "retry", "ok", "failed", "slow", "login"]
    lines = [f"12:{i:02d}:{rng.randint(0, 59):02d} {rng.choice(lv)} {rng.choice(svc)} {rng.choice(msgs)}" for i in range(rng.randint(10, 13))]
    log = "\n".join(lines)
    if level == 1:
        cmd, val = 'grep -c "ERROR" app.log', sum("ERROR" in l for l in lines)
    elif level == 2:
        cmd, val = 'grep -v "INFO" app.log | wc -l', sum("INFO" not in l for l in lines)
    elif level == 3:
        cmd, val = 'grep -E "ERROR|WARN" app.log | grep -c "db"', sum(bool(re.search("ERROR|WARN", l)) and "db" in l for l in lines)
    else:
        cmd, val = 'grep -w "db" app.log | grep -v "ok" | wc -l', sum(bool(re.search(r"\bdb\b", l)) and "ok" not in l for l in lines)
    return number(f"Файл `app.log`:\n\n```\n{log}\n```\n\nЧто выведет команда `{cmd}`?", val, family="grep", topic="linux", level=level)


# =========================================================================== QA
def g_equiv(rng, level):
    tiers = rng.randint(3, 5)
    cuts = sorted(rng.sample(range(100, 5000, 100), tiers - 1))
    desc = f"Скидка зависит от суммы заказа: от 0 до {cuts[0]} — 0%"
    for i, c in enumerate(cuts):
        nxt = f"до {cuts[i + 1]}" if i + 1 < len(cuts) else "и выше"
        desc += f"; от {c} {nxt} — {5 * (i + 1)}%"
    desc += ". Отрицательные суммы и нечисловой ввод недопустимы."
    return number(desc + " Сколько классов эквивалентности (валидных и невалидных) нужно покрыть?", tiers + 2,
                  family="equiv", topic="qa_theory", level=level)


def g_coverage(rng, level):
    if level == 1:
        total, hit = rng.randint(20, 40), None
        hit = rng.randint(total // 2, total - 2)
        return number(f"В функции {total} выполняемых операторов; тесты суммарно выполнили {hit} из них. Каково покрытие операторов (statement coverage), %? Округлите до целого.",
                      round(hit / total * 100), tol=0.51, family="coverage", topic="qa_theory", level=level)
    if level == 2:
        dec = rng.randint(4, 16)
        taken = rng.randint(dec, 2 * dec - 1)
        return number(f"В коде {dec} условных переходов (if), каждый имеет две ветви. Тесты прошли по {taken} различным ветвям. Каково покрытие ветвей (branch coverage), %? Округлите до целого.",
                      round(taken / (2 * dec) * 100), tol=0.51, family="coverage", topic="qa_theory", level=level)
    nif, nfor, nwhile, nand = rng.randint(1, 5), rng.randint(0, 3), rng.randint(0, 3), rng.randint(0, 3)
    lines = ["def f(a, b, items):", "    r = 0"]
    for i in range(nif):
        lines.append(f"    if a > {i}:\n        r += 1")
    for _ in range(nfor):
        lines.append("    for x in items:\n        r += x")
    for _ in range(nwhile):
        lines.append("    while b > 0:\n        b -= 1")
    for i in range(nand):
        lines.append(f"    if a > {i} {rng.choice(['and', 'or'])} b < {i + 5}:\n        r -= 1")
    lines.append("    return r")
    decisions = nif + nfor + nwhile + nand * 2   # каждое if с and/or даёт 2 предиката
    return number("Чему равна цикломатическая сложность функции (число предикатов + 1; составное условие `and`/`or` считается как два предиката)?\n\n"
                  + _code("\n".join(lines)), decisions + 1, family="coverage", topic="qa_theory", level=4 if level >= 4 else 3)


def g_defects(rng, level):
    if level <= 2:
        d, kloc = rng.randint(20, 90), rng.choice([4, 5, 8, 10, 12])
        return number(f"В модуле {kloc * 1000} строк кода найдено {d} дефектов. Чему равна плотность дефектов (на 1000 строк)? Округлите до десятых.",
                      round(d / kloc, 1), tol=0.11, family="defects", topic="qa_theory", level=level)
    before, after = rng.randint(40, 120), rng.randint(5, 30)
    return number(f"До релиза команда нашла {before} дефектов, после релиза пользователи нашли ещё {after}. Чему равна эффективность удаления дефектов DRE (%)? Округлите до целого.",
                  round(before / (before + after) * 100), tol=0.51, family="defects", topic="qa_theory", level=level)


# =========================================================================== КОНЦЕПТУАЛЬНЫЕ ПУЛЫ
# (уровень, тема, вопрос, верный, [неверные]) — не более ~25% теста, варианты перемешиваются.
POOLS = {
    "common": [
        (1, "web", "Какая команда git отправляет локальные коммиты в удалённый репозиторий?", "git push", ["git commit", "git fetch", "git stash"]),
        (1, "python", "Какой из типов Python изменяемый?", "list", ["tuple", "str", "frozenset"]),
        (2, "web", "Чем `git rebase` отличается от `git merge`?", "rebase переносит коммиты поверх другой ветки, переписывая историю; merge создаёт коммит слияния",
         ["rebase удаляет удалённую ветку, merge — локальную", "merge переписывает историю, rebase — нет", "они всегда дают идентичную историю"]),
        (2, "python", "Что может быть ключом словаря в Python?", "tuple из чисел", ["list", "set", "dict"]),
        (2, "web", "Какой код ответа HTTP означает «ресурс создан»?", "201", ["200", "204", "302"]),
        (3, "python", "Что делает GIL в CPython?", "не даёт нескольким потокам одновременно выполнять байт-код Python",
         ["ускоряет ввод-вывод за счёт кэширования", "запрещает использовать потоки", "разрешает только один процесс на машине"]),
        (3, "web", "Для чего нужен заголовок `Idempotency-Key` при POST-запросах платежей?", "чтобы повтор запроса не создал дубликат операции",
         ["чтобы ускорить ответ сервера", "чтобы зашифровать тело запроса", "чтобы включить HTTP/2"]),
        (4, "python", "Почему `def f(x, acc=[])` — опасная сигнатура?", "список по умолчанию создаётся один раз и разделяется между вызовами",
         ["список копируется при каждом вызове и тормозит программу", "Python запрещает изменяемые значения по умолчанию", "аргумент acc нельзя передать позиционно"]),
        (4, "web", "Что означает гарантия «at-least-once» при доставке сообщений?", "сообщение доставляется минимум один раз, возможны дубликаты",
         ["сообщение доставляется ровно один раз", "сообщение может быть потеряно, но не дублируется", "порядок сообщений всегда сохраняется"]),
    ],
    "backend": [
        (1, "web", "Какой HTTP-метод по определению безопасен и идемпотентен?", "GET", ["POST", "PATCH", "DELETE"]),
        (2, "sql", "Какой индекс лучше всего ускорит `WHERE email = ? ORDER BY created_at` на большой таблице?", "составной индекс (email, created_at)",
         ["индекс только по created_at", "два отдельных хеш-индекса", "индекс не поможет"]),
        (2, "backend_arch", "В чём суть проблемы N+1 запросов?", "на каждый из N объектов выполняется отдельный запрос вместо одного JOIN/IN",
         ["N запросов блокируют друг друга", "запрос выполняется N раз из-за ретраев", "N+1 соединение с БД превышает пул"]),
        (3, "sql", "Что гарантирует уровень изоляции Read Committed?", "транзакция не видит незафиксированные изменения других транзакций",
         ["строки не меняются другими транзакциями до конца транзакции", "отсутствие фантомных строк", "последовательное выполнение всех транзакций"]),
        (3, "web", "Чем PUT отличается от PATCH?", "PUT заменяет ресурс целиком, PATCH применяет частичное изменение",
         ["PUT только создаёт, PATCH только удаляет", "PATCH идемпотентен всегда, PUT — никогда", "отличий нет"]),
        (4, "backend_arch", "Для чего применяют паттерн Transactional Outbox?", "чтобы атомарно сохранить изменение в БД и событие для брокера",
         ["чтобы шифровать сообщения брокера", "чтобы ускорить чтение из реплик", "чтобы шардировать таблицы"]),
        (4, "backend_arch", "Что такое cache stampede и как его смягчают?", "лавина запросов к БД при одновременном истечении ключа; блокировкой пересборки или jitter в TTL",
         ["переполнение кэша; увеличением памяти", "потеря ключей при рестарте; репликацией", "конфликт версий; оптимистичной блокировкой"]),
    ],
    "frontend": [
        (1, "css", "Какой HTML-тег семантически предназначен для основной навигации?", "<nav>", ["<menu-block>", "<div id=\"nav\">", "<header>"]),
        (2, "css", "Что делает `box-sizing: border-box`?", "ширина и высота включают padding и border", ["убирает отступы между блоками", "делает границы скруглёнными", "включает Flexbox"]),
        (2, "javascript", "Чем `let` отличается от `var`?", "у `let` блочная область видимости, у `var` — функциональная", ["`let` нельзя переприсваивать", "`var` появился позже", "отличий нет"]),
        (3, "web", "Что такое reflow (layout) в браузере?", "пересчёт геометрии элементов при изменении DOM/стилей", ["загрузка скриптов", "сжатие изображений", "обновление Service Worker"]),
        (3, "javascript", "Что делает `useEffect(fn, [])` в React?", "вызывает fn один раз после первого рендера", ["вызывает fn при каждом рендере", "вызывает fn перед каждым рендером", "никогда не вызывает fn"]),
        (4, "web", "Что такое hydration при SSR?", "навешивание обработчиков и состояния на уже отрендеренный на сервере HTML", ["сжатие HTML на сервере", "ленивая загрузка картинок", "кэширование API"]),
        (4, "web", "Почему блокирующий CSS замедляет первую отрисовку?", "браузер не рисует страницу, пока не построит CSSOM", ["CSS выполняется как JS в основном потоке", "CSS всегда грузится после DOM", "браузер не поддерживает параллельную загрузку"]),
    ],
    "data": [
        (1, "ml", "Что такое переобучение (overfitting)?", "модель хорошо работает на обучающей выборке и плохо на новых данных", ["модель плохо работает на всех данных", "обучение прекращается досрочно", "слишком мало признаков"]),
        (2, "ml", "Зачем нужна кросс-валидация?", "для более надёжной оценки обобщающей способности модели", ["для ускорения обучения", "для увеличения числа признаков", "для замены тестовой выборки обучающей"]),
        (2, "statistics", "Как правильно интерпретировать p-value?", "вероятность получить такие или более экстремальные данные при верной нулевой гипотезе", ["вероятность того, что нулевая гипотеза верна", "вероятность ошибки модели", "доля объяснённой дисперсии"]),
        (3, "ml", "Чем L1-регуляризация отличается от L2?", "L1 способна обнулять коэффициенты (отбор признаков), L2 лишь уменьшает их", ["L2 обнуляет коэффициенты, L1 нет", "L1 применяется только к деревьям", "отличий нет"]),
        (3, "ml", "Что показывает ROC-AUC?", "способность модели ранжировать положительные объекты выше отрицательных", ["долю правильных ответов", "среднюю ошибку прогноза", "число ложноотрицательных"]),
        (4, "ml", "Что такое утечка данных (data leakage)?", "попадание в обучение информации, недоступной в момент реального прогноза", ["потеря строк при слиянии таблиц", "раскрытие персональных данных", "переполнение памяти"]),
    ],
    "devops": [
        (1, "devops", "Чем образ Docker отличается от контейнера?", "образ — неизменяемый шаблон, контейнер — запущенный экземпляр образа", ["это одно и то же", "контейнер — файл, образ — процесс", "образ работает только на Linux"]),
        (2, "devops", "Для чего в Kubernetes нужна readiness-проба?", "чтобы трафик шёл на под только когда он готов принимать запросы", ["чтобы перезапускать зависший под", "чтобы масштабировать под", "чтобы монтировать тома"]),
        (2, "devops", "Что означает подход Infrastructure as Code?", "описание и управление инфраструктурой через версионируемые файлы конфигурации", ["хранение паролей в коде", "запуск кода на серверах без CI", "ручная настройка по инструкции"]),
        (3, "devops", "Чем canary-выкатка отличается от blue-green?", "canary направляет на новую версию малую долю трафика, blue-green переключает всё разом между двумя средами", ["canary требует остановки сервиса", "blue-green работает только в облаке", "это синонимы"]),
        (3, "devops", "Зачем нужен remote state и блокировка состояния в Terraform?", "чтобы команда делала изменения согласованно и без гонок", ["чтобы ускорить plan", "чтобы шифровать провайдеры", "чтобы запускать код в контейнере"]),
        (4, "devops", "Чем SLI отличается от SLO?", "SLI — измеряемая метрика качества, SLO — целевое значение этой метрики", ["SLO — договор с клиентом, SLI — штраф", "SLI — бюджет ошибок, SLO — алерт", "это синонимы"]),
    ],
    "qa": [
        (1, "qa_theory", "Что такое регрессионное тестирование?", "проверка, что изменения не сломали ранее работавшую функциональность", ["тестирование нагрузки", "тестирование только нового кода", "проверка вёрстки"]),
        (2, "qa_theory", "Чем severity отличается от priority дефекта?", "severity — влияние на систему, priority — срочность исправления", ["это синонимы", "priority определяет разработчик, severity — менеджер всегда", "severity — это номер релиза"]),
        (2, "qa_theory", "О чём говорит пирамида тестирования?", "больше быстрых юнит-тестов, меньше интеграционных, ещё меньше UI-тестов", ["UI-тестов должно быть больше всего", "тесты нужно писать только на верхнем уровне", "пирамида про приоритеты багов"]),
        (3, "qa_theory", "Что такое flaky-тест и как с ним бороться?", "тест с нестабильным результатом без изменений кода; изолируют окружение, убирают зависимость от времени/порядка", ["тест, который всегда падает; его удаляют", "медленный тест; его распараллеливают", "тест без проверок"]),
        (3, "qa_theory", "Чем smoke-тестирование отличается от sanity?", "smoke — быстрая проверка критичных функций сборки, sanity — узкая проверка конкретного исправления", ["это синонимы", "sanity — нагрузочное, smoke — безопасность", "smoke выполняют только в production"]),
        (4, "qa_theory", "Что такое мутационное тестирование?", "в код вносят небольшие изменения (мутанты) и проверяют, что тесты их ловят", ["случайные входные данные для UI", "тестирование на разных ОС", "проверка миграций БД"]),
        (4, "qa_theory", "Зачем нужны контрактные тесты (consumer-driven)?", "чтобы проверять совместимость API между сервисами без полного интеграционного стенда", ["чтобы тестировать юридические договоры", "чтобы заменить unit-тесты", "чтобы измерять производительность"]),
    ],
}


def g_pool(spec: Optional[str]):
    def gen(rng, level):
        items = [it for it in (POOLS["common"] + (POOLS.get(spec, []) if spec else [])) if it[0] == level]
        lv, topic, prompt, correct, wrongs = rng.choice(items)
        return choice(rng, prompt, correct, list(wrongs), family="pool", topic=topic, level=level)
    return gen


# =========================================================================== РЕЕСТР СЕМЕЙСТВ
@dataclass
class Family:
    name: str
    levels: tuple
    fn: Callable
    specs: Optional[tuple] = None  # None = общее для всех специализаций
    weight: float = 1.0


COMMON = [
    Family("py_trace", (1, 2, 3, 4), g_py_trace), Family("big_o_ops", (1, 2, 3, 4), g_big_o_ops),
    Family("binsearch", (2, 3, 4), g_binsearch), Family("sort_count", (1, 2, 3, 4), g_sort_count),
    Family("struct_sim", (1, 2, 3, 4), g_struct_sim), Family("sql_exec", (1, 2, 3, 4), g_sql_exec, weight=0.9),
    Family("regex", (1, 2, 3, 4), g_regex, weight=0.8), Family("bits", (1, 2, 3, 4), g_bits, weight=0.7),
    Family("graph", (2, 3, 4), g_graph), Family("dp", (2, 3, 4), g_dp), Family("cidr", (1, 2, 3, 4), g_cidr, weight=0.7),
]
SPEC_FAMILIES = {
    "backend": [Family("token_bucket", (3, 4), g_token_bucket, ("backend",), 1.8), Family("cache_latency", (1, 2, 3), g_cache_latency, ("backend",), 1.8),
                Family("shards", (2, 3), g_shards, ("backend",), 1.6), Family("backoff", (2, 3), g_backoff, ("backend",), 1.6),
                Family("little", (3, 4), g_little, ("backend",), 1.6), Family("sql_exec", (1, 2, 3, 4), g_sql_exec, ("backend",), 1.4)],
    "frontend": [Family("specificity", (2, 3), g_specificity, ("frontend",), 2.0), Family("boxmodel", (1, 2), g_boxmodel, ("frontend",), 1.8),
                 Family("js_array", (1, 2, 3, 4), g_js_array, ("frontend",), 2.2), Family("event_loop", (3, 4), g_event_loop, ("frontend",), 2.0)],
    "data": [Family("stats", (1, 2, 3), g_stats, ("data",), 2.0), Family("confusion", (2, 3), g_confusion, ("data",), 1.8),
             Family("bayes", (3, 4), g_bayes, ("data",), 1.6), Family("scaling", (1, 2), g_scaling, ("data",), 1.5),
             Family("sql_exec", (1, 2, 3, 4), g_sql_exec, ("data",), 1.8)],
    "devops": [Family("cron", (2, 3, 4), g_cron, ("devops",), 1.8), Family("chmod", (1, 2, 3), g_chmod, ("devops",), 1.6),
               Family("sla", (2, 3, 4), g_sla, ("devops",), 1.6), Family("rollout", (3, 4), g_rollout, ("devops",), 1.6),
               Family("grep", (1, 2, 3, 4), g_grep, ("devops",), 1.8), Family("cidr", (1, 2, 3, 4), g_cidr, ("devops",), 1.6)],
    "qa": [Family("equiv", (2,), g_equiv, ("qa",), 2.0), Family("coverage", (1, 2, 3, 4), g_coverage, ("qa",), 2.0),
           Family("defects", (1, 2, 3), g_defects, ("qa",), 1.5), Family("grep", (1, 2, 3, 4), g_grep, ("qa",), 1.4),
           Family("regex", (1, 2, 3, 4), g_regex, ("qa",), 1.3)],
}


def families_for(spec: str) -> list[Family]:
    """Общие + специфичные семейства + концептуальный пул (его вес мал: ≤ ~25% теста, см. engine)."""
    return COMMON + SPEC_FAMILIES.get(spec, []) + [Family("pool", (1, 2, 3, 4), g_pool(spec), None, 0.55)]
