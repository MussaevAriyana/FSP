"""Резюме: автораспознавание PDF (эвристики + словарь стека) и генерация стандартизированного PDF-профиля.

Распознавание намеренно «мягкое»: результат — *предзаполнение формы*, которое кандидат проверяет и
исправляет. Заявленные в резюме данные в ранжировании не участвуют (см. matching.py), поэтому
ошибки распознавания не влияют на категорию.
"""
import io
import os
import re
from typing import Optional

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..taxonomy import ALL_STACK, GRADES, SOFT_SKILLS, SPECS, category_label
from ..techcatalog import CATALOG

STACK_ALIASES = {t['id']: t['aliases'] + [t['id']] for t in CATALOG}
SOFT_STEMS = {"Коммуникация": ["коммуникац", "communication"], "Работа в команде": ["в команде", "командн", "teamwork"],
              "Ответственность": ["ответственн"], "Самообучаемость": ["самообуч", "быстро обуча"], "Лидерство": ["лидер", "leadership"],
              "Ориентация на результат": ["на результат"], "Критическое мышление": ["критическ", "аналитическ"],
              "Наставничество": ["наставнич", "менторинг", "mentoring"]}
ROLE_WORDS = ["разработчик", "инженер", "аналитик", "тестировщик", "developer", "engineer", "qa ", "devops", "analyst",
              "data scientist", "sre", "стажёр", "стажер", "intern"]


def extract_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def _find_stack(text: str) -> list[str]:
    low = text.lower()
    found = []
    for tag in ALL_STACK:
        variants = STACK_ALIASES.get(tag, [tag])
        for v in variants:
            pat = r"(?<![\w#+.])" + re.escape(v) + r"(?![\w#+])"
            if re.search(pat, low):
                found.append(tag)
                break
    return found


def _experience(text: str) -> float:
    low = text.lower()
    m = re.findall(r"(\d{1,2}(?:[.,]\d)?)\s*\+?\s*(?:лет|года|год|years?|yrs)", low)
    if m:
        return min(max(float(x.replace(",", ".")) for x in m), 40.0)
    total = 0
    for a, b in re.findall(r"((?:19|20)\d{2})\s*[-–—]\s*((?:19|20)\d{2}|н\.?\s?в\.?|по настоящее|present)", low):
        end = 2026 if not b[:2].isdigit() else int(b)
        total += max(0, end - int(a))
    return float(min(total, 40))


def parse_resume(data: bytes) -> dict:
    text = extract_text(data)
    if len(text.strip()) < 20:
        raise ValueError("Не удалось извлечь текст из PDF (возможно, это скан). Заполните профиль вручную.")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    email = next(iter(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)), "")
    phone = next(iter(re.findall(r"\+?\d[\d\s\-()]{9,16}\d", text)), "").strip()
    name = ""
    for l in lines[:12]:
        l2 = re.sub(r"^(фио|имя|name)\s*[:\-]\s*", "", l, flags=re.I)
        if re.fullmatch(r"[A-ZА-ЯЁ][a-zа-яё]+(?:\s+[A-ZА-ЯЁ][a-zа-яё]+){1,2}", l2):
            name = l2
            break
    roles, seen = [], set()
    for l in lines:
        l = l.lstrip("•·-–— ").strip()
        ll = l.lower()
        if len(l) <= 80 and any(w in ll for w in ROLE_WORDS) and ll not in seen and "@" not in l:
            seen.add(ll)
            roles.append(l)
        if len(roles) >= 4:
            break
    low = text.lower()
    soft = [name_ for name_, stems in SOFT_STEMS.items() if any(s in low for s in stems)]
    spec_guess: Optional[str] = None
    best = 0
    for spec in SPECS:
        from ..taxonomy import STACK
        score = len(set(STACK[spec]) & set(_find_stack(text)))
        if score > best:
            best, spec_guess = score, spec
    return {"full_name": name, "email": email, "phone": phone, "stack_declared": _find_stack(text),
            "experience_years": _experience(text), "roles": roles, "soft_skills": soft, "spec_guess": spec_guess,
            "note": "Данные распознаны автоматически — проверьте и поправьте их перед сохранением."}


# ------------------------------------------------------------------------------ генерация PDF
_FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
]
_fonts_ready = False


