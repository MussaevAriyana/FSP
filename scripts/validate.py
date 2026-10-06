"""Собственная процедура валидации (docs/DOCUMENTATION.md §6).

Запуск:  python3 scripts/validate.py            (≈1–2 минуты, детерминирован: seed=2026)
Выход:   docs/validation_results.json и docs/VALIDATION_RESULTS.md

Что проверяется на синтетической популяции (модель — scripts/simulate.py):
  A. Уникальность тестов и защита от утечки заданий (пересечение между попытками, покрытие «слитым» банком).
  B. Эквивалентность сложности вариантов одного грейда (разброс результата при одной и той же способности).
  C. Дискриминация: матрица «истинный грейд × проходимый грейд», процент зачёта.
  D. Надёжность: повторное прохождение (test–retest), согласие зачёт/незачёт, Cohen's kappa, корреляция.
  E. Атаки: случайное угадывание, «списывание» чужих ответов, ответы с чужого варианта.
  F. Подбор: P@10 и nDCG@10 ранжирования платформы против базовой линии «по самоописанному резюме».

ОГРАНИЧЕНИЕ: всё это — модель с допущениями, а не реальные кандидаты. Пайплайн проверяется честно,
содержательная валидность требует калибровки на реальных данных (см. §6.5 документации).
"""
import json
import math
import random
import statistics as st
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app.services import engine, matching  # noqa: E402
from app.taxonomy import GRADE_ORDER, SPECS, STACK  # noqa: E402
from simulate import THETA_OFFSET, draw_theta, p_correct, simulate_answers  # noqa: E402

SEED = 2026
PASS = 0.65
rng = random.Random(SEED)
SPEC_LIST = list(SPECS)
R = {}


def take(spec, grade, theta, seed, r):
    qs = engine.build_test(spec, grade, str(seed))
    ans = simulate_answers(qs, theta, r)
    return qs, engine.grade_answers(qs, ans, grade, PASS)


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def pearson(x, y):
    mx, my = st.fmean(x), st.fmean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x)); sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy) if sx and sy else 0.0


# ---------- A. уникальность и утечка ----------
def exp_uniqueness(n_attempts=300, pairs=20000):
    out = {}
    for spec, grade in [("backend", "middle"), ("frontend", "junior"), ("data", "senior"), ("devops", "trainee"), ("qa", "middle")]:
        tests = [engine.build_test(spec, grade, f"u{i}") for i in range(n_attempts)]
        sig = [[(q["prompt"], tuple(sorted(q.get("options", ())))) for q in t] for t in tests]
        ans = [[(q["prompt"], q["answer"]) for q in t] for t in tests]
        same_q = same_a = 0
        total = 0
        for _ in range(pairs):
            i, j = rng.sample(range(n_attempts), 2)
            si, sj = set(sig[i]), set(sig[j])
            same_q += len(si & sj)
            ai, aj = set(ans[i]), set(ans[j])
            same_a += len(ai & aj)
            total += len(tests[i])
        # покрытие: доля заданий нового теста, чьё (условие, ответ) есть в «слитом» банке из N попыток
        cov = {}
        bank_tests = [set(x) for x in ans]
        fresh = [engine.build_test(spec, grade, f"fresh{i}") for i in range(100)]
        for N in (1, 10, 100, 300):
            bank = set().union(*bank_tests[:N])
            hit = [sum((q["prompt"], q["answer"]) in bank for q in t) / len(t) for t in fresh]
            full = sum(h == 1 for h in hit)
            cov[N] = {"mean_share_known": round(st.fmean(hit), 4), "max_share_known": round(max(hit), 3), "tests_fully_covered": full}
        out[f"{spec}/{grade}"] = {"questions_per_test": len(tests[0]), "pairwise_same_question_share": round(same_q / total, 4),
                                   "pairwise_same_prompt_answer_share": round(same_a / total, 4),
                                   "families_per_test_mean": round(st.fmean(len({q["family"] for q in t}) for t in tests), 2),
                                   "leak_coverage_by_bank_size": cov}
    return out


