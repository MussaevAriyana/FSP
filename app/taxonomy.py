"""Справочники: специализации, грейды, стек, отрасли, вопросы опроса.

Справочник составлен по общепринятым в ИТ понятиям; для MVP — основные направления.
Категория кандидата = связка (специализация, грейд), например «backend / middle».
"""

SPECS = {
    "backend":  {"title": "Backend-разработка", "short": "Backend"},
    "frontend": {"title": "Frontend-разработка", "short": "Frontend"},
    "data":     {"title": "Data Science и аналитика данных", "short": "Data"},
    "devops":   {"title": "DevOps / SRE", "short": "DevOps"},
    "qa":       {"title": "Тестирование (QA)", "short": "QA"},
    "fullstack": {"title": "Fullstack-разработка", "short": "Fullstack"},
    "mobile":   {"title": "Мобильная разработка (iOS / Android)", "short": "Mobile"},
    "ml":       {"title": "Машинное обучение и ИИ", "short": "ML / AI"},
    "security": {"title": "Информационная безопасность", "short": "Security"},
    "analyst":  {"title": "Системная и бизнес-аналитика", "short": "Аналитика"},
    "embedded": {"title": "Embedded, робототехника и системное ПО", "short": "Embedded"},
    "gamedev":  {"title": "Разработка игр и графики", "short": "GameDev"},
}

# Составные специализации: набор заданий и технологий собирается из базовых (+ собственные технологии каталога)
SPEC_BASES = {"fullstack": ("backend", "frontend"), "mobile": ("frontend", "backend"), "ml": ("data", "backend"),
              "security": ("devops", "backend", "qa"), "analyst": ("data", "qa"), "embedded": ("backend", "devops"),
              "gamedev": ("backend", "frontend")}

# Порядок важен. level — «ядровой» уровень сложности заданий теста на этот грейд (шкала 1–5)
GRADES = {
    "trainee": {"title": "Стажёр", "hint": "без коммерческого опыта", "level": 2},
    "junior":  {"title": "Junior", "hint": "опыт до 1 года", "level": 3},
    "middle":  {"title": "Middle", "hint": "опыт 1–3 года", "level": 4},
    "senior":  {"title": "Senior", "hint": "опыт от 3 лет", "level": 5},
}
GRADE_ORDER = list(GRADES)

# Смежные специализации (для мягкого учёта при подборе)
RELATED_SPECS = {"backend": {"devops": 0.35, "data": 0.3, "fullstack": 0.6, "embedded": 0.25, "security": 0.25, "gamedev": 0.25, "ml": 0.25},
                 "frontend": {"backend": 0.25, "fullstack": 0.6, "mobile": 0.35, "gamedev": 0.2},
                 "data": {"backend": 0.3, "ml": 0.6, "analyst": 0.35}, "devops": {"backend": 0.35, "qa": 0.2, "security": 0.35, "embedded": 0.2},
                 "qa": {"backend": 0.2, "frontend": 0.2, "analyst": 0.3, "security": 0.2},
                 "fullstack": {"backend": 0.6, "frontend": 0.6, "mobile": 0.3}, "mobile": {"frontend": 0.35, "fullstack": 0.3, "gamedev": 0.2},
                 "ml": {"data": 0.6, "backend": 0.25}, "security": {"devops": 0.35, "backend": 0.25, "qa": 0.2}, "analyst": {"data": 0.35, "qa": 0.3},
                 "embedded": {"backend": 0.25, "devops": 0.2}, "gamedev": {"backend": 0.25, "frontend": 0.2, "mobile": 0.2}}

# Каталог технологий (~160 позиций, см. techcatalog.py). STACK[spec] — технологии, типичные для специализации.
from .techcatalog import CATALOG, GROUPS, TECH_IDS  # noqa: E402

STACK = {spec: [t["id"] for t in CATALOG if spec in t["specs"] or any(b in t["specs"] for b in SPEC_BASES.get(spec, ()))] for spec in SPECS}
ALL_STACK = list(TECH_IDS)
MAX_SURVEY_STACK = 25

# Какие технологии подтверждает хорошее решение задач по теме
TOPIC_STACK = {
    "python": ["python"], "sql": ["sql", "postgresql", "mysql", "sqlite"], "javascript": ["javascript", "typescript", "nodejs"],
    "css": ["css", "html", "sass"], "linux": ["linux", "bash"], "os": ["linux"], "networks": ["networks", "nginx"],
    "statistics": ["statistics", "ab_testing", "pandas", "numpy"], "ml": ["ml", "scikit_learn"],
    "devops": ["docker", "ci_cd", "kubernetes", "terraform", "ansible"], "web": ["rest", "openapi", "websockets"],
    "qa_theory": ["manual", "api_testing", "load_testing"],
    "backend_arch": ["microservices", "redis", "kafka", "rabbitmq", "design_patterns", "clean_architecture"],
    "algorithms": ["algorithms"],
}

INDUSTRIES = ["Финтех и банки", "Электронная коммерция", "Телеком", "Государственные сервисы (GovTech)",
              "Игры и медиа", "Образование (EdTech)", "Промышленность и логистика", "Медицина (HealthTech)", "Другое"]
WORK_FORMATS = {"office": "Офис", "remote": "Удалённо", "hybrid": "Гибрид"}
SOFT_SKILLS = ["Коммуникация", "Работа в команде", "Ответственность", "Самообучаемость", "Лидерство",
               "Ориентация на результат", "Критическое мышление", "Наставничество"]

SURVEY = [
    {"id": "industry", "title": "В какой отрасли вам интереснее работать?", "type": "single", "options": INDUSTRIES},
    {"id": "spec", "title": "Ваша специализация", "type": "single",
     "options": [{"value": k, "label": v["title"]} for k, v in SPECS.items()]},
    {"id": "stack", "title": "С какими технологиями вы работаете? (до 25)", "type": "multi", "options": "by_spec"},
    {"id": "grade", "title": "Какой грейд вы считаете своим?", "type": "single",
     "options": [{"value": k, "label": f'{v["title"]} — {v["hint"]}'} for k, v in GRADES.items()]},
    {"id": "format", "title": "Предпочтительный формат работы", "type": "single",
     "options": [{"value": k, "label": v} for k, v in WORK_FORMATS.items()]},
]


def taxonomy_payload() -> dict:
    return {"specs": SPECS, "grades": GRADES, "stack": STACK, "tech": CATALOG, "tech_groups": GROUPS, "max_stack": MAX_SURVEY_STACK, "industries": INDUSTRIES,
            "work_formats": WORK_FORMATS, "soft_skills": SOFT_SKILLS, "survey": SURVEY}


def category_label(spec: str | None, grade: str | None) -> str:
    if not spec or not grade:
        return "Категория не присвоена"
    return f'{SPECS[spec]["short"]} · {GRADES[grade]["title"]}'