def _register_fonts():
    global _fonts_ready
    if _fonts_ready:
        return
    env = os.environ.get("PDF_FONT_REGULAR"), os.environ.get("PDF_FONT_BOLD")
    for reg, bold in ([env] if all(env) else []) + _FONT_CANDIDATES:
        if os.path.exists(reg) and os.path.exists(bold):
            pdfmetrics.registerFont(TTFont("AppSans", reg))
            pdfmetrics.registerFont(TTFont("AppSans-Bold", bold))
            _fonts_ready = True
            return
    raise RuntimeError("Не найден шрифт с кириллицей для PDF. Установите fonts-dejavu-core или задайте PDF_FONT_REGULAR/PDF_FONT_BOLD.")


PURPLE, PURPLE_DARK, LAV = colors.HexColor("#5B0F8F"), colors.HexColor("#2E0A4F"), colors.HexColor("#F1E7FB")


LEVELS_RU = {"secondary": "Среднее общее", "college": "Среднее профессиональное", "bachelor": "Бакалавр", "specialist": "Специалитет", "master": "Магистр",
             "phd": "Аспирантура / кандидат наук", "courses": "Курсы, переподготовка"}
EMP_RU = {"full": "полная занятость", "part": "частичная", "project": "проектная", "internship": "стажировка"}
SCH_RU = {"office": "офис", "remote": "удалённо", "hybrid": "гибрид", "shift": "сменный график"}
YN_RU = {"no": "нет", "yes": "да", "maybe": "возможно", "rarely": "редко"}
MAR_RU = {"single": "не женат / не замужем", "married": "женат / замужем", "divorced": "разведён / разведена", "widowed": "вдовец / вдова"}
KIDS_RU = {"none": "нет", "one": "один ребёнок", "two": "двое детей", "three_plus": "трое и более"}
MIL_RU = {"served": "служил(а)", "reserve": "в запасе", "exempt": "освобождён(а)", "not_liable": "не военнообязан(а)", "student": "отсрочка (учёба)"}
LANG_LEVEL = {"native": "родной", "A1": "A1", "A2": "A2", "B1": "B1", "B2": "B2", "C1": "C1", "C2": "C2"}


def resume_advice(rs: dict, cand: dict) -> list[dict]:
    """Проверка резюме по общепринятым требованиям к ИТ-резюме. Это подсказки, а не запреты: severity = warn | tip."""
    out = []
    add = lambda sev, text: out.append({"severity": sev, "text": text})
    if not rs.get("desired_position"):
        add("warn", "Укажите желаемую должность — по ней резюме находят и сравнивают.")
    summ = (rs.get("summary") or "").strip()
    if not summ:
        add("warn", "Добавьте короткое «О себе» (2–4 предложения): роль, главный опыт, что ищете.")
    elif len(summ) > 700:
        add("tip", "«О себе» длиннее 700 знаков — лучше сократить до 2–4 предложений.")
    if not rs.get("salary_expectation"):
        add("tip", "Желаемая зарплата не указана — работодателю сложнее предложить подходящие условия.")
    exp = rs.get("experience") or []
    if not exp:
        add("tip", "Нет опыта работы? Добавьте стажировки, фриланс, участие в ФСП или проекты — это тоже опыт.")
    for e in exp:
        label = e.get("position") or e.get("company") or "место работы"
        if not e.get("start"):
            add("warn", f"«{label}»: не указана дата начала — в резюме принято указывать период работы.")
        if not (e.get("description") or "").strip():
            add("tip", f"«{label}»: опишите обязанности и достижения.")
        elif not any(ch.isdigit() for ch in e["description"]):
            add("tip", f"«{label}»: добавьте измеримый результат (цифры, сроки, масштаб) — это сильнее общих слов.")
    if not rs.get("education"):
        add("tip", "Добавьте образование: учебное заведение, специальность, годы. Курсы тоже подойдут.")
    if not (rs.get("links") or {}).get("github") and not rs.get("projects"):
        add("tip", "Для ИТ-резюме полезны ссылки на репозиторий (GitHub) или проекты.")
    if not rs.get("languages"):
        add("tip", "Укажите языки и уровень (по шкале A1–C2): английский важен во многих ИТ-вакансиях.")
    if not cand.get("phone") or not cand.get("full_name"):
        add("warn", "В профиле нет ФИО или телефона — работодатель получит их при принятии приглашения.")
    if (rs.get("personal") or {}).get("marital_status") or (rs.get("personal") or {}).get("children"):
        add("tip", "Семейное положение и дети необязательны. Работодатель не вправе требовать их для приёма на работу — показывайте их только если хотите.")
    return out