# ---------- B+C. эквивалентность, дискриминация ----------
def exp_discrimination(n=250):
    mat = {}
    ratio_sd = {}
    for gi, g in enumerate(GRADE_ORDER):
        for ti, tg in enumerate(GRADE_ORDER):
            passed = 0
            ratios = []
            for k in range(n):
                spec = SPEC_LIST[k % len(SPEC_LIST)]
                theta = draw_theta(gi, rng)
                _, res = take(spec, tg, theta, f"d{gi}{ti}{k}", rng)
                passed += res["passed"]
                ratios.append(res["ratio"])
            mat[f"{g}->{tg}"] = round(passed / n, 3)
            ratio_sd[f"{g}->{tg}"] = round(st.pstdev(ratios), 3)
    # эквивалентность: фиксированная способность = центр грейда, 400 разных вариантов
    eq = {}
    for gi, g in enumerate(GRADE_ORDER):
        rs = []
        for k in range(400):
            spec = SPEC_LIST[k % len(SPEC_LIST)]
            qs = engine.build_test(spec, g, f"e{gi}{k}")
            # ожидаемая доля баллов при θ=gi (без шума ответов): средняя вероятность, взвешенная уровнем
            num = sum(q["level"] * p_correct(gi + THETA_OFFSET, q["level"], q["kind"]) for q in qs)
            den = sum(q["level"] for q in qs)
            rs.append(num / den)
        eq[g] = {"expected_ratio_mean": round(st.fmean(rs), 3), "expected_ratio_sd": round(st.pstdev(rs), 4),
                 "min": round(min(rs), 3), "max": round(max(rs), 3)}
    return {"pass_rate_matrix": mat, "ratio_sd": ratio_sd, "variant_equivalence": eq}


# ---------- D. надёжность ----------
def exp_reliability(n=600):
    out = {}
    for gi, g in enumerate(GRADE_ORDER):
        a, b, ra, rb = [], [], [], []
        for k in range(n):
            spec = SPEC_LIST[k % len(SPEC_LIST)]
            theta = draw_theta(gi, rng)
            _, x = take(spec, g, theta, f"r{gi}a{k}", rng)
            _, y = take(spec, g, theta, f"r{gi}b{k}", rng)
            a.append(int(x["passed"])); b.append(int(y["passed"])); ra.append(x["ratio"]); rb.append(y["ratio"])
        out[g] = {"pass_rate": round(st.fmean(a), 3), "agreement": round(sum(i == j for i, j in zip(a, b)) / n, 3),
                  "kappa": round(kappa(a, b), 3), "ratio_pearson_r": round(pearson(ra, rb), 3)}
    # устойчивость категории: кандидат с истинным грейдом g проходит «лесенку»; доля стабильных категорий при повторе
    stable = 0
    m = 800
    def ladder(spec, gi, theta, tag):
        # начинает с заявленного = истинному; категория = самый высокий пройденный из {g, g+1}
        cat = None
        for tg in GRADE_ORDER[max(0, gi - 1): min(3, gi + 1) + 1]:
            _, res = take(spec, tg, theta, f"{tag}{tg}", rng)
            if res["passed"]:
                cat = tg
        return cat
    for k in range(m):
        gi = rng.randrange(4); spec = SPEC_LIST[k % 5]; theta = draw_theta(gi, rng)
        stable += ladder(spec, gi, theta, f"s{k}a") == ladder(spec, gi, theta, f"s{k}b")
    out["category_stability_ladder"] = round(stable / m, 3)
    return out


