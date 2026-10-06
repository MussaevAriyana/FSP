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

STACK_ALIASES = {
    "javascript": ["javascript", "js", "ecmascript"], "typescript": ["typescript", "ts"], "nodejs": ["node.js", "nodejs", "node js"],
    "postgresql": ["postgresql", "postgres", "постгрес"], "kubernetes": ["kubernetes", "k8s", "кубернетес"],
    "csharp": ["c#", ".net", "dotnet"], "go": ["golang", "go lang"], "ci_cd": ["ci/cd", "ci-cd", "gitlab ci", "github actions", "jenkins"],
    "ml": ["machine learning", "машинное обучение", "scikit-learn", "sklearn", "pytorch", "tensorflow"],
    "pandas": ["pandas", "numpy"], "statistics": ["statistics", "статистик", "a/b"], "rest": ["rest", "restful", "openapi", "swagger"],
    "api_testing": ["postman", "api testing", "тестирование api"], "manual": ["ручное тестирование", "manual testing", "тест-кейс", "тест-кейсы"],
    "networks": ["tcp/ip", "dns", "сети", "networking"], "bash": ["bash", "shell"], "react": ["react", "react.js", "reactjs"],
    "vue": ["vue", "vue.js"], "angular": ["angular"], "html": ["html", "html5"], "css": ["css", "css3", "scss"],
}
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


def build_profile_pdf(cand: dict, fsp: Optional[dict], email: str) -> bytes:
    """Стандартизированный PDF-профиль: самоописанные данные + блок «подтверждено платформой»."""
    _register_fonts()
    st = lambda **kw: ParagraphStyle("s", fontName=kw.pop("fn", "AppSans"), fontSize=kw.pop("fs", 10), leading=kw.pop("ld", 14), **kw)
    h1, h2, body, small = st(fn="AppSans-Bold", fs=18, ld=22, textColor=PURPLE_DARK), st(fn="AppSans-Bold", fs=12, ld=16, textColor=PURPLE, spaceBefore=10, spaceAfter=4), st(), st(fs=8.5, ld=12, textColor=colors.grey)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title="Профиль кандидата — ФСП Карьера")
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    story = [Paragraph("ФСП Карьера · Профиль кандидата", st(fs=9, ld=12, textColor=PURPLE)), Spacer(1, 3),
             Paragraph(esc(cand.get("full_name") or "Имя не указано"), h1),
             Paragraph(esc(cand.get("headline") or ""), body)]
    contacts = [f"ФИО: {cand.get('full_name') or '—'}", f"Email: {email}"]
    if cand.get("phone"):
        contacts.append(f"Телефон: {cand['phone']}")
    if cand.get("city"):
        contacts.append(f"Город: {cand['city']}")
    story += [Paragraph("Контакты", h2)] + [Paragraph(esc(c), body) for c in contacts]

    cat = category_label(cand.get("spec"), cand.get("grade"))
    ver = [[Paragraph("<b>Категория</b>", body), Paragraph(esc(cat), body)]]
    if cand.get("grade"):
        ver.append([Paragraph("<b>Результат теста</b>", body), Paragraph(f"{round(cand.get('best_score', 0) * 100)}% (порог зачёта 65%)", body)])
        ver.append([Paragraph("<b>Подтверждённый стек</b>", body), Paragraph(esc(", ".join(cand.get("stack_confirmed") or []) or "—"), body)])
    if fsp:
        ver.append([Paragraph("<b>Опыт ФСП</b>", body),
                    Paragraph(esc(f"{fsp['events_count']} мероприятий; лучший результат: топ-{fsp['best_top_percent']:g}% ({fsp['best_event']})"), body)])
    else:
        ver.append([Paragraph("<b>Опыт ФСП</b>", body), Paragraph("истории участия нет", body)])
    t = Table(ver, colWidths=[48 * mm, 120 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LAV), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.white), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [Paragraph("Подтверждено платформой", h2), t]

    story += [Paragraph("О себе", h2), Paragraph(esc(cand.get("about") or "—"), body),
              Paragraph("Опыт и роли", h2), Paragraph(esc(f"Стаж: {cand.get('experience_years', 0):g} лет"), body)]
    for r in cand.get("roles") or []:
        story.append(Paragraph("• " + esc(r), body))
    story += [Paragraph("Стек (заявлен кандидатом)", h2), Paragraph(esc(", ".join(cand.get("stack_declared") or []) or "—"), body),
              Paragraph("Софт-скиллы", h2), Paragraph(esc(", ".join(cand.get("soft_skills") or []) or "—"), body), Spacer(1, 10),
              Paragraph("Блок «Подтверждено платформой» сформирован автоматически по результатам тестирования и данным ФСП. Остальные поля заполнены кандидатом.", small)]
    doc.build(story)
    return buf.getvalue()
