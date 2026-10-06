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
}

# Порядок важен: индекс = уровень сложности заданий (1..4)
GRADES = {
    "trainee": {"title": "Стажёр", "hint": "без коммерческого опыта", "level": 1},
    "junior":  {"title": "Junior", "hint": "опыт до 1 года", "level": 2},
    "middle":  {"title": "Middle", "hint": "опыт 1–3 года", "level": 3},
    "senior":  {"title": "Senior", "hint": "опыт от 3 лет", "level": 4},
}
GRADE_ORDER = list(GRADES)

# Смежные специализации (для мягкого учёта при подборе)
RELATED_SPECS = {"backend": {"devops": 0.35, "data": 0.3}, "frontend": {"backend": 0.25},
                 "data": {"backend": 0.3}, "devops": {"backend": 0.35, "qa": 0.2}, "qa": {"backend": 0.2, "frontend": 0.2}}

STACK = {
    "backend":  ["python", "java", "go", "csharp", "nodejs", "php", "sql", "postgresql", "redis", "kafka", "docker", "rest", "git"],
    "frontend": ["javascript", "typescript", "react", "vue", "angular", "html", "css", "rest", "git"],
    "data":     ["python", "sql", "pandas", "ml", "statistics", "spark", "git"],
    "devops":   ["linux", "bash", "docker", "kubernetes", "ci_cd", "terraform", "networks", "git"],
    "qa":       ["manual", "selenium", "pytest", "api_testing", "sql", "ci_cd", "git"],
}
ALL_STACK = sorted({t for tags in STACK.values() for t in tags})

# Какие технологии подтверждает хорошее решение задач по теме
TOPIC_STACK = {
    "python": ["python"], "sql": ["sql", "postgresql"], "javascript": ["javascript", "typescript"],
    "css": ["css", "html"], "linux": ["linux", "bash"], "networks": ["networks"],
    "statistics": ["statistics", "pandas"], "ml": ["ml"], "devops": ["docker", "ci_cd", "kubernetes"],
    "web": ["rest"], "qa_theory": ["manual", "api_testing"], "backend_arch": ["redis", "kafka"],
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
    {"id": "stack", "title": "С какими технологиями вы работаете? (до 8)", "type": "multi", "options": "by_spec"},
    {"id": "grade", "title": "Какой грейд вы считаете своим?", "type": "single",
     "options": [{"value": k, "label": f'{v["title"]} — {v["hint"]}'} for k, v in GRADES.items()]},
    {"id": "format", "title": "Предпочтительный формат работы", "type": "single",
     "options": [{"value": k, "label": v} for k, v in WORK_FORMATS.items()]},
]


def taxonomy_payload() -> dict:
    return {"specs": SPECS, "grades": GRADES, "stack": STACK, "industries": INDUSTRIES,
            "work_formats": WORK_FORMATS, "soft_skills": SOFT_SKILLS, "survey": SURVEY}


def category_label(spec: str | None, grade: str | None) -> str:
    if not spec or not grade:
        return "Категория не присвоена"
    return f'{SPECS[spec]["short"]} · {GRADES[grade]["title"]}'