# ---------- E. атаки ----------
def exp_attacks(n=1500):
    out = {}
    for g in GRADE_ORDER:
        guess_pass = copy_pass = copy_ratio = 0
        for k in range(n):
            spec = SPEC_LIST[k % 5]
            qs = engine.build_test(spec, g, f"g{g}{k}")
            # случайный угадыватель: на choice — случайный вариант, на number — случайное число
            ans = {q["id"]: (rng.randrange(4) if q["kind"] == "choice" else rng.randint(0, 100)) for q in qs}
            guess_pass += engine.grade_answers(qs, ans, g, PASS)["passed"]
            # «списывание»: ответы друга (идеальные!) на его варианте теста подставляются в свой вариант по номеру задания
            friend = engine.build_test(spec, g, f"friend{g}{k}")
            ans2 = {q["id"]: f["answer"] for q, f in zip(qs, friend)}
            res = engine.grade_answers(qs, ans2, g, PASS)
            copy_pass += res["passed"]; copy_ratio += res["ratio"]
        out[g] = {"random_guess_pass_rate": round(guess_pass / n, 4), "copy_perfect_friend_pass_rate": round(copy_pass / n, 4),
                  "copy_perfect_friend_mean_ratio": round(copy_ratio / n, 3)}
    return out


# ---------- G. чувствительность к допущению о способности ----------
def exp_sensitivity(n=200):
    import simulate as S
    out = {}
    keep = S.THETA_OFFSET
    try:
        for off in (0.6, 0.9, 1.2, 1.5):
            S.THETA_OFFSET = off
            row = {}
            for gi, g in enumerate(GRADE_ORDER):
                own = up = down = 0
                for k in range(n):
                    spec = SPEC_LIST[k % 5]; t = draw_theta(gi, rng)
                    own += take(spec, g, t, f"s{off}{gi}{k}", rng)[1]["passed"]
                    if gi < 3:
                        up += take(spec, GRADE_ORDER[gi + 1], t, f"u{off}{gi}{k}", rng)[1]["passed"]
                    if gi > 0:
                        down += take(spec, GRADE_ORDER[gi - 1], t, f"w{off}{gi}{k}", rng)[1]["passed"]
                row[g] = {"own": round(own / n, 2), "next_up": round(up / n, 2) if gi < 3 else None, "one_below": round(down / n, 2) if gi else None}
            out[str(off)] = row
    finally:
        S.THETA_OFFSET = keep
    return out