def build_profile_pdf(cand: dict, fsp: Optional[dict], email: str, include_personal: bool = False, masked: bool = False) -> bytes:
    """Резюме в PDF по привычной структуре: шапка с контактами и желаемой должностью → «О себе» → опыт (от новых к старым) → образование →
    навыки → языки → проекты → сертификаты → дополнительно, плюс блок «Подтверждено платформой» (категория, тест, ФСП).
    masked=True — версия для работодателя до принятия приглашения: без имени, контактов, названий компаний и вузов, ссылок."""
    _register_fonts()
    st = lambda **kw: ParagraphStyle("s", fontName=kw.pop("fn", "AppSans"), fontSize=kw.pop("fs", 10), leading=kw.pop("ld", 14), **kw)
    h1, h2, body, small = st(fn="AppSans-Bold", fs=18, ld=22, textColor=PURPLE_DARK), st(fn="AppSans-Bold", fs=12, ld=16, textColor=PURPLE, spaceBefore=10, spaceAfter=4), st(), st(fs=8.5, ld=12, textColor=colors.grey)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title="Резюме — ФСП Карьера")
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    rs = cand.get("resume") or {}
    hid = "(скрыто до принятия приглашения)"
    name = cand.get("pseudo_code") or "Кандидат" if masked else (cand.get("full_name") or "Имя не указано")
    story = [Paragraph("ФСП Карьера · Резюме", st(fs=9, ld=12, textColor=PURPLE)), Spacer(1, 3), Paragraph(esc(name), h1)]
    pos = rs.get("desired_position") or cand.get("headline") or ""
    if pos:
        story.append(Paragraph(esc(pos) + (f" · от {rs['salary_expectation']:,} ₽".replace(",", " ") if rs.get("salary_expectation") else ""), st(fn="AppSans-Bold", fs=11, ld=15)))
    contacts = []
    if not masked:
        contacts += [f"Email: {email}"] + ([f"Телефон: {cand['phone']}"] if cand.get("phone") else [])
    if cand.get("city") and (not masked or cand.get("_show_city")):
        contacts.append(f"Город: {cand['city']}")
    links = rs.get("links") or {}
    if not masked:
        contacts += [f"{k.capitalize()}: {v}" for k, v in links.items() if v]
    if contacts:
        story.append(Paragraph(esc(" · ".join(contacts)), small))
    wishes = []
    if rs.get("employment_types"):
        wishes.append("занятость: " + ", ".join(EMP_RU.get(x, x) for x in rs["employment_types"]))
    if rs.get("schedules"):
        wishes.append("формат: " + ", ".join(SCH_RU.get(x, x) for x in rs["schedules"]))
    if rs.get("relocation"):
        wishes.append("переезд: " + YN_RU.get(rs["relocation"], ""))
    if rs.get("business_trips"):
        wishes.append("командировки: " + YN_RU.get(rs["business_trips"], ""))
    if wishes:
        story.append(Paragraph(esc("; ".join(wishes)), small))

    cat = category_label(cand.get("spec"), cand.get("grade"))
    ver = [[Paragraph("<b>Категория</b>", body), Paragraph(esc(cat), body)]]
    if cand.get("grade"):
        ver.append([Paragraph("<b>Результат теста</b>", body), Paragraph(f"{round(cand.get('best_score', 0) * 100)}% (зачёт: 65% Стажёр и Junior, 70% Middle, 80% Senior)", body)])
        ver.append([Paragraph("<b>Подтверждённый стек</b>", body), Paragraph(esc(", ".join(cand.get("stack_confirmed") or []) or "—"), body)])
    ver.append([Paragraph("<b>Опыт ФСП</b>", body),
                Paragraph(esc(f"{fsp['events_count']} мероприятий; лучший результат: топ-{fsp['best_top_percent']:g}% ({fsp['best_event']})") if fsp else "истории участия нет", body)])
    t = Table(ver, colWidths=[48 * mm, 120 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LAV), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.white), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [Paragraph("Подтверждено платформой", h2), t]

    about = rs.get("summary") or cand.get("about") or ""
    if about:
        story += [Paragraph("О себе", h2), Paragraph(esc(about), body)]
    exp = sorted(rs.get("experience") or [], key=lambda e: e.get("start") or "", reverse=True)
    if exp or cand.get("experience_years"):
        story.append(Paragraph("Опыт работы" + (f" · общий стаж {cand.get('experience_years', 0):g} лет" if cand.get("experience_years") else ""), h2))
    for e in exp:
        company = (hid if masked else e.get("company")) if e.get("company") else ""
        story.append(Paragraph(f"<b>{esc(e.get('position') or '')}</b>{', ' + esc(company) if company else ''} ({esc(e.get('start') or '…')} — {esc(e.get('end') or 'по настоящее время')})", body))
        if e.get("description"):
            story.append(Paragraph(esc(e["description"]), small))
    if not exp:
        for r in cand.get("roles") or []:
            story.append(Paragraph("• " + esc(r), body))
    if rs.get("education"):
        story.append(Paragraph("Образование", h2))
        for x in rs["education"]:
            inst = (hid if masked else x.get("institution")) or ""
            lvl = LEVELS_RU.get(x.get("level"), "")
            story.append(Paragraph(esc(f"{inst}. {lvl} {x.get('degree') or ''} {x.get('specialty') or ''} ({x.get('year_from') or ''}–{x.get('year_to') or ''})".replace("  ", " ")), body))
    skills = list(cand.get("stack_declared") or [])
    if skills:
        story += [Paragraph("Навыки", h2), Paragraph(esc(", ".join(skills)), body)]
    if rs.get("languages"):
        story += [Paragraph("Языки", h2), Paragraph(esc(", ".join(f"{x['name']} — {LANG_LEVEL.get(x.get('level'), '')}".rstrip(' —') for x in rs["languages"] if x.get("name"))), body)]
    if rs.get("projects"):
        story.append(Paragraph("Проекты", h2))
        for x in rs["projects"]:
            link = "" if masked else x.get("link")
            story.append(Paragraph(f"<b>{esc(x.get('name') or '')}</b>" + (f" — {esc(x['role'])}" if x.get("role") else "") + (f" · {esc(link)}" if link else ""), body))
            if x.get("description"):
                story.append(Paragraph(esc(x["description"]), small))
    if rs.get("certificates"):
        story.append(Paragraph("Дипломы и сертификаты", h2))
        kinds = {"certificate": "Сертификат", "diploma": "Диплом", "award": "Награда"}
        for x in rs["certificates"]:
            story.append(Paragraph(esc(f"{kinds.get(x.get('kind'), '')}: {x.get('name') or ''} — {x.get('issuer') or ''}, {x.get('year') or ''}"), body))
    if cand.get("soft_skills"):
        story += [Paragraph("Личные качества", h2), Paragraph(esc(", ".join(cand["soft_skills"])), body)]
    pr = rs.get("personal") or {}
    if include_personal and pr:
        lines = []
        if pr.get("birth_year"):
            lines.append(f"Год рождения: {pr['birth_year']}")
        if pr.get("citizenship"):
            lines.append(f"Гражданство: {pr['citizenship']}")
        if pr.get("marital_status"):
            lines.append(f"Семейное положение: {MAR_RU.get(pr['marital_status'], '')}")
        if pr.get("children"):
            lines.append(f"Дети: {KIDS_RU.get(pr['children'], '')}")
        if pr.get("military"):
            lines.append(f"Воинская обязанность: {MIL_RU.get(pr['military'], '')}")
        if pr.get("driving"):
            lines.append(f"Водительские права: {pr['driving']}")
        if lines:
            story += [Paragraph("Дополнительно", h2)] + [Paragraph(esc(x), body) for x in lines]
    story += [Spacer(1, 10), Paragraph("Блок «Подтверждено платформой» сформирован автоматически по результатам тестирования и данным ФСП. Остальные поля заполнены кандидатом."
                                       + (" Версия для работодателя: имя, контакты, названия компаний и вузов, ссылки скрыты до принятия приглашения." if masked else ""), small)]
    doc.build(story)
    return buf.getvalue()
