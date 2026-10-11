"""Схемы запросов (Pydantic v2). Из них же строится OpenAPI."""
import re
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from .taxonomy import ALL_STACK, GRADES, MAX_SURVEY_STACK, SPECS, WORK_FORMATS

# Адрес электронной почты (без внешней зависимости email-validator)
EmailStr = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=254,
                                            pattern=r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")]
Spec = Literal[tuple(SPECS)]  # noqa: F821 — список специализаций берётся из taxonomy.SPECS
Grade = Literal["trainee", "junior", "middle", "senior"]


class Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")


def _tags(v, limit=12):
    if v is None or v == "":
        return []
    if isinstance(v, str):
        v = [x for x in v.split(",")]
    out = []
    for x in v:
        x = str(x).strip().lower()
        if x and x not in out:
            out.append(x)
    return out[:limit]


class Salary(Base):
    """Диапазон заработной платы в рублях — обязателен для вакансии и приглашения."""
    salary_from: int = Field(ge=1_000, le=10_000_000, description="Зарплата «от», руб.")
    salary_to: int = Field(ge=1_000, le=10_000_000, description="Зарплата «до», руб.")

    @model_validator(mode="after")
    def _order(self):
        if self.salary_to < self.salary_from:
            raise ValueError("«до» не может быть меньше «от»")
        return self


# ----------------------------------------------------------------------------- auth
class RegisterIn(Base):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128, description="Не короче 8 символов, буквы и цифры")
    role: Literal["candidate", "employer"]
    consent_pd: bool = Field(description="Согласие на обработку персональных данных (152-ФЗ) — обязательно")
    full_name: str = Field(default="", max_length=120)
    company_name: str = Field(default="", max_length=160)

    @field_validator("password")
    @classmethod
    def _pw(cls, v):
        if not (any(c.isalpha() for c in v) and any(c.isdigit() for c in v)):
            raise ValueError("пароль должен содержать буквы и цифры")
        return v

    @field_validator("consent_pd")
    @classmethod
    def _consent(cls, v):
        if not v:
            raise ValueError("без согласия на обработку персональных данных регистрация невозможна")
        return v

    @model_validator(mode="after")
    def _company(self):
        if self.role == "employer" and not self.company_name:
            raise ValueError("для работодателя укажите название компании")
        return self


class LoginIn(Base):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ConfirmIn(Base):
    token: str = Field(min_length=10, max_length=100)


# ----------------------------------------------------------------------------- кандидат
class ProfileIn(Base):
    full_name: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=32)
    city: str = Field(default="", max_length=80)
    headline: str = Field(default="", max_length=160)
    about: str = Field(default="", max_length=3000)
    experience_years: float = Field(default=0, ge=0, le=50)
    roles: list[str] = Field(default_factory=list, max_length=8)
    soft_skills: list[str] = Field(default_factory=list, max_length=10)
    stack_declared: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("stack_declared", mode="before")
    @classmethod
    def _stack(cls, v):
        return _tags(v, 40)


class SurveyIn(Base):
    industry: str = Field(max_length=80)
    spec: Spec
    stack: list[str] = Field(default_factory=list, max_length=MAX_SURVEY_STACK)
    grade: Grade
    format: Literal["office", "remote", "hybrid"] = "remote"

    @field_validator("stack", mode="before")
    @classmethod
    def _stack(cls, v):
        return [t for t in _tags(v, MAX_SURVEY_STACK) if t in ALL_STACK][:MAX_SURVEY_STACK]


class TestStartIn(Base):
    __test__ = False  # не тестовый класс для pytest
    spec: Spec
    grade: Grade
    expert: bool = Field(default=False, description="Экспертный тест (платная услуга): задания уровня 5 по специализации вашей категории")
    consent_proctoring: bool = Field(default=False, description="Согласие на прокторинг: журнал событий браузера и снимки с веб-камеры")
    camera_ready: bool = Field(default=False, description="Камера включена и работает")


class ProctorEvent(Base):
    kind: str = Field(max_length=30)
    meta: dict[str, Any] = Field(default_factory=dict)


class ProctorIn(Base):
    cid: str = Field(min_length=6, max_length=40, description="Идентификатор вкладки (случайный, создаётся в браузере)")
    events: list[ProctorEvent] = Field(default_factory=list, max_length=80)
    snapshot: Optional[str] = Field(default=None, max_length=120_000, description="JPEG data URL со снимком веб-камеры")
    camera: bool = True


class ModerationIn(Base):
    decision: Literal["clear", "annul"]
    comment: str = Field(default="", max_length=1000)


class TestFinishIn(Base):
    __test__ = False
    answers: dict[str, Any] = Field(default_factory=dict, description="{id задания: индекс варианта | число}")
    blur_count: int = Field(default=0, ge=0, le=1000, description="Сколько раз кандидат покидал вкладку (отправляет клиент)")
    times: dict[str, float] = Field(default_factory=dict, description="{id задания: секунд, проведённых на задании}")


