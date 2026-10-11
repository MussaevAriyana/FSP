"""Сложные семейства заданий (уровни 4–5): многошаговые рассуждения, а не подстановка в формулу.

Как и в testgen.py: условие — параметризованный шаблон, ответ вычисляется кодом (симуляцией, перебором,
sqlite, ipaddress), поэтому «слитое» условие бесполезно для следующего кандидата.
Уровень 5 — задания, которые сильный специалист решает за 3–6 минут с карандашом: нужно удержать в голове
несколько правил сразу (порядок исполнения, изоляция транзакций, планирование, параллельные чередования).
"""
import heapq
import io
import ipaddress
import itertools
import math
import random
import re
import sqlite3
from collections import Counter, OrderedDict, defaultdict, deque
from fractions import Fraction

from .testgen import Family, _code, choice, number, run_py

# =========================================================================== ОБЩИЕ


def h_trace(rng, level):
    """Трассировка Python: замыкания, изменяемые значения по умолчанию, генераторы, рекурсия с мемоизацией."""
    if level == 4:
        kind = rng.choice(["closure", "default"])
        if kind == "closure":
            a, b = rng.randint(2, 5), rng.randint(2, 6)
            x, y, z = (rng.randint(1, 4) for _ in range(3))
            src = (f"def make(step):\n    n = 0\n    def tick(k):\n        nonlocal n\n        n += step * k\n        return n\n"
                   f"    return tick\n\nt = make({a})\nu = make({b})\nprint(t({x}) + u({y}) + t({z}) - u({x}))")
        else:
            v = [rng.randint(1, 6) for _ in range(5)]
            src = (f"def add(v, acc=[]):\n    acc.append(v)\n    return len(acc) * 10 + sum(acc)\n\n"
                   f"add({v[0]})\nadd({v[1]})\nprint(add({v[2]}, []) + add({v[3]}))\n")
    else:
        kind = rng.choice(["gen", "memo", "gen2"])
        if kind == "gen":
            a, b, n = rng.randint(2, 4), rng.randint(3, 7), rng.randint(12, 24)
            src = (f"def gen(n):\n    i = 0\n    while True:\n        i += 1\n        if i % {a} == 0:\n            continue\n"
                   f"        yield i * i\n        if i >= n:\n            return\n\n"
                   f"total = 0\nfor v in gen({n}):\n    if v % {b} == 0:\n        total += 100\n        continue\n    total += v\n"
                   f"print(total)")
        elif kind == "gen2":
            a, b = rng.randint(3, 6), rng.randint(2, 5)
            n = rng.randint(7, 11)
            src = (f"def fib():\n    x, y = 1, {a}\n    while True:\n        yield x\n        x, y = y, (x + y) % {b * 7 + 3}\n\n"
                   f"g = fib()\nvals = [next(g) for _ in range({n})]\nprint(sum(vals[::2]) - sum(vals[1::2]))")
        else:
            n = rng.randint(9, 14)
            c1, c2, c3 = rng.randint(1, 3), rng.randint(1, 3), rng.randint(1, 2)
            src = (f"calls = 0\nmemo = {{}}\n\ndef f(n):\n    global calls\n    calls += 1\n    if n < 3:\n        return n + 1\n"
                   f"    if n in memo:\n        return memo[n]\n    r = ({c1} * f(n - 1) + {c2} * f(n - 2) + {c3} * f(n - 3)) % 1000\n"
                   f"    memo[n] = r\n    return r\n\nres = f({n})\nprint(calls * 1000 + res)")
    return number("Что выведет программа?\n\n" + _code(src), int(run_py(src)), family="h_trace", topic="python", level=level)


def h_recur(rng, level):
    """Рекуррентные соотношения и подсчёт работы рекурсивных функций."""
    if level == 4:
        a, k = rng.choice([2, 3]), rng.randint(3, 6)
        mult = rng.randint(1, 3)
        t = 1
        n = 1
        for _ in range(k):
            n *= 2
            t = a * t + mult * n
        return number(f"Время работы алгоритма задано соотношением T(1) = 1, T(n) = {a}·T(n/2) + {mult}·n для n, равных степени двойки. "
                      f"Чему равно T({2 ** k})?", t, family="h_recur", topic="algorithms", level=level)
    n0 = rng.randint(30, 200)
    c = rng.randint(1, 3)
    src = (f"def f(n):\n    if n <= 1:\n        return 1\n    work = 0\n    for _ in range(n // {c + 1}):\n        work += 1\n"
           f"    return work + f(n // 2) + f(n // 2 - 1)\n\nprint(f({n0}))")
    return number("Что выведет программа?\n\n" + _code(src), int(run_py(src)), family="h_recur", topic="algorithms", level=level)


def _graph_edges(rng, n, extra, wmax=9, directed=False):
    base = set()
    nodes = list(range(1, n + 1))
    rng.shuffle(nodes)
    for i in range(1, n):
        a, b = nodes[i], nodes[rng.randrange(i)]
        base.add((a, b) if directed else tuple(sorted((a, b))))
    while extra > 0:
        a, b = rng.sample(range(1, n + 1), 2)
        e = (a, b) if directed else tuple(sorted((a, b)))
        if e not in base and (b, a) not in base:
            base.add(e)
            extra -= 1
    return sorted((a, b, rng.randint(1, wmax)) for a, b in base)