# ---------- F. подбор ----------
def exp_matching(n_cand=700, n_needs=150, p_over=0.25, p_under=0.10):
    now = datetime.now(timezone.utc)
    cands = []
    for i in range(n_cand):
        gi = rng.choices(range(4), [0.3, 0.3, 0.25, 0.15])[0]
        spec = rng.choice(SPEC_LIST)
        theta = draw_theta(gi, rng)
        u = rng.random()
        claim = min(3, gi + 1) if u < p_over else max(0, gi - 1) if u < p_over + p_under else gi
        # самоописание: завышение стека у 40% (добавляют типичные технологии без подтверждения)
        decl = set(rng.sample(STACK[spec], min(len(STACK[spec]), rng.randint(2, 4))))
        if rng.random() < 0.4:
            decl |= set(rng.sample(STACK[spec], min(len(STACK[spec]), 5)))
        # путь платформы: тест на заявленный грейд, при провале — ниже
        cat = None; best = None
        for tg in range(claim, -1, -1):
            qs, res = take(spec, GRADE_ORDER[tg], theta, f"m{i}{tg}", rng)
            if res["passed"]:
                cat, best = tg, (qs, res); break
        if cat is None:
            continue
        fsp = None
        if rng.random() < 0.45:
            fsp = {"strength": min(1, max(0, 0.45 + 0.1 * (gi - 1) + rng.gauss(0, 0.2))), "events_count": rng.randint(1, 5),
                   "best_top_percent": 10.0, "best_event": "Открытый кубок ФСП"}
        last = (now - timedelta(days=rng.randint(0, 150))).strftime("%Y-%m-%dT%H:%M:%SZ")
        cands.append({"true_spec": spec, "true_grade": gi, "claim_grade": claim, "declared": decl,
                      "spec": spec, "grade": GRADE_ORDER[cat], "ratio": best[1]["ratio"],
                      "stack_confirmed": engine.confirmed_stack(best[1]["topics"]), "fsp": fsp, "last_activity_at": last,
                      "micro_bonus": 0.0, "integrity_review": False})
    def rel(c, need):
        if c["true_spec"] != need["spec"]:
            return 0
        d = abs(c["true_grade"] - GRADE_ORDER.index(need["grade"]))
        return 3 if d == 0 else 1 if d == 1 else 0
    def ndcg(gains):
        dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains[:10]))
        ideal = sorted(gains, reverse=True)
        return dcg  # нормируем снаружи
    res = {"platform": {"p10": [], "ndcg10": []}, "baseline_self_description": {"p10": [], "ndcg10": []}}
    for _ in range(n_needs):
        spec = rng.choice(SPEC_LIST); grade = rng.choice(GRADE_ORDER); stack = rng.sample(STACK[spec], 3)
        need = {"spec": spec, "grade": grade, "stack": stack}
        gains_all = sorted((rel(c, need) for c in cands), reverse=True)
        idcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains_all[:10])) or 1.0
        # платформа
        ranked = sorted(cands, key=lambda c: -matching.score_candidate(need, c, now)["score"])
        # базовая линия: по самоописанию — совпадение спец-ции, заявленного грейда и заявленного стека
        base = sorted(cands, key=lambda c: -((2.0 if c["true_spec"] == spec else 0) + (1.5 if GRADE_ORDER[c["claim_grade"]] == grade else 0)
                                              + len(c["declared"] & set(stack)) / 3))
        for name, lst in (("platform", ranked), ("baseline_self_description", base)):
            g10 = [rel(c, need) for c in lst[:10]]
            res[name]["p10"].append(sum(x == 3 for x in g10) / 10)
            res[name]["ndcg10"].append(ndcg(g10) / idcg)
    out = {k: {m: round(st.fmean(v), 3) for m, v in d.items()} for k, d in res.items()}
    out["population"] = {"candidates_with_category": len(cands), "needs": n_needs,
                         "claim_overstated_share": round(st.fmean(c["claim_grade"] > c["true_grade"] for c in cands), 3),
                         "category_equals_true_share": round(st.fmean(GRADE_ORDER[c["true_grade"]] == c["grade"] for c in cands), 3)}
    return out