class PrivacyIn(Base):
    show_stack: bool = True
    show_fsp: bool = True
    show_experience: bool = True
    show_city: bool = False
    show_personal: bool = Field(default=False, description="Показывать работодателям личные сведения из резюме (возраст, гражданство, семейное положение и т.п.)")
    visible_in_bank: bool = True


class SettingsIn(Base):
    consent_publish: bool = Field(description="Согласие на публикацию профиля в банке кандидатов (виден работодателям)")
    privacy: PrivacyIn = Field(default_factory=PrivacyIn)


class FspLinkIn(Base):
    fsp_id: str = Field(min_length=4, max_length=40, description="Идентификатор участника ФСП, например FSP-100001")


class DecisionIn(Base):
    decision: Literal["accept", "decline"]


class ApplyIn(Base):
    message: str = Field(default="", max_length=1500)


class InviteStageIn(Base):
    stage: Literal["considering", "interview", "test_task", "offer", "hired", "rejected"]
    note: str = Field(default="", max_length=500, description="Короткий комментарий, который увидит кандидат")
    vacancy_id: Optional[int] = Field(default=None, description="Вакансия, на которую принят кандидат (для этапа hired, если приглашение не было привязано к вакансии)")


class MicrotaskAnswerIn(Base):
    answer: str = Field(min_length=3, max_length=5000)


# ----------------------------------------------------------------------------- работодатель
class CompanyIn(Base):
    company_name: str = Field(min_length=2, max_length=160)
    industry: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=3000)
    website: str = Field(default="", max_length=200)
    contact_name: str = Field(default="", max_length=120)
    contact_method: str = Field(default="", max_length=200, description="Как с вами связаться кандидату: e-mail, Telegram, телефон")


class NeedIn(Base):
    title: str = Field(min_length=3, max_length=160, description="Кто нужен, например «Backend-разработчик в платёжную команду»")
    spec: Spec
    grade: Grade
    stack: list[str] = Field(default_factory=list, max_length=12)
    team_desc: str = Field(default="", max_length=2000, description="Чем занимается команда")
    work_format: Literal["office", "remote", "hybrid", ""] = ""

    @field_validator("stack", mode="before")
    @classmethod
    def _stack(cls, v):
        return _tags(v)


class SearchQuery(Base):
    need_id: Optional[int] = None
    spec: Optional[Spec] = None
    grade: Optional[str] = Field(default=None, description="Один грейд или список через запятую")
    stack: Optional[str] = Field(default=None, description="Технологии через запятую (кандидат должен иметь ВСЕ среди подтверждённых)")
    has_fsp: Optional[bool] = None
    expert_only: Optional[bool] = Field(default=None, description="Только прошедшие Expert-тест (платная услуга «Поиск среди Expert»)")
    min_score: Optional[int] = Field(default=None, ge=0, le=100, description="Минимальный результат теста, %")
    city: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("grade")
    @classmethod
    def _grades(cls, v):
        if v:
            for g in v.split(","):
                if g.strip() not in GRADES:
                    raise ValueError(f"неизвестный грейд: {g}")
        return v


class InviteIn(Salary):
    candidate_code: str = Field(min_length=3, max_length=20, description="Код кандидата из выдачи, например C-7F3A9B")
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=10, max_length=3000)
    contact_method: str = Field(min_length=3, max_length=200, description="Способ связи, который увидит кандидат")
    vacancy_id: Optional[int] = None
    need_id: Optional[int] = None


class VacancyIn(Salary):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=5000)
    spec: Spec
    grade: Grade
    stack: list[str] = Field(default_factory=list, max_length=12)
    work_format: Literal["office", "remote", "hybrid", ""] = ""
    city: str = Field(default="", max_length=80)
    employment: Literal["full", "part", "project", "internship", ""] = ""
    requirements: str = Field(default="", max_length=4000)
    conditions: str = Field(default="", max_length=4000)

    @field_validator("stack", mode="before")
    @classmethod
    def _stack(cls, v):
        return _tags(v)


class VacancyStatusIn(Base):
    status: Literal["published", "closed"]


class ApplicationStatusIn(Base):
    status: Literal["hired", "rejected", "viewed", "invited_to_talk", "call_passed"]


class MicrotaskIn(Base):
    title: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=10, max_length=4000)
    spec: Spec
    grade: Grade
    kind: Literal["solve", "approach"] = "approach"
    fsp_ids: list[str] = Field(default_factory=list, max_length=50, description="FSP ID кандидатов, которым адресовано задание. Пусто — задание получают кандидаты категории")

    @field_validator("fsp_ids", mode="before")
    @classmethod
    def _fsp_ids(cls, v):
        if isinstance(v, str):
            v = re.split(r"[\s,;]+", v)
        out = []
        for x in v or []:
            x = str(x).strip().upper()
            if x and x not in out:
                if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{2,30}", x):
                    raise ValueError(f"Некорректный FSP ID: {x}")
                out.append(x)
        return out


class RateIn(Base):
    rating: int = Field(ge=1, le=5)
    feedback: str = Field(default="", max_length=1000)