def h_graph(rng, level):
    kinds = ["paths", "dag", "flow", "mst"] if level == 5 else ["mst", "dag"]
    kind = rng.choice(kinds)
    if kind == "mst":
        n = rng.randint(7, 9)
        edges = _graph_edges(rng, n, rng.randint(5, 8), wmax=20)
        parent = list(range(n + 1))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        total = 0
        for a, b, w in sorted(edges, key=lambda e: e[2]):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
                total += w
        return number(f"Взвешенный неориентированный связный граф на вершинах 1..{n}, рёбра (u, v, вес): {edges}. "
                      f"Каков суммарный вес минимального остовного дерева?", total, family="h_graph", topic="algorithms", level=level)
    if kind == "paths":
        n = rng.randint(6, 8)
        edges = _graph_edges(rng, n, rng.randint(5, 8), wmax=4)
        adj = defaultdict(list)
        for a, b, w in edges:
            adj[a].append((b, w)); adj[b].append((a, w))
        dist = {i: math.inf for i in range(1, n + 1)}
        cnt = {i: 0 for i in range(1, n + 1)}
        dist[1], cnt[1] = 0, 1
        pq = [(0, 1)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist[u]:
                continue
            for v, w in adj[u]:
                nd = d + w
                if nd < dist[v]:
                    dist[v], cnt[v] = nd, cnt[u]
                    heapq.heappush(pq, (nd, v))
                elif nd == dist[v]:
                    cnt[v] += cnt[u]
        return number(f"Взвешенный неориентированный граф, рёбра (u, v, вес): {edges}. Для каждой вершины v ≠ 1 найдите число различных кратчайших путей "
                      f"из вершины 1 в v. Чему равна сумма этих чисел по всем вершинам v = 2..{n}?", sum(cnt[v] for v in range(2, n + 1)),
                      family="h_graph", topic="algorithms", level=level)
    if kind == "dag":
        n = rng.randint(6, 8)
        order = list(range(1, n + 1))
        edges = set()
        for i in range(1, n):
            edges.add((order[rng.randrange(i)], order[i]))
        for _ in range(rng.randint(3, 6)):
            i, j = sorted(rng.sample(range(n), 2))
            edges.add((order[i], order[j]))
        wedges = sorted((a, b, rng.randint(1, 9)) for a, b in edges)
        best = {i: 0 for i in order}
        for u in order:
            for a, b, w in wedges:
                if a == u:
                    best[b] = max(best[b], best[u] + w)
        return number(f"Ориентированный ациклический граф на вершинах 1..{n}, дуги (из, в, вес): {wedges}. "
                      f"Чему равна сумма по всем вершинам v длин самых тяжёлых (по сумме весов) путей, заканчивающихся в v? Путь может начинаться в любой вершине, "
                      f"путь из одной вершины имеет вес 0.", sum(best.values()), family="h_graph", topic="algorithms", level=level)
    # максимальный поток (Эдмондс–Карп) на маленькой сети
    n = rng.randint(6, 7)
    arcs = {}
    for i in range(1, n):
        arcs[(i, i + 1)] = rng.randint(3, 15)
    for _ in range(rng.randint(5, 7)):
        a, b = sorted(rng.sample(range(1, n + 1), 2))
        arcs.setdefault((a, b), rng.randint(3, 15))
    cap = defaultdict(int, arcs)
    adj = defaultdict(set)
    for (a, b) in arcs:
        adj[a].add(b); adj[b].add(a)
    flow = 0
    while True:
        prev = {1: None}
        dq = deque([1])
        while dq and n not in prev:
            u = dq.popleft()
            for v in sorted(adj[u]):
                if v not in prev and cap[(u, v)] > 0:
                    prev[v] = u
                    dq.append(v)
        if n not in prev:
            break
        path, v = [], n
        while prev[v] is not None:
            path.append((prev[v], v)); v = prev[v]
        f = min(cap[e] for e in path)
        for u, v in path:
            cap[(u, v)] -= f
            cap[(v, u)] += f
        flow += f
    shown = sorted((a, b, c) for (a, b), c in arcs.items())
    return number(f"Транспортная сеть, дуги (из, в, пропускная способность): {shown}. Источник — вершина 1, сток — вершина {n}. "
                  f"Каков максимальный поток?", flow, family="h_graph", topic="algorithms", level=level)


def h_dp(rng, level):
    kind = rng.choice(["lcs", "edit", "subsets", "lis"])
    if kind == "lcs":
        a = "".join(rng.choice("ABC") for _ in range(rng.randint(13, 16)))
        b = "".join(rng.choice("ABC") for _ in range(rng.randint(13, 16)))
        dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
        for i in range(1, len(a) + 1):
            for j in range(1, len(b) + 1):
                dp[i][j] = dp[i - 1][j - 1] + 1 if a[i - 1] == b[j - 1] else max(dp[i - 1][j], dp[i][j - 1])
        return number(f"Какова длина наибольшей общей подпоследовательности строк `{a}` и `{b}`?", dp[-1][-1],
                      family="h_dp", topic="algorithms", level=level)
    if kind == "edit":
        a = "".join(rng.choice("abcd") for _ in range(rng.randint(10, 12)))
        b = "".join(rng.choice("abcd") for _ in range(rng.randint(10, 12)))
        dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
        for i in range(len(a) + 1):
            dp[i][0] = i
        for j in range(len(b) + 1):
            dp[0][j] = j
        for i in range(1, len(a) + 1):
            for j in range(1, len(b) + 1):
                dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
        return number(f"Каково расстояние Левенштейна (вставка, удаление, замена символа — по 1) между `{a}` и `{b}`?", dp[-1][-1],
                      family="h_dp", topic="algorithms", level=level)
    if kind == "subsets":
        nums = [rng.randint(1, 12) for _ in range(rng.randint(10, 12))]
        s = rng.randint(sum(nums) // 3, sum(nums) // 2)
        ways = [1] + [0] * s
        for x in nums:
            for t in range(s, x - 1, -1):
                ways[t] += ways[t - x]
        return number(f"Сколько существует подмножеств (по позициям, элементы с равными значениями различимы) массива `{nums}` с суммой ровно {s}?",
                      ways[s], family="h_dp", topic="algorithms", level=level)
    arr = [rng.randint(1, 60) for _ in range(rng.randint(16, 20))]
    best = [1] * len(arr)
    for i in range(len(arr)):
        for j in range(i):
            if arr[j] < arr[i]:
                best[i] = max(best[i], best[j] + 1)
    return number(f"Какова длина наибольшей строго возрастающей подпоследовательности массива `{arr}`?", max(best),
                  family="h_dp", topic="algorithms", level=level)


def h_sql(rng, level):
    regions = ["North", "South", "East", "West"][:rng.randint(3, 4)]
    reps = ["Ann", "Bob", "Cid", "Dan", "Eve"]
    rows = [(i + 1, rng.choice(regions), rng.choice(reps), rng.randrange(100, 901, 50), rng.randint(1, 4)) for i in range(rng.randint(11, 14))]
    for r in regions:  # у каждого региона не меньше трёх продаж
        while sum(1 for x in rows if x[1] == r) < 3:
            i = rng.randrange(len(rows)); rows[i] = (rows[i][0], r, *rows[i][2:])
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE sales(id INTEGER, region TEXT, rep TEXT, amount INTEGER, month INTEGER)")
    con.executemany("INSERT INTO sales VALUES (?,?,?,?,?)", rows)
    window_ok = sqlite3.sqlite_version_info >= (3, 25, 0)
    reg = rng.choice(regions)
    if level == 4 or not window_ok:
        thr = rng.randrange(500, 1500, 50)
        sql = ("SELECT SUM(total) FROM (\n  SELECT region, SUM(amount) AS total FROM sales\n  GROUP BY region\n"
               f"  HAVING SUM(amount) > {thr} AND COUNT(DISTINCT rep) >= 2\n);")
    else:
        kind = rng.choice(["rank", "run", "lag"])
        if kind == "rank":
            k = 2
            sql = ("SELECT amount FROM (\n  SELECT region, amount,\n         ROW_NUMBER() OVER (PARTITION BY region ORDER BY amount DESC, id) AS rn\n"
                   f"  FROM sales\n) WHERE region = '{reg}' AND rn = {k};")
        elif kind == "run":
            target = rng.choice(rows)[0]
            sql = ("SELECT run FROM (\n  SELECT id, SUM(amount) OVER (ORDER BY id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS run\n"
                   f"  FROM sales\n) WHERE id = {target};")
        else:
            target = rng.choice(rows[1:])[0]
            sql = ("SELECT amount - prev FROM (\n  SELECT id, amount, LAG(amount) OVER (PARTITION BY region ORDER BY id) AS prev, region\n"
                   f"  FROM sales\n) WHERE id = {target} AND prev IS NOT NULL;")
    row = con.execute(sql.rstrip(";")).fetchone()
    con.close()
    if row is None or row[0] is None:  # редкий случай: строка без предыдущей — перегенерируем проще
        return h_sql(rng, level)
    t = "| id | region | rep | amount | month |\n|---|---|---|---|---|\n" + "\n".join("| " + " | ".join(map(str, r)) + " |" for r in rows)
    return number(f"Таблица `sales`:\n\n{t}\n\nКакое число вернёт запрос (SQLite)?\n\n{_code(sql, 'sql')}", int(row[0]),
                  family="h_sql", topic="sql", level=level)


def _interleavings(steps, m):
    """Множество конечных значений общего счётчика: поток i m раз делает tmp = x; x = tmp + steps[i]."""
    threads = len(steps)
    seen, finals = set(), set()
    start = (tuple([0] * threads), 0, tuple([0] * threads))

    def go(state):
        if state in seen:
            return
        seen.add(state)
        pcs, x, tmps = state
        done = True
        for i in range(threads):
            if pcs[i] >= 2 * m:
                continue
            done = False
            p = list(pcs); t = list(tmps)
            if pcs[i] % 2 == 0:
                t[i] = x; nx = x
            else:
                nx = t[i] + steps[i]
            p[i] += 1
            go((tuple(p), nx, tuple(t)))
        if done:
            finals.add(x)
    go(start)
    return finals


def h_concurrency(rng, level):
    threads, m = rng.choice([(2, 2), (2, 3), (3, 1), (3, 2)])
    steps = [rng.randint(1, 5) for _ in range(threads)]
    finals = _interleavings(steps, m)
    code = "x = 0\n\n" + "\n\n".join(
        f"def worker{i + 1}():\n    for _ in range({m}):\n        tmp = x\n        x = tmp + {steps[i]}   # не атомарно: чтение и запись — два шага" for i in range(threads))
    head = (f"Общая переменная `x = 0`. Одновременно запускаются потоки, каждый выполняет свою функцию; потоки могут чередоваться между любыми двумя операциями "
            f"(чтением `tmp = x` и записью `x = tmp + k`), блокировок нет.\n\n{_code(code)}\n\n")
    return number(head + "Каждое возможное итоговое значение `x` (по всем допустимым чередованиям) учтём один раз. Чему равна сумма всех различных возможных итоговых значений?",
                  sum(finals), family="h_concurrency", topic="backend_arch", level=level)


def h_bits(rng, level):
    n = rng.randint(8, 10)
    arr = [sum(1 << b for b in rng.sample(range(8), rng.randint(2, 4))) for _ in range(n)]
    if level == 4:
        cnt = sum(1 for i in range(n) for j in range(i + 1, n) if arr[i] & arr[j] == 0)
        return number(f"Сколько пар индексов i < j в массиве `{arr}` удовлетворяют условию `a[i] & a[j] == 0`?", cnt,
                      family="h_bits", topic="algorithms", level=level)
    if rng.random() < 0.5:
        best = max(arr[i] ^ arr[j] for i in range(n) for j in range(i + 1, n))
        return number(f"Каково максимальное значение `a[i] ^ a[j]` по всем парам i < j для массива `{arr}`?", best,
                      family="h_bits", topic="algorithms", level=level)
    k = rng.randint(2, 4)
    cnt = sum(1 for i in range(n) for j in range(i + 1, n) if bin(arr[i] ^ arr[j]).count("1") == k)
    return number(f"Сколько пар i < j в массиве `{arr}` имеют такое значение `a[i] ^ a[j]`, у которого ровно {k} единичных бит?", cnt,
                  family="h_bits", topic="algorithms", level=level)


def h_cidr(rng, level):
    base = ipaddress.ip_network(f"10.{rng.randint(0, 200)}.{rng.randrange(0, 256, 4)}.0/22")
    pieces = []
    for sub in base.subnets(new_prefix=24):
        r = rng.random()
        if r < 0.35:
            pieces.append(sub)
        elif r < 0.65:
            pieces.extend(sub.subnets(new_prefix=25))
        elif r < 0.75:
            pieces.extend(list(sub.subnets(new_prefix=26))[:rng.randint(1, 3)])
        elif r < 0.88:
            pieces.extend(list(sub.subnets(new_prefix=27))[:rng.randint(1, 5)])
    rng.shuffle(pieces)
    pieces = pieces[:rng.randint(5, 7)]
    if rng.random() < 0.5 and pieces:  # добавим вложенный дубликат
        p = rng.choice(pieces)
        if p.prefixlen < 27:
            pieces.append(next(p.subnets(prefixlen_diff=1)))
    rng.shuffle(pieces)
    shown = ", ".join(str(p) for p in pieces)
    merged = list(ipaddress.collapse_addresses(pieces))
    if level == 4 or rng.random() < 0.4:
        total = sum(m.num_addresses for m in merged)
        return number(f"Список сетей: {shown}. Сколько всего различных IPv4-адресов они покрывают (с учётом пересечений)?", total,
                      family="h_cidr", topic="networks", level=level)
    return number(f"Список сетей: {shown}. Сети объединяют в минимально возможный набор CIDR-блоков (суммаризация маршрутов без потери и добавления адресов). "
                  f"Чему равна сумма длин префиксов всех получившихся блоков?", sum(m.prefixlen for m in merged), family="h_cidr", topic="networks", level=level)


def h_regex(rng, level):
    kind = rng.choice(["lazy", "back", "look", "multi"])
    if kind == "lazy":
        tags = ["b", "i", "u", "em"]
        parts = []
        for _ in range(rng.randint(3, 5)):
            t = rng.choice(tags)
            parts.append(f"<{t}>{rng.choice(['x', 'yy', 'zzz', 'q'])}</{t}>")
        text = " ".join(parts)
        greedy = rng.random() < 0.5
        pat = r"<.+>" if greedy else r"<.+?>"
        res = re.findall(pat, text)
        return number(f"Для строки `s = \"{text}\"` выражение `re.findall(r\"{pat}\", s)` возвращает список. Чему равна суммарная длина "
                      f"всех найденных подстрок?", sum(map(len, res)), family="h_regex", topic="python", level=level)
    if kind == "back":
        words = ["level", "radar", "banana", "noon", "apple", "tenet", "stats", "abcba", "civic", "refer", "pip", "queue", "deed", "peep", "kayak"]
        ws = rng.sample(words, rng.randint(8, 10))
        pat = r"\b(\w)\w*\1\b"
        return number(f"Слова: `{' '.join(ws)}`. Сколько слов целиком совпадёт с выражением `\\b(\\w)\\w*\\1\\b`, то есть начинается и заканчивается "
                      f"одной и той же буквой (поиск `re.findall` по всей строке)?", len(re.findall(pat, " ".join(ws))),
                      family="h_regex", topic="python", level=level)
    if kind == "look":
        toks = []
        for _ in range(rng.randint(8, 11)):
            toks.append(rng.choice([f"#{rng.randint(1, 99)}", f"{rng.randint(1, 99)}", f"id{rng.randint(1, 99)}", f"#x{rng.randint(1, 9)}"]))
        s = " ".join(toks)
        pat = r"(?<=#)\d+"
        return number(f"Для строки `s = \"{s}\"` найдены все совпадения `re.findall(r\"(?<=#)\\d+\", s)`. Чему равна сумма найденных чисел?",
                      sum(int(x) for x in re.findall(pat, s)), family="h_regex", topic="python", level=level)
    lines = [f"{rng.choice(['GET', 'POST', 'PUT', 'GET'])} /{rng.choice(['a', 'api', 'v2', 'x1'])} {rng.choice([200, 201, 404, 500, 204])}" for _ in range(rng.randint(8, 11))]
    text = "\n".join(lines)
    pat = r"^(?:GET|POST) /\w+ 2\d\d$"
    return number(f"Многострочный текст:\n\n```\n{text}\n```\n\nСколько совпадений вернёт `re.findall(r\"{pat}\", s, re.MULTILINE)`?",
                  len(re.findall(pat, text, re.MULTILINE)), family="h_regex", topic="python", level=level)


def h_hash(rng, level):
    m = rng.choice([7, 8, 9, 11, 13])
    keys = rng.sample(range(10, 99), rng.randint(5, min(m - 1, 8)))
    table = [None] * m
    for k in keys:
        i = k % m
        while table[i] is not None:
            i = (i + 1) % m
        table[i] = k
    if level == 4:
        return number(f"Хеш-таблица размером {m} с открытой адресацией и линейным пробированием (`i = key % {m}`, при коллизии — следующая ячейка по кругу). "
                      f"Ключи вставляются в порядке `{keys}`. Чему равна сумма номеров ячеек (нумерация с 0), в которых окажутся все ключи?",
                      sum(i for i, v in enumerate(table) if v is not None), family="h_hash", topic="algorithms", level=level)
    deleted = rng.sample(keys[:-1], rng.randint(1, 2))
    tomb = list(table)
    for d in deleted:
        tomb[table.index(d)] = "DEL"
    total = 0
    for target in (k for k in keys if k not in deleted):
        probes, i = 0, target % m
        while True:
            probes += 1
            if tomb[i] == target:
                break
            i = (i + 1) % m
        total += probes
    return number(f"Хеш-таблица размером {m}, линейное пробирование (`i = key % {m}`). Вставлены ключи `{keys}` по порядку; затем удалены {deleted} "
                  f"(ячейка помечается «надгробием» DEL и при поиске не прерывает цепочку). Для каждого оставшегося ключа выполняется поиск; считается число "
                  f"просмотренных ячеек (включая ту, где найден ключ). Чему равна сумма просмотренных ячеек по всем поискам?", total,
                  family="h_hash", topic="algorithms", level=level)


def h_prob(rng, level):
    if level == 4:
        n, k = rng.randint(6, 12), None
        k = rng.randint(2, n - 2)
        p = math.comb(n, k) / 2 ** n * 100
        return number(f"Симметричную монету подбрасывают {n} раз. Какова вероятность (в %) получить ровно {k} орлов? Округлите до десятых.",
                      round(p, 1), tol=0.11, family="h_prob", topic="statistics", level=level)
    kind = rng.choice(["cond", "expmax"])
    if kind == "cond":
        s = rng.randint(8, 11)
        outs = list(itertools.product(range(1, 7), repeat=2))
        cond = [o for o in outs if 6 in o]
        good = [o for o in cond if sum(o) >= s]
        if not good:
            s = 8
            good = [o for o in cond if sum(o) >= s]
        val = len(good) / len(cond) * 100
        return number(f"Бросают два честных кубика. Известно, что хотя бы на одном выпало 6. Какова вероятность (в %), что сумма очков не меньше {s}? Округлите до десятых.",
                      round(val, 1), tol=0.11, family="h_prob", topic="statistics", level=level)
    n = rng.randint(2, 3)
    sides = rng.choice([4, 6, 8])
    outs = list(itertools.product(range(1, sides + 1), repeat=n))
    e = sum(max(o) for o in outs) / len(outs)
    return number(f"Бросают {n} честных кубика с гранями от 1 до {sides}. Каково математическое ожидание максимального выпавшего числа? Округлите до сотых.",
                  round(e, 2), tol=0.011, family="h_prob", topic="statistics", level=level)


def h_sched(rng, level):
    """Операционные системы: планирование процессов и замещение страниц."""
    if level == 5 and rng.random() < 0.5:
        n = rng.randint(4, 5)
        q = rng.randint(2, 4)
        procs = [(f"P{i + 1}", rng.randint(0, 6), rng.randint(2, 9)) for i in range(n)]
        procs.sort(key=lambda p: (p[1], p[0]))
        rem = {p[0]: p[2] for p in procs}
        arr = {p[0]: p[1] for p in procs}
        t, queue, done = 0, deque(), {}
        pending = deque(procs)
        while pending and pending[0][1] <= t:
            queue.append(pending.popleft()[0])
        while len(done) < n:
            if not queue:
                t = pending[0][1]
                while pending and pending[0][1] <= t:
                    queue.append(pending.popleft()[0])
                continue
            p = queue.popleft()
            run = min(q, rem[p])
            t += run
            rem[p] -= run
            while pending and pending[0][1] <= t:
                queue.append(pending.popleft()[0])
            if rem[p] > 0:
                queue.append(p)
            else:
                done[p] = t
        target = rng.choice(list(done))
        table = "| процесс | прибытие | время выполнения |\n|---|---|---|\n" + "\n".join(f"| {a} | {b} | {c} |" for a, b, c in procs)
        return number(f"Планировщик Round Robin с квантом {q}. Процессы:\n\n{table}\n\nЕсли за время кванта пришёл новый процесс, он встаёт в очередь "
                      f"раньше вытесненного. Переключение мгновенное. В какой момент времени завершится {target}?", done[target],
                      family="h_sched", topic="os", level=level)
    seq = [rng.randint(1, 6) for _ in range(rng.randint(12, 16))]
    frames = rng.randint(3, 4)

    def faults(policy, fr):
        mem, f = [], 0
        for i, p in enumerate(seq):
            if p in mem:
                if policy == "lru":
                    mem.remove(p); mem.append(p)
                continue
            f += 1
            if len(mem) >= fr:
                if policy == "opt":
                    nxt = {x: (seq[i + 1:].index(x) if x in seq[i + 1:] else 10 ** 6) for x in mem}
                    mem.remove(max(mem, key=lambda x: nxt[x]))
                else:
                    mem.pop(0)
            mem.append(p)
        return f
    if level == 4:
        return number(f"Последовательность обращений к страницам: `{seq}`. В памяти {frames} кадра, изначально пусто. Введите число: (промахи FIFO)·100 + (промахи LRU).",
                      faults("fifo", frames) * 100 + faults("lru", frames), family="h_sched", topic="os", level=level)
    return number(f"Последовательность обращений к страницам: `{seq}`, память пуста в начале. На сколько промахов алгоритм FIFO при {frames} кадрах даёт "
                  f"больше, чем оптимальный алгоритм (OPT, вытесняет страницу, которая понадобится позже всех) при {frames} кадрах?",
                  faults("fifo", frames) - faults("opt", frames), family="h_sched", topic="os", level=level)


def h_modmath(rng, level):
    if level == 4:
        a, e, m = rng.randint(3, 40), rng.randint(20, 200), rng.choice([97, 101, 211, 1000, 997, 360])
        return number(f"Чему равно значение `pow({a}, {e}, {m})` — остаток от деления {a}^{e} на {m}?", pow(a, e, m),
                      family="h_modmath", topic="algorithms", level=level)
    kind = rng.choice(["crt", "phi", "inv"])
    if kind == "crt":
        m1, m2 = rng.choice([(5, 7), (7, 9), (8, 11), (9, 10), (11, 13), (6, 7), (4, 9)])
        x0 = rng.randint(1, m1 * m2 - 1)
        return number(f"Найдите наименьшее неотрицательное x, для которого x ≡ {x0 % m1} (mod {m1}) и x ≡ {x0 % m2} (mod {m2}).", x0,
                      family="h_modmath", topic="algorithms", level=level)
    if kind == "phi":
        n = rng.choice([x for x in range(100, 700) if len({p for p in range(2, x) if x % p == 0 and all(p % q for q in range(2, int(p ** .5) + 1))}) >= 2])
        return number(f"Сколько существует натуральных чисел от 1 до {n}, взаимно простых с {n}?", sum(1 for k in range(1, n + 1) if math.gcd(k, n) == 1),
                      family="h_modmath", topic="algorithms", level=level)
    m = rng.choice([97, 101, 103, 107, 109, 113])
    a = rng.randint(2, m - 1)
    return number(f"Найдите обратный к {a} элемент по модулю {m} (такое x из [1, {m - 1}], что {a}·x ≡ 1 mod {m}).", pow(a, -1, m),
                  family="h_modmath", topic="algorithms", level=level)


COMMON_HARD = [
    Family("h_trace", (4, 5), h_trace, None, 1.1), Family("h_recur", (4, 5), h_recur), Family("h_graph", (4, 5), h_graph, None, 1.1),
    Family("h_dp", (5,), h_dp, None, 1.1), Family("h_sql", (4, 5), h_sql, None, 1.0), Family("h_concurrency", (5,), h_concurrency, None, 0.9),
    Family("h_bits", (4, 5), h_bits, None, 0.8), Family("h_cidr", (4, 5), h_cidr, None, 0.8), Family("h_regex", (5,), h_regex, None, 0.8),
    Family("h_hash", (4, 5), h_hash, None, 0.9), Family("h_prob", (4, 5), h_prob, None, 0.8), Family("h_sched", (4, 5), h_sched, None, 0.9),
    Family("h_modmath", (4, 5), h_modmath, None, 0.7),
]


# =========================================================================== BACKEND
def h_quorum(rng, level):
    n = rng.choice([5, 5, 7])
    lat = sorted(rng.sample(range(8, 140), n))
    shuffled = list(lat)
    rng.shuffle(shuffled)
    w = rng.randint(n // 2 + 1, n - 1)
    r = rng.randint(1, n - w + 1) if level == 4 else rng.randint(n - w + 1, n - 1)
    ok = w + r > n
    wl, rl = lat[w - 1], lat[r - 1]
    if level == 4:
        return number(f"Данные хранятся на {n} репликах (кворумная репликация). Задержки ответа реплик, мс: `{shuffled}`. Запись считается успешной, когда "
                      f"подтвердили W = {w} реплик, чтение — когда ответили R = {r} реплик (запрос уходит на все реплики одновременно). "
                      f"Каково время выполнения операции записи в мс?", wl, family="h_quorum", topic="backend_arch", level=level)
    return number(f"Данные хранятся на {n} репликах. Задержки ответа реплик, мс: `{shuffled}`. Запись ждёт ответов от W = {w} реплик, чтение — от R = {r} "
                  f"(запросы уходят на все реплики параллельно). Чему равна сумма задержек одной записи и одного чтения (мс), "
                  f"умноженная на {1 if ok else 2} (множитель 1, если W + R > N, иначе 2)?", (wl + rl) * (1 if ok else 2),
                  family="h_quorum", topic="backend_arch", level=level)


def h_isolation(rng, level):
    x0 = rng.randint(10, 90) * 10
    k = rng.randint(2, 4)
    deltas = [rng.choice([-50, -30, -20, 10, 20, 40, 70]) for _ in range(k)]
    commits = [rng.random() < 0.7 for _ in range(k)]
    # позиция первого SELECT транзакции T1 среди завершений: перед какой по счёту транзакцией
    pos = rng.randint(0, k - 1)
    lines = [f"Исходно `x = {x0}`. Транзакция T1 выполняет два запроса `SELECT x`, между ними другие транзакции (по одной за раз, каждая — `UPDATE x = x + d`, затем COMMIT или ROLLBACK):", ""]
    seq = []
    for i in range(k):
        if i == pos:
            seq.append("T1: SELECT x  → r1")
        seq.append(f"T{i + 2}: UPDATE x = x + ({deltas[i]}); {'COMMIT' if commits[i] else 'ROLLBACK'}")
    if pos >= k:
        seq.append("T1: SELECT x  → r1")
    seq.append("T1: SELECT x  → r2")
    body = "\n".join(f"{j + 1}. {s}" for j, s in enumerate(seq))
    rc = x0 + sum(d for d, c in zip(deltas, commits) if c)
    rr = x0 + sum(d for d, c in zip(deltas[:pos], commits[:pos]) if c)
    q = (f"{lines[0]}\n\n{body}\n\nЧему равна сумма значений r2 при уровне изоляции READ COMMITTED и r2 при уровне REPEATABLE READ "
         f"(снимок данных фиксируется на первом запросе транзакции; в REPEATABLE READ в стиле PostgreSQL)?")
    return number(q, rc + rr, family="h_isolation", topic="backend_arch", level=level)


def h_chash(rng, level):
    for _ in range(30):
        q = _h_chash(rng, level)
        if q["answer"] > 0:
            return q
    return q


def _h_chash(rng, level):
    ring = 360
    nodes = rng.sample(range(0, ring), rng.randint(3, 4))
    new = rng.choice([p for p in range(ring) if p not in nodes])
    keys = rng.sample(range(0, ring), rng.randint(10, 13))
    vn = level == 5

    def owner(k, nds):
        cand = [p for p in sorted(nds) if p >= k]
        return cand[0] if cand else min(nds)
    ring_nodes = {f"N{i + 1}": ([p, (p + rng.randint(40, 120)) % ring] if vn else [p]) for i, p in enumerate(nodes)}
    flat = {p: n for n, ps in ring_nodes.items() for p in ps}
    new_ps = [new, (new + 100) % ring] if vn and ((new + 100) % ring) not in flat else [new]
    flat2 = dict(flat)
    for p in new_ps:
        flat2[p] = "NEW"
    moved = sum(k for k in keys if flat[owner(k, flat)] != flat2[owner(k, flat2)])
    desc = "; ".join(f"{n}: {ps}" for n, ps in ring_nodes.items())
    return number(f"Консистентное хеширование на кольце 0..{ring - 1}: ключ принадлежит первому узлу (точке) по ходу часовой стрелки, начиная с позиции ключа "
                  f"(позиция ключа равна позиции точки — принадлежит этой точке; после {ring - 1} идёт 0). Точки узлов: {desc}. "
                  f"Добавляется новый узел с точками {new_ps}. Ключи на кольце: `{sorted(keys)}`. Чему равна сумма позиций тех ключей, у которых сменится владелец?",
                  moved, family="h_chash", topic="backend_arch", level=level)


def h_slidewin(rng, level):
    w, lim = rng.choice([5, 10, 10, 12]), rng.randint(3, 5)
    times = sorted(rng.choices(range(0, 3 * w), k=rng.randint(12, 16)))
    acc = []
    for t in times:
        if sum(1 for a in acc if a > t - w) < lim:
            acc.append(t)
    sliding = len(acc)
    fixed, cnt = 0, Counter()
    for t in times:
        b = t // w
        if cnt[b] < lim:
            cnt[b] += 1; fixed += 1
    if level == 4:
        return number(f"Ограничитель «скользящее окно»: за любые последние {w} секунд (интервал (t − {w}, t]) принимается не более {lim} запросов; "
                      f"отклонённые запросы окно не занимают. Запросы пришли в секунды `{times}`. Чему равна сумма моментов времени принятых запросов?",
                      sum(acc), family="h_slidewin", topic="backend_arch", level=level)
    return number(f"Два ограничителя с лимитом {lim} запросов: «фиксированное окно» (окна [0,{w}), [{w},{2 * w}), … с обнулением счётчика) и «скользящее окно» "
                  f"(интервал (t − {w}, t], отклонённые запросы окно не занимают). Запросы пришли в секунды `{times}`. "
                  f"Каково число принятых запросов при фиксированном окне, умноженное на 100, плюс число принятых при скользящем?",
                  fixed * 100 + sliding, family="h_slidewin", topic="backend_arch", level=level)


def h_mm1(rng, level):
    mu = rng.randrange(40, 401, 5)
    lam = int(mu * rng.choice([0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9]))
    rho = lam / mu
    if level == 4:
        return number(f"Очередь M/M/1: интенсивность поступления {lam} запросов/с, интенсивность обслуживания {mu} запросов/с. "
                      f"Чему равно среднее время пребывания запроса в системе W = 1/(μ − λ), в мс? Округлите до десятых.",
                      round(1000 / (mu - lam), 1), tol=0.11, family="h_mm1", topic="backend_arch", level=level)
    p = rng.choice([90, 95, 99])
    t = -math.log(1 - p / 100) / (mu - lam) * 1000
    return number(f"Очередь M/M/1: λ = {lam} запросов/с, μ = {mu} запросов/с. Время пребывания запроса в системе распределено экспоненциально "
                  f"со средним 1/(μ − λ). Каково {p}-й перцентиль времени пребывания (мс)? Округлите до целого.", round(t), tol=1.01,
                  family="h_mm1", topic="backend_arch", level=level)


def h_bloom(rng, level):
    m = rng.randrange(5000, 30001, 500)
    n = max(100, int(m / rng.uniform(6, 14) // 50 * 50))
    k = max(1, round(m / n * math.log(2)))
    fpr = (1 - math.exp(-k * n / m)) ** k * 100
    return number(f"Фильтр Блума: m = {m} бит, вставлено n = {n} элементов, число хеш-функций k = {k}. Оцените вероятность ложноположительного ответа "
                  f"по формуле (1 − e^(−kn/m))^k, в процентах, округлите до сотых.", round(fpr, 2), tol=0.011,
                  family="h_bloom", topic="backend_arch", level=level)


BACKEND_HARD = [
    Family("h_quorum", (4, 5), h_quorum, ("backend",), 2.6), Family("h_isolation", (5,), h_isolation, ("backend",), 3.0),
    Family("h_chash", (4, 5), h_chash, ("backend",), 2.6), Family("h_slidewin", (4, 5), h_slidewin, ("backend",), 2.6),
    Family("h_mm1", (4, 5), h_mm1, ("backend",), 2.4), Family("h_bloom", (5,), h_bloom, ("backend",), 1.8),
]


# =========================================================================== FRONTEND
def _sim_events(rng, level):
    """Мини-модель очередей событий JS: синхронный код → микрозадачи → таймеры (макрозадачи)."""
    labels = rng.sample("ABCDEFGHJKLMNP", 9)
    it = iter(labels)
    code, sync, micro, timers = [], [], [], []
    # статическая рамка + случайные блоки
    blocks = ["log", "timeout", "then", "async", "timeout_then", "nested"]
    chosen = rng.sample(blocks, rng.randint(4, 5))
    if "log" not in chosen:
        chosen[0] = "log"
    rng.shuffle(chosen)
    order_micro = []
    for b in chosen:
        if b == "log":
            a = next(it); code.append(f"console.log('{a}');"); sync.append(a)
        elif b == "timeout":
            a = next(it); d = rng.choice([0, 0, 5, 10])
            code.append(f"setTimeout(() => console.log('{a}'), {d});"); timers.append((d, len(timers), [a]))
        elif b == "then":
            a = next(it); code.append(f"Promise.resolve().then(() => console.log('{a}'));"); order_micro.append(a)
        elif b == "async":
            a, c = next(it), next(it)
            code.append(f"(async () => {{ console.log('{a}'); await null; console.log('{c}'); }})();")
            sync.append(a); order_micro.append(c)
        elif b == "timeout_then":
            a, c = next(it), next(it); d = rng.choice([0, 0, 5])
            code.append(f"setTimeout(() => {{ console.log('{a}'); Promise.resolve().then(() => console.log('{c}')); }}, {d});")
            timers.append((d, len(timers), [a, c]))
        else:
            a, c = next(it), next(it)
            code.append(f"Promise.resolve().then(() => {{ console.log('{a}'); queueMicrotask(() => console.log('{c}')); }});")
            order_micro.append(a)
            order_micro.append(("nested", c))
    # микрозадачи: вложенные идут в конец очереди на момент постановки
    out_micro, queue = [], deque(order_micro)
    while queue:
        m = queue.popleft()
        if isinstance(m, tuple):
            out_micro.append(m[1])
        else:
            out_micro.append(m)
            nested = [x for x in order_micro if isinstance(x, tuple) and x[1] not in out_micro and False]
    # корректное моделирование вложенных: цепочка (a, затем c в конец очереди)
    out_micro, q = [], deque()
    for m in order_micro:
        q.append(m)
    # вложенная микрозадача c ставится при выполнении a, т.е. после всех уже стоящих в очереди
    flat = deque([m for m in order_micro if not isinstance(m, tuple)])
    nested_after = {}
    for i, m in enumerate(order_micro):
        if isinstance(m, tuple):
            nested_after[order_micro[i - 1]] = m[1]
    out_micro = []
    while flat:
        a = flat.popleft()
        out_micro.append(a)
        if a in nested_after:
            flat.append(nested_after[a])
    result = list(sync) + out_micro
    for d, _, labs in sorted(timers, key=lambda t: (t[0], t[1])):
        result += labs
    return "\n".join(code), result


def h_eventloop(rng, level):
    code, order = _sim_events(rng, level)
    answer = " → ".join(order)
    wrongs = set()
    for _ in range(80):
        w = list(order)
        i, j = rng.sample(range(len(w)), 2)
        w[i], w[j] = w[j], w[i]
        s = " → ".join(w)
        if s != answer:
            wrongs.add(s)
        if len(wrongs) >= 3:
            break
    return choice(rng, "В каком порядке выведутся строки (Node.js / браузер)? Учтите порядок синхронного кода, микрозадач и таймеров.\n\n"
                  + _code(code, "javascript"), answer, sorted(wrongs), family="h_eventloop", topic="javascript", level=level)


def h_flex(rng, level):
    n = rng.randint(3, 4)
    gap = rng.choice([0, 8, 10, 12, 16])
    basis = [rng.randrange(60, 241, 10) for _ in range(n)]
    cont = rng.randrange(300, 701, 20)
    free = cont - sum(basis) - gap * (n - 1)
    if free >= 0:
        g = [rng.randint(0, 3) for _ in range(n)]
        if sum(g) == 0:
            g[0] = 1
        k = rng.randrange(n)
        w = basis[k] + free * g[k] / sum(g)
        props = "; ".join(f"item{i + 1}: flex-basis {basis[i]}px, flex-grow {g[i]}" for i in range(n))
        mode = "grow"
    else:
        sh = [rng.randint(1, 3) for _ in range(n)]
        k = rng.randrange(n)
        scaled = sum(sh[i] * basis[i] for i in range(n))
        w = basis[k] + free * (sh[k] * basis[k]) / scaled
        props = "; ".join(f"item{i + 1}: flex-basis {basis[i]}px, flex-shrink {sh[i]}" for i in range(n))
        mode = "shrink"
    return number(f"Flex-контейнер `display: flex; width: {cont}px; gap: {gap}px`, элементы без min/max-width и без переноса. {props}. "
                  f"Чему равна итоговая ширина item{k + 1} (px)? Округлите до десятых. (При сжатии уменьшение пропорционально flex-shrink × flex-basis.)",
                  round(w, 1), tol=0.11, family="h_flex", topic="css", level=level)


def h_fontem(rng, level):
    root = rng.choice([14, 16, 18])
    sizes = [(rng.choice(["em", "%", "rem"]), None) for _ in range(rng.randint(3, 4))]
    cur, parts = root, []
    for unit, _ in sizes:
        if unit == "em":
            v = rng.choice([0.75, 1.25, 1.5, 0.8, 1.2, 2]); cur = cur * v if parts else cur * v; parts.append(f"{v}em")
        elif unit == "%":
            v = rng.choice([80, 90, 110, 125, 150, 200]); cur = cur * v / 100; parts.append(f"{v}%")
        else:
            v = rng.choice([0.9, 1, 1.1, 1.25, 1.5]); cur = root * v; parts.append(f"{v}rem")
    chain = " → ".join(f"div{i + 1}: font-size {p}" for i, p in enumerate(parts))
    return number(f"Корневой элемент: `html {{ font-size: {root}px }}`. Элементы вложены друг в друга: {chain}. Значение `em` и `%` считается от размера шрифта "
                  f"родителя, `rem` — от корня. Каков вычисленный размер шрифта самого вложенного div (px)? Округлите до сотых.",
                  round(cur, 2), tol=0.011, family="h_fontem", topic="css", level=level)


def h_react(rng, level):
    clicks = rng.randint(2, 4)
    ops = []
    for _ in range(rng.randint(3, 4)):
        ops.append(rng.choice([("v", rng.randint(1, 5)), ("f", rng.randint(1, 5)), ("m", rng.choice([2, 3]))]))
    ssnap = None

    def apply(state, ops_):
        snap = state
        cur = state
        for kind, v in ops_:
            if kind == "v":
                cur = snap + v      # setCount(count + v): использует «снимок»
            elif kind == "f":
                cur = cur + v       # setCount(c => c + v)
            else:
                cur = cur * v       # setCount(c => c * v)
        return cur
    s = 0
    for _ in range(clicks):
        s = apply(s, ops)
    lines = []
    for kind, v in ops:
        lines.append({"v": f"  setCount(count + {v});", "f": f"  setCount(c => c + {v});", "m": f"  setCount(c => c * {v});"}[kind])
    code = ("function Counter() {\n  const [count, setCount] = useState(0);\n  const onClick = () => {\n" + "\n".join(lines) +
            "\n  };\n  return <button onClick={onClick}>{count}</button>;\n}")
    return number(f"Компонент React (React 18, обновления внутри обработчика группируются):\n\n{_code(code, 'jsx')}\n\nЧто будет показано на кнопке после {clicks} кликов (между кликами компонент перерисовывается)?",
                  s, family="h_react", topic="javascript", level=level)


def _js_parseint(s, radix):
    if radix == 0:
        radix = 10
    if radix < 2 or radix > 36:
        return None
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"[:radix]
    val, seen = 0, False
    for ch in s.lower():
        if ch in digits:
            val = val * radix + digits.index(ch); seen = True
        else:
            break
    return val if seen else None


def h_parseint(rng, level):
    pool = ["10", "11", "12", "21", "7", "101", "3", "99", "20", "15", "41", "8"]
    arr = rng.sample(pool, rng.randint(5, 6))
    res = [_js_parseint(x, i) for i, x in enumerate(arr)]
    ok = [r for r in res if r is not None]
    return number(f"Что вернёт `{arr!r}.map(parseInt)` в JavaScript (помните: callback получает (элемент, индекс), а индекс становится основанием)? "
                  f"Введите сумму всех полученных чисел, не считая NaN (NaN — как 0).".replace("[", "[").replace("'", '"'),
                  sum(ok), family="h_parseint", topic="javascript", level=level)


def _lum(c):
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def h_contrast(rng, level):
    def col():
        return "#%02x%02x%02x" % tuple(rng.randrange(0, 256, 5) for _ in range(3))
    a, b = col(), col()
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    ratio = (la + 0.05) / (lb + 0.05)
    return number(f"Текст цвета {a} на фоне {b}. Чему равно отношение контраста по WCAG 2.x: (L1 + 0.05) / (L2 + 0.05), где L — относительная яркость "
                  f"(sRGB с гамма-коррекцией: для компоненты c/255 ≤ 0.03928 берётся c/255/12.92, иначе ((c/255 + 0.055)/1.055)^2.4; "
                  f"L = 0.2126·R + 0.7152·G + 0.0722·B)? Округлите до десятых.", round(ratio, 1), tol=0.11,
                  family="h_contrast", topic="css", level=level)


FRONTEND_HARD = [
    Family("h_eventloop", (4, 5), h_eventloop, ("frontend",), 3.0), Family("h_flex", (4, 5), h_flex, ("frontend",), 2.6),
    Family("h_fontem", (4, 5), h_fontem, ("frontend",), 2.2), Family("h_react", (5,), h_react, ("frontend",), 2.6),
    Family("h_parseint", (5,), h_parseint, ("frontend",), 2.0), Family("h_contrast", (5,), h_contrast, ("frontend",), 1.8),
]


# =========================================================================== DATA
def h_auc(rng, level):
    n = rng.randint(7, 9)
    scores = rng.sample(range(1, 100), n)
    labels = [rng.random() < 0.5 for _ in range(n)]
    if all(labels) or not any(labels):
        labels[0], labels[1] = True, False
    pos = [s for s, l in zip(scores, labels) if l]
    neg = [s for s, l in zip(scores, labels) if not l]
    auc = sum(1 for p in pos for q in neg if p > q) / (len(pos) * len(neg))
    rows = ", ".join(f"({s}, {int(l)})" for s, l in zip(scores, labels))
    return number(f"Классификатор выдал оценки и истинные метки (оценка, метка): {rows}. Чему равен ROC-AUC (вероятность, что случайный положительный объект "
                  f"получит оценку выше случайного отрицательного)? Округлите до сотых.", round(auc, 2), tol=0.011,
                  family="h_auc", topic="ml", level=level)


def h_kmeans(rng, level):
    for _ in range(100):
        pts = [(rng.randint(0, 12), rng.randint(0, 12)) for _ in range(rng.randint(6, 7))]
        c = rng.sample(pts, 2)
        assign = []
        ok = True
        for p in pts:
            d = [(p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 for q in c]
            if d[0] == d[1]:
                ok = False; break
            assign.append(d.index(min(d)))
        if ok and 0 < sum(assign) < len(pts):
            break
    clusters = [[p for p, a in zip(pts, assign) if a == k] for k in (0, 1)]
    cent = [(sum(x for x, _ in cl) / len(cl), sum(y for _, y in cl) / len(cl)) for cl in clusters]
    sse = sum((x - cent[k][0]) ** 2 + (y - cent[k][1]) ** 2 for k in (0, 1) for x, y in clusters[k])
    return number(f"Точки на плоскости: {pts}. Алгоритм k-means (k = 2), начальные центры — {c[0]} и {c[1]}. Выполняется одна итерация: "
                  f"назначение точек ближайшему центру (евклидово расстояние), затем пересчёт центров. Чему равна сумма квадратов расстояний "
                  f"от точек до своих новых центров (SSE)? Округлите до сотых.", round(sse, 2), tol=0.021, family="h_kmeans", topic="ml", level=level)


def h_linreg(rng, level):
    n = rng.randint(5, 6)
    xs = sorted(rng.sample(range(1, 15), n))
    a, b = rng.choice([-2, -1, 1, 2, 3]), rng.randint(0, 10)
    ys = [a * x + b + rng.randint(-4, 4) for x in xs]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    icpt = my - slope * mx
    x0 = rng.randint(15, 20)
    pairs = ", ".join(f"({x}, {y})" for x, y in zip(xs, ys))
    return number(f"Данные (x, y): {pairs}. Постройте линейную регрессию y = kx + b методом наименьших квадратов. Каково предсказание для x = {x0}? Округлите до десятых.",
                  round(slope * x0 + icpt, 1), tol=0.11, family="h_linreg", topic="statistics", level=level)


def h_infogain(rng, level):
    a_pos, a_neg = rng.randint(2, 8), rng.randint(2, 8)
    b_pos, b_neg = rng.randint(2, 8), rng.randint(2, 8)

    def ent(p, n):
        t = p + n
        return -sum((x / t) * math.log2(x / t) for x in (p, n) if x)
    tp, tn = a_pos + b_pos, a_neg + b_neg
    t = tp + tn
    gain = ent(tp, tn) - (a_pos + a_neg) / t * ent(a_pos, a_neg) - (b_pos + b_neg) / t * ent(b_pos, b_neg)
    return number(f"Узел дерева решений содержит {tp} положительных и {tn} отрицательных объектов. Разбиение по признаку делит их на две ветви: "
                  f"в первой {a_pos} положительных и {a_neg} отрицательных, во второй {b_pos} и {b_neg}. Каков информационный выигрыш (энтропия в битах, log2)? "
                  f"Округлите до тысячных.", round(gain, 3), tol=0.0011, family="h_infogain", topic="ml", level=level)


def h_gd(rng, level):
    if level == 4 or rng.random() < 0.5:
        a, c, b = rng.choice([1, 2, 3]), rng.randint(2, 9), rng.randint(0, 5)
        w, lr, steps = rng.randint(-5, 0), rng.choice([0.05, 0.1, 0.2]), rng.randint(3, 5)
        w0 = w
        for _ in range(steps):
            w -= lr * 2 * a * (w - c)
        return number(f"Минимизируется f(w) = {a}·(w − {c})² + {b} градиентным спуском: w ← w − η·f′(w), η = {lr}, стартовое w = {w0}. Чему равно w после {steps} шагов? "
                      f"Округлите до тысячных.", round(w, 3), tol=0.0011, family="h_gd", topic="ml", level=level)
    x, y = rng.choice([1, 2, 3]), rng.choice([0, 1])
    w0, lr = rng.choice([0.0, 0.5, -0.5]), rng.choice([0.5, 1.0])
    p = 1 / (1 + math.exp(-w0 * x))
    w1 = w0 - lr * (p - y) * x
    return number(f"Логистическая регрессия без смещения: p = σ(w·x), потеря — логарифмическая. Один объект x = {x}, метка y = {y}, w = {w0}, шаг обучения η = {lr}. "
                  f"Чему равно w после одного шага градиентного спуска (градиент = (p − y)·x)? Округлите до тысячных.", round(w1, 3), tol=0.0011,
                  family="h_gd", topic="ml", level=level)


def h_nb(rng, level):
    prior = rng.choice([0.3, 0.4, 0.5, 0.6])
    pa = [rng.choice([0.2, 0.3, 0.5, 0.7, 0.8, 0.9]) for _ in range(3)]
    pb = [rng.choice([0.1, 0.2, 0.4, 0.5, 0.6, 0.7]) for _ in range(3)]
    x = [rng.randint(0, 1) for _ in range(3)]
    la, lb = prior, 1 - prior
    for i in range(3):
        la *= pa[i] if x[i] else 1 - pa[i]
        lb *= pb[i] if x[i] else 1 - pb[i]
    post = la / (la + lb) * 100
    return number(f"Наивный байесовский классификатор, класс A (априорная вероятность {prior}) против B. Вероятности признаков равными 1: "
                  f"у A — {pa}, у B — {pb}. У объекта признаки равны {x}. Какова апостериорная вероятность класса A (в %)? Округлите до десятых.",
                  round(post, 1), tol=0.11, family="h_nb", topic="ml", level=level)


def h_corr(rng, level):
    n = rng.randint(6, 7)
    xs = [rng.randint(1, 20) for _ in range(n)]
    ys = [x * rng.choice([-1, 1, 2]) + rng.randint(-6, 6) for x in xs]
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx, syy = sum((x - mx) ** 2 for x in xs), sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return h_corr(rng, level)
    r = sxy / math.sqrt(sxx * syy)
    return number(f"Для выборок x = {xs} и y = {ys} вычислите коэффициент корреляции Пирсона. Округлите до сотых.", round(r, 2), tol=0.011,
                  family="h_corr", topic="statistics", level=level)


DATA_HARD = [
    Family("h_auc", (4, 5), h_auc, ("data",), 2.4), Family("h_kmeans", (5,), h_kmeans, ("data",), 2.6),
    Family("h_linreg", (4, 5), h_linreg, ("data",), 2.4), Family("h_infogain", (5,), h_infogain, ("data",), 2.6),
    Family("h_gd", (4, 5), h_gd, ("data",), 2.4), Family("h_nb", (5,), h_nb, ("data",), 2.4), Family("h_corr", (4, 5), h_corr, ("data",), 2.2),
]


# =========================================================================== DEVOPS
def h_binpack(rng, level):
    nodes = rng.randint(3, 5)
    cpu = [rng.choice([4, 8, 16]) for _ in range(nodes)]
    mem = [c * rng.choice([2, 4, 4, 8]) for c in cpu]
    res_c, res_m = rng.choice([0.5, 1.0]), rng.choice([1, 2])
    pod_c, pod_m = rng.choice([250, 500, 750, 1000]), rng.choice([256, 512, 1024, 1536])
    maxp = rng.choice([8, 10, 15, 20, 110])
    total = 0
    for c, m in zip(cpu, mem):
        by_c = int((c - res_c) * 1000 // pod_c)
        by_m = int((m - res_m) * 1024 // pod_m)
        total += min(by_c, by_m, maxp)
    desc = ", ".join(f"{c} vCPU / {m} GiB" for c, m in zip(cpu, mem))
    return number(f"Кластер Kubernetes из {nodes} узлов (ёмкость: {desc}). На каждом узле система резервирует {res_c} vCPU и {res_m} GiB памяти; "
                  f"максимум {maxp} подов на узел. Под запрашивает requests: {pod_c} m CPU и {pod_m} MiB памяти. Сколько таких подов суммарно можно разместить?",
                  total, family="h_binpack", topic="devops", level=level)


def h_errbudget(rng, level):
    slo = rng.choice([99.0, 99.5, 99.7, 99.8, 99.9, 99.95, 99.99])
    days = rng.randint(28, 31)
    budget = (1 - slo / 100)
    err = rng.choice([0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0, 7.5, 10.0]) / 100
    if err <= budget:
        err = budget * rng.choice([2, 3, 5, 8])
    if level == 4:
        hours = days * 24 * budget / err
        return number(f"SLO доступности {slo}% на окно {days} суток. Сейчас доля ошибочных запросов постоянно равна {err * 100:g}% (нагрузка равномерна). "
                      f"Через сколько часов с начала окна будет исчерпан бюджет ошибок? Округлите до десятых.", round(hours, 1), tol=0.11,
                      family="h_errbudget", topic="devops", level=level)
    used = rng.choice([10, 20, 30, 40, 50])
    left = (100 - used) / 100 * days * 24 * budget / err
    return number(f"SLO {slo}% на окно {days} суток; бюджет ошибок уже израсходован на {used}%. Начался инцидент: доля ошибочных запросов {err * 100:g}% при равномерной "
                  f"нагрузке. Через сколько часов будет исчерпан оставшийся бюджет? Округлите до десятых.", round(left, 1), tol=0.11,
                  family="h_errbudget", topic="devops", level=level)


def h_vpc(rng, level):
    reqs = [rng.choice([10, 25, 50, 60, 100, 120, 200, 250, 500]) for _ in range(rng.randint(3, 4))]
    reserved = 5
    sizes = []
    for h in reqs:
        need = h + reserved
        sizes.append(max(16, 1 << (need - 1).bit_length()))
    vpc = rng.choice([22, 21, 20])
    free = 2 ** (32 - vpc) - sum(sizes)
    if free < 0:
        vpc = 19
        free = 2 ** (32 - vpc) - sum(sizes)
    prefixes = [32 - (s.bit_length() - 1) for s in sizes]
    return number(f"В сети VPC /{vpc} нужно разместить подсети под {reqs} хостов (по одной подсети на каждое число). В каждой подсети облако резервирует {reserved} адресов, "
                  f"размер подсети — минимальная степень двойки (не меньше 16 адресов), в которую всё помещается. "
                  f"Сколько адресов VPC останется нераспределёнными?", free, family="h_vpc", topic="networks", level=level)


def h_layers(rng, level):
    has_ignore = rng.random() < 0.7
    ins = [("FROM python:3.12-slim", None), ("WORKDIR /app", None)]
    copy_req = ("COPY requirements.txt .", "requirements.txt")
    pip = ("RUN pip install -r requirements.txt", None)
    copy_cfg = ("COPY config/ ./config/", "config/")
    copy_all = ("COPY . .", "*")
    tail = [("RUN python -m compileall .", None), ("ENV PORT=8000", None), ("EXPOSE 8000", None), ('CMD ["python", "main.py"]', None)]
    order = [copy_req, pip]
    if rng.random() < 0.6:
        order.append(copy_cfg)
    order.append(copy_all)
    if rng.random() < 0.4:  # «неправильный» порядок: сначала копируем всё
        order = [copy_all] + [x for x in order if x is not copy_all]
    ins += order + tail
    files = ["requirements.txt", "main.py", "README.md", "config/app.yaml", "tests/test_a.py", "static/logo.png"]
    ign = ("README.md", "tests/") if has_ignore else ()

    def rebuilt(changed):
        for i, (line, ctx) in enumerate(ins):
            if ctx is None:
                continue
            if ctx == changed or (ctx.endswith("/") and changed.startswith(ctx)):
                return len(ins) - i
            if ctx == "*" and not any(changed == g or (g.endswith("/") and changed.startswith(g)) for g in ign):
                return len(ins) - i
        return 0
    scen = rng.sample(files, 3)
    total = sum(rebuilt(f) for f in scen)
    df = "\n".join(l for l, _ in ins)
    ignore_txt = ("\n\nФайл `.dockerignore`: " + ", ".join(f"`{x}`" for x in ign)) if ign else "\n\nФайла `.dockerignore` нет."
    sc = ", ".join(f"`{f}`" for f in scen)
    return number(f"Dockerfile:\n\n{_code(df, 'dockerfile')}{ignore_txt}\n\nОбраз полностью собран, все слои закэшированы. Рассмотрите три независимых сценария: "
                  f"в каждом изменяется ровно один файл — {sc} — и образ пересобирается из полностью закэшированного состояния. "
                  f"Сколько инструкций Dockerfile будет выполнено заново (не из кэша) суммарно по трём сценариям? "
                  f"(Считаются все инструкции, включая ENV, EXPOSE и CMD; слой пересобирается, если изменился его контекст или любой слой выше.)",
                  total, family="h_layers", topic="devops", level=level)


def h_firewall(rng, level):
    nets = ["10.0.0.0/8", "10.1.0.0/16", "10.1.2.0/24", "192.168.0.0/16", "192.168.5.0/24", "172.16.0.0/12", "0.0.0.0/0"]
    rules = []
    for _ in range(rng.randint(4, 5)):
        rules.append((rng.choice(["ALLOW", "DENY"]), rng.choice(nets), rng.choice(["*", "22", "80", "443"])))
    default = rng.choice(["ALLOW", "DENY"])
    pkts = []
    for _ in range(rng.randint(10, 13)):
        base = rng.choice(["10.1.2.", "10.1.9.", "10.7.0.", "192.168.5.", "192.168.9.", "172.20.1.", "8.8.8.", "10.0.0."])
        pkts.append((f"{base}{rng.randint(1, 250)}", rng.choice(["22", "80", "443", "8080"])))
    allowed = 0
    for ip, port in pkts:
        act = default
        for a, net, p in rules:
            if ipaddress.ip_address(ip) in ipaddress.ip_network(net) and (p == "*" or p == port):
                act = a; break
        allowed += int(port) if act == "ALLOW" else 0
    rt = "\n".join(f"{i + 1}. {a} src {n} dport {p}" for i, (a, n, p) in enumerate(rules))
    pt = ", ".join(f"({ip}, {pt})" for ip, pt in pkts)
    return number(f"Межсетевой экран применяет правила сверху вниз, срабатывает первое подходящее (по адресу источника и порту назначения), "
                  f"иначе действует политика по умолчанию — {default}.\n\n```\n{rt}\n```\n\nПакеты (src, dport): {pt}. Чему равна сумма номеров портов назначения пропущенных пакетов?",
                  allowed, family="h_firewall", topic="networks", level=level)


def h_swrr(rng, level):
    names = ["A", "B", "C"]
    weights = [rng.randint(1, 7) for _ in names]
    if len(set(weights)) == 1 and len(weights) > 1:
        weights[0] += 1
    cur = [0] * len(names)
    total = sum(weights)
    n = rng.randint(9, 18)
    seq = []
    for _ in range(n):
        cur = [c + w for c, w in zip(cur, weights)]
        i = cur.index(max(cur))
        seq.append(names[i])
        cur[i] -= total
    cnt = Counter(seq)
    target = rng.choice(names)
    return number(f"Балансировщик nginx использует smooth weighted round-robin (на каждом запросе к текущим весам прибавляются веса серверов, "
                  f"выбирается максимальный текущий вес — при равенстве первый по порядку, из него вычитается сумма весов). Серверы и веса: "
                  f"{', '.join(f'{a}={w}' for a, w in zip(names, weights))}. Сколько из первых {n} запросов получит сервер {target}, "
                  f"и в каком по счёту запросе сервер {target} обработает запрос впервые? Введите число: (число запросов)·100 + (номер первого запроса).",
                  cnt[target] * 100 + seq.index(target) + 1, family="h_swrr", topic="devops", level=level)


DEVOPS_HARD = [
    Family("h_binpack", (4, 5), h_binpack, ("devops",), 2.4), Family("h_errbudget", (4, 5), h_errbudget, ("devops",), 2.4),
    Family("h_vpc", (5,), h_vpc, ("devops",), 2.4), Family("h_layers", (4, 5), h_layers, ("devops",), 2.4),
    Family("h_firewall", (4, 5), h_firewall, ("devops",), 2.6), Family("h_swrr", (5,), h_swrr, ("devops",), 2.4),
]


# =========================================================================== QA
def h_pairwise(rng, level):
    sizes = [rng.randint(2, 4) for _ in range(rng.randint(3, 4))]
    names = "ABCD"[:len(sizes)]
    if level == 4:
        pairs = sum(a * b for a, b in itertools.combinations(sizes, 2))
        desc = ", ".join(f"{n}: {s} знач." for n, s in zip(names, sizes))
        return number(f"Параметры тестируемой формы: {desc}. Сколько различных пар «значение параметра X — значение параметра Y» (по всем парам параметров) "
                      f"нужно покрыть для всех пар (all-pairs)?", pairs, family="h_pairwise", topic="qa_theory", level=level)
    k = rng.randint(5, 6)
    tests = [tuple(rng.randrange(s) for s in sizes) for _ in range(k)]
    covered = set()
    for t in tests:
        for i, j in itertools.combinations(range(len(sizes)), 2):
            covered.add((i, j, t[i], t[j]))
    desc = ", ".join(f"{n}: значения 0..{s - 1}" for n, s in zip(names, sizes))
    return number(f"Параметры: {desc}. Набор тестов (по значению каждого параметра): `{tests}`. Сколько различных пар значений (по всем парам параметров) "
                  f"покрывает этот набор?", len(covered), family="h_pairwise", topic="qa_theory", level=level)


def h_bva(rng, level):
    params = []
    for _ in range(rng.randint(3, 5)):
        lo = rng.randint(0, 20)
        params.append((lo, lo + rng.choice([2, 3, 4, 10, 20, 50])))
    robust = level == 5
    base = [(lo + hi) // 2 for lo, hi in params]
    tests = {tuple(base)}
    for i, (lo, hi) in enumerate(params):
        vals = {lo, lo + 1, hi - 1, hi}
        if robust:
            vals |= {lo - 1, hi + 1}
        for v in vals:
            t = list(base); t[i] = v; tests.add(tuple(t))
    desc = ", ".join(f"p{i + 1} ∈ [{lo}, {hi}]" for i, (lo, hi) in enumerate(params))
    tp = "робастный анализ граничных значений: для каждого параметра берутся lo−1, lo, lo+1, hi−1, hi, hi+1" if robust else \
         "анализ граничных значений: для каждого параметра берутся lo, lo+1, hi−1, hi"
    return number(f"Целочисленные параметры: {desc}. Применяется {tp}, остальные параметры при этом равны номиналу (середина диапазона, целая часть). "
                  f"Тесты строятся по одному параметру, плюс один номинальный тест; одинаковые тесты не повторяются. Сколько различных тестов получится?",
                  len(tests), family="h_bva", topic="qa_theory", level=level)


def h_condcov(rng, level):
    def one():
        p, q, r = rng.randint(1, 9), rng.randint(1, 9), rng.randint(1, 9)
        return (p, q, r), f"(a > {p} and b < {q}) or c == {r}"
    (p1, q1, r1), e1 = one()
    (p2, q2, r2), e2 = one()
    tests = [(rng.randint(0, 10), rng.randint(0, 10), rng.randint(0, 10)) for _ in range(rng.randint(4, 5))]

    def cover(p, q, r):
        cond, dec = set(), set()
        for a, b, c in tests:
            c1 = a > p
            cond.add(("a", c1))
            res = False
            if c1:
                c2 = b < q
                cond.add(("b", c2))
                res = c2
            if not res:
                c3 = c == r
                cond.add(("c", c3))
                res = c3
            dec.add(res)
        return len(cond), len(dec)
    n1, d1 = cover(p1, q1, r1)
    n2, d2 = cover(p2, q2, r2)
    code = f"if {e1}:\n    first()\nif {e2}:\n    second()"
    return number(f"Две проверки:\n\n{_code(code)}\n\nТесты (a, b, c): `{tests}`; каждый тест выполняет оба `if`. Условия вычисляются с коротким замыканием (правая часть "
                  f"`and`/`or` не вычисляется, если результат уже известен). Для каждой проверки подсчитайте: N — сколько из шести пар «элементарное условие — значение» "
                  f"(три условия, True и False) вычислено хотя бы раз; D — сколько исходов решения (True/False) получено. Введите (N₁ + N₂)·10 + (D₁ + D₂).",
                  (n1 + n2) * 10 + d1 + d2, family="h_condcov", topic="qa_theory", level=level)


def h_mutation(rng, level):
    t1, t2, k, r = rng.randint(2, 8), rng.randint(3, 9), rng.randint(1, 4), rng.randint(0, 6)
    head = "def f(a, b):"
    body = f"    return (a > {t1} and b + {k} < {t2}) or a == {r}"
    src = head + "\n" + body
    muts = []
    # замены операторов и констант
    for tok, rep in ((">", ">="), ("<", "<="), ("==", "!="), ("+", "-"), (" and ", " or "), (" or ", " and ")):
        for m in re.finditer(re.escape(tok), body):
            if tok in (">", "<") and body[m.end():m.end() + 1] == "=":
                continue
            muts.append(body[:m.start()] + rep + body[m.end():])
    for val in (t1, t2, r):
        muts.append(body.replace(f"> {t1}", f"> {t1 + 1}", 1) if val == t1 else body.replace(f"< {t2}", f"< {t2 - 1}", 1) if val == t2 else body.replace(f"== {r}", f"== {r + 1}", 1))
    uniq = []
    for m in muts:
        if m != body and m not in uniq:
            uniq.append(m)
    rng.shuffle(uniq)
    muts = uniq[:8]
    tests = [(rng.randint(0, 10), rng.randint(0, 10)) for _ in range(rng.randint(4, 5))]

    def run(line, a, b):
        g = {}
        exec(head + "\n" + line, {"__builtins__": {}}, g)
        return g["f"](a, b)
    survived = [i + 1 for i, m in enumerate(muts) if all(run(m, a, b) == run(body, a, b) for a, b in tests)]
    ml = "\n".join(f"{i + 1}. `{m.strip()}`" for i, m in enumerate(muts))
    return number(f"Функция:\n\n{_code(src)}\n\nМутанты (заменена одна строка `return`):\n\n{ml}\n\nТесты (a, b): `{tests}`. Мутант «убит», если хотя бы на одном тесте "
                  f"его результат отличается от оригинала. Чему равна сумма номеров мутантов, которые ВЫЖИЛИ (0, если выживших нет)?", sum(survived),
                  family="h_mutation", topic="qa_theory", level=level)


def h_flaky(rng, level):
    p = rng.choice([0.01, 0.02, 0.03, 0.05, 0.08, 0.1, 0.12, 0.15, 0.2])
    n = rng.randint(20, 150)
    rr = rng.randint(1, 3)
    while (1 - p) ** n < 0.02 or (1 - p) ** n > 0.9:
        n = rng.randint(10, 150)
    if level == 4:
        green = (1 - p) ** n * 100
        return number(f"Набор из {n} независимых тестов; каждый ложно падает с вероятностью {p * 100:g}% (код корректен). Какова вероятность (в %), что "
                      f"весь набор пройдёт без единого падения? Округлите до десятых.", round(green, 1), tol=0.11, family="h_flaky", topic="qa_theory", level=level)
    green = (1 - p ** (rr + 1)) ** n * 100
    return number(f"Набор из {n} независимых тестов; каждый ложно падает с вероятностью {p * 100:g}%. Упавший тест перезапускается до {rr} раз(а) "
                  f"(итого до {rr + 1} попыток). Какова вероятность (в %), что весь набор в итоге окажется зелёным? Округлите до десятых.",
                  round(green, 1), tol=0.11, family="h_flaky", topic="qa_theory", level=level)


QA_HARD = [
    Family("h_pairwise", (4, 5), h_pairwise, ("qa",), 2.4), Family("h_bva", (4, 5), h_bva, ("qa",), 2.4),
    Family("h_condcov", (4, 5), h_condcov, ("qa",), 2.6), Family("h_mutation", (5,), h_mutation, ("qa",), 2.8),
    Family("h_flaky", (4, 5), h_flaky, ("qa",), 2.0),
]

HARD_SPEC = {"backend": BACKEND_HARD, "frontend": FRONTEND_HARD, "data": DATA_HARD, "devops": DEVOPS_HARD, "qa": QA_HARD}
HARD_ALL = COMMON_HARD + BACKEND_HARD + FRONTEND_HARD + DATA_HARD + DEVOPS_HARD + QA_HARD