def md(r):
    L = ["# Результаты валидации (синтетическая популяция)", "",
         f"Сгенерировано `scripts/validate.py`, seed={SEED}. **Это модель, а не реальные кандидаты** — см. оговорки в §6.5 документации.", ""]
    L += ["## A. Уникальность и утечка", "", "| Категория | Заданий | Совпадающих заданий между двумя попытками | Совпадение «условие+ответ» | Видимое «слитым» банком из 300 попыток |", "|---|---|---|---|---|"]
    for k, v in r["uniqueness"].items():
        L.append(f"| {k} | {v['questions_per_test']} | {v['pairwise_same_question_share']*100:.2f}% | {v['pairwise_same_prompt_answer_share']*100:.2f}% | {v['leak_coverage_by_bank_size'][300]['mean_share_known']*100:.1f}% (макс. {v['leak_coverage_by_bank_size'][300]['max_share_known']*100:.0f}%) |")
    L += ["", "## B. Эквивалентность вариантов одного грейда", "", "| Грейд | Ожидаемая доля баллов (ср.) | SD между вариантами | мин | макс |", "|---|---|---|---|---|"]
    for g, v in r["discrimination"]["variant_equivalence"].items():
        L.append(f"| {g} | {v['expected_ratio_mean']} | {v['expected_ratio_sd']} | {v['min']} | {v['max']} |")
    L += ["", "## C. Дискриминация: доля зачёта (строка — истинный грейд, столбец — проходимый тест)", "", "| | " + " | ".join(GRADE_ORDER) + " |", "|---|" + "---|" * 4]
    for g in GRADE_ORDER:
        L.append(f"| **{g}** | " + " | ".join(f"{r['discrimination']['pass_rate_matrix'][f'{g}->{t}']*100:.0f}%" for t in GRADE_ORDER) + " |")
    L += ["", "## D. Надёжность (повторное прохождение, тот же уровень, новые варианты)", "", "| Грейд | Зачёт | Согласие | κ Коэна | r (доля баллов) |", "|---|---|---|---|---|"]
    for g in GRADE_ORDER:
        v = r["reliability"][g]
        L.append(f"| {g} | {v['pass_rate']*100:.0f}% | {v['agreement']*100:.0f}% | {v['kappa']} | {v['ratio_pearson_r']} |")
    L += ["", f"Устойчивость присвоенной категории при повторной «лесенке» тестов: **{r['reliability']['category_stability_ladder']*100:.0f}%**.", "",
          "## E. Атаки", "", "| Грейд | Случайное угадывание: зачёт | Списывание идеальных ответов друга: зачёт | …средняя доля баллов |", "|---|---|---|---|"]
    for g in GRADE_ORDER:
        v = r["attacks"][g]
        L.append(f"| {g} | {v['random_guess_pass_rate']*100:.2f}% | {v['copy_perfect_friend_pass_rate']*100:.2f}% | {v['copy_perfect_friend_mean_ratio']*100:.0f}% |")
    L += ["", "## G. Чувствительность к допущению о способности (сдвиг θ; базовое значение — 1.2)", "", "| Сдвиг | Грейд | Зачёт своего теста | Зачёт теста на ступень выше | Зачёт теста на ступень ниже |", "|---|---|---|---|---|"]
    for off, row in r["sensitivity"].items():
        for g, v in row.items():
            f = lambda x: "—" if x is None else f"{x*100:.0f}%"
            L.append(f"| {off} | {g} | {f(v['own'])} | {f(v['next_up'])} | {f(v['one_below'])} |")
    L += ["", "## F. Подбор: платформа против ранжирования по самоописанному резюме", "",
          "Условие — доля кандидатов, завысивших грейд в самооценке. Ground truth — истинные специализация и грейд.", "",
          "| Завысили грейд | Метод | Precision@10 (точная категория) | nDCG@10 |", "|---|---|---|---|"]
    for p, m in r["matching"].items():
        L.append(f"| {float(p)*100:.0f}% | Платформа (категория по тесту + подтверждённые данные) | {m['platform']['p10']} | {m['platform']['ndcg10']} |")
        L.append(f"| | Базовая линия (самоописание) | {m['baseline_self_description']['p10']} | {m['baseline_self_description']['ndcg10']} |")
    pop = r["matching"]["0.25"]["population"]
    L += ["", f"Популяция: ≈{pop['candidates_with_category']} кандидатов с категорией, {pop['needs']} потребностей; при 25% завышений категория по тесту совпала с истинной у {pop['category_equals_true_share']*100:.0f}% кандидатов (остальные — шум теста и «везение» на ступень выше)."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    for name, fn in [("uniqueness", exp_uniqueness), ("discrimination", exp_discrimination), ("reliability", exp_reliability),
                     ("attacks", exp_attacks), ("matching", lambda: {str(p): exp_matching(p_over=p, p_under=0.10) for p in (0.0, 0.25, 0.5, 0.75)}), ("sensitivity", exp_sensitivity)]:
        print("→", name, flush=True)
        R[name] = fn()
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "validation_results.json").write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "docs" / "VALIDATION_RESULTS.md").write_text(md(R), encoding="utf-8")
    print((ROOT / "docs" / "VALIDATION_RESULTS.md").read_text(encoding="utf-8"))