class VacancyListQuery(Base):
    spec: Optional[Spec] = None
    grade: Optional[Grade] = None
    limit: int = Field(default=30, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class DeleteAccountIn(Base):
    password: str = Field(min_length=1, max_length=128, description="Подтверждение паролем")


class ResendIn(Base):
    email: EmailStr


# ----------------------------------------------------------------------------- резюме, аккаунт, услуги, тренировка
class ExperienceItem(Base):
    company: str = Field(default="", max_length=120)
    position: str = Field(default="", max_length=120)
    start: str = Field(default="", max_length=7, description="ГГГГ-ММ")
    end: str = Field(default="", max_length=7, description="ГГГГ-ММ; пусто — по настоящее время")
    description: str = Field(default="", max_length=2000)


class ProjectItem(Base):
    name: str = Field(default="", max_length=120)
    role: str = Field(default="", max_length=120)
    link: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=2000)
    stack: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("stack", mode="before")
    @classmethod
    def _stack(cls, v):
        return _tags(v)


class EducationItem(Base):
    institution: str = Field(default="", max_length=160)
    level: Literal["", "secondary", "college", "bachelor", "specialist", "master", "phd", "courses"] = ""
    degree: str = Field(default="", max_length=80)
    specialty: str = Field(default="", max_length=160)
    year_from: str = Field(default="", max_length=4)
    year_to: str = Field(default="", max_length=4)


class CertificateItem(Base):
    kind: Literal["certificate", "diploma", "award"] = "certificate"
    name: str = Field(default="", max_length=160)
    issuer: str = Field(default="", max_length=160)
    year: str = Field(default="", max_length=4)
    link: str = Field(default="", max_length=300)


class LanguageItem(Base):
    name: str = Field(default="", max_length=40)
    level: Literal["", "A1", "A2", "B1", "B2", "C1", "C2", "native"] = ""


class PersonalIn(Base):
    """Личные сведения — необязательны; работодатель видит их только если кандидат включил «показывать личные сведения»."""
    birth_year: Optional[int] = Field(default=None, ge=1940, le=2015)
    citizenship: str = Field(default="", max_length=60)
    marital_status: Literal["", "single", "married", "divorced", "widowed"] = ""
    children: Literal["", "none", "one", "two", "three_plus"] = ""
    military: Literal["", "served", "reserve", "exempt", "not_liable", "student"] = ""
    driving: str = Field(default="", max_length=30, description="Категории водительских прав, например «B»")


class LinksIn(Base):
    github: str = Field(default="", max_length=200)
    telegram: str = Field(default="", max_length=100)
    linkedin: str = Field(default="", max_length=200)
    site: str = Field(default="", max_length=200)


class ResumeIn(Base):
    summary: str = Field(default="", max_length=2000, description="Коротко о себе и желаемой роли")
    desired_position: str = Field(default="", max_length=120)
    salary_expectation: Optional[int] = Field(default=None, ge=1_000, le=10_000_000, description="Желаемая зарплата, ₽ на руки или до вычета — по вашему выбору")
    employment_types: list[Literal["full", "part", "project", "internship"]] = Field(default_factory=list, max_length=4)
    schedules: list[Literal["office", "remote", "hybrid", "shift"]] = Field(default_factory=list, max_length=4)
    relocation: Literal["", "no", "yes", "maybe"] = ""
    business_trips: Literal["", "no", "yes", "rarely"] = ""
    languages: list[LanguageItem] = Field(default_factory=list, max_length=8)
    links: LinksIn = Field(default_factory=LinksIn)
    personal: PersonalIn = Field(default_factory=PersonalIn)
    experience: list[ExperienceItem] = Field(default_factory=list, max_length=20)
    projects: list[ProjectItem] = Field(default_factory=list, max_length=20)
    education: list[EducationItem] = Field(default_factory=list, max_length=10)
    certificates: list[CertificateItem] = Field(default_factory=list, max_length=30)


class AvatarIn(Base):
    image: str = Field(max_length=60_000, description="Фото или логотип: data URL jpeg/png/webp, до ~40 КБ (браузер уменьшает до 256 px)")

    @field_validator("image")
    @classmethod
    def _img(cls, v):
        if not v.startswith(("data:image/jpeg;base64,", "data:image/png;base64,", "data:image/webp;base64,")):
            raise ValueError("допустимы jpeg, png или webp")
        return v


class TopupIn(Base):
    amount: int = Field(ge=100, le=100_000, description="Сумма пополнения, ₽")


class BuyIn(Base):
    service: str = Field(max_length=40)
    vacancy_id: Optional[int] = None


class SupportIn(Base):
    subject: str = Field(min_length=3, max_length=160)
    message: str = Field(min_length=10, max_length=4000)


class SupportReplyIn(Base):
    reply: str = Field(min_length=2, max_length=4000)


class PracticeNextIn(Base):
    spec: Spec
    level: int = Field(ge=1, le=5)


class PracticeAnswerIn(Base):
    answer: Any = None
