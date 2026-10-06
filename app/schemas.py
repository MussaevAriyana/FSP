"""Схемы запросов (Pydantic v2). Из них же строится OpenAPI."""
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from .taxonomy import ALL_STACK, GRADES, SPECS, WORK_FORMATS

# Адрес электронной почты (без внешней зависимости email-validator)
EmailStr = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=254,
                                            pattern=r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")]
Spec = Literal["backend", "frontend", "data", "devops", "qa"]
Grade = Literal["trainee", "junior", "middle", "senior"]


class Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")


def _tags(v):
    if v is None or v == "":
        return []
    if isinstance(v, str):
        v = [x for x in v.split(",")]
    out = []
    for x in v:
        x = str(x).strip().lower()
        if x and x not in out:
            out.append(x)
    return out[:12]


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
    stack_declared: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("stack_declared", mode="before")
    @classmethod
    def _stack(cls, v):
        return _tags(v)


class SurveyIn(Base):
    industry: str = Field(max_length=80)
    spec: Spec
    stack: list[str] = Field(default_factory=list, max_length=8)
    grade: Grade
    format: Literal["office", "remote", "hybrid"] = "remote"

    @field_validator("stack", mode="before")
    @classmethod
    def _stack(cls, v):
        return [t for t in _tags(v) if t in ALL_STACK][:8]


class TestStartIn(Base):
    __test__ = False  # не тестовый класс для pytest
    spec: Spec
    grade: Grade


class TestFinishIn(Base):
    __test__ = False
    answers: dict[str, Any] = Field(default_factory=dict, description="{id задания: индекс варианта | число}")
    blur_count: int = Field(default=0, ge=0, le=1000, description="Сколько раз кандидат покидал вкладку (отправляет клиент)")


class PrivacyIn(Base):
    show_stack: bool = True
    show_fsp: bool = True
    show_experience: bool = True
    show_city: bool = False
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

    @field_validator("stack", mode="before")
    @classmethod
    def _stack(cls, v):
        return _tags(v)


class VacancyStatusIn(Base):
    status: Literal["published", "closed"]


class ApplicationStatusIn(Base):
    status: Literal["viewed", "invited_to_talk", "rejected"]


class MicrotaskIn(Base):
    title: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=10, max_length=4000)
    spec: Spec
    grade: Grade
    kind: Literal["solve", "approach"] = "approach"


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
