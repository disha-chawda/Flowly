from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import Priority, Category, Completion, Source

TITLE_MAX = 200
DESCRIPTION_MAX = 2000


def _validate_title(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("title must not be empty or whitespace-only")
    if len(trimmed) > TITLE_MAX:
        raise ValueError(f"title must be at most {TITLE_MAX} characters")
    return trimmed


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    deadline: datetime | None = None
    estimated_time: int | None = Field(default=None, gt=0)
    priority: Priority = Priority.MEDIUM
    category: Category = Category.PERSONAL
    completion: Completion = Completion.INCOMPLETE
    source: Source = Source.MANUAL

    @field_validator("title")
    @classmethod
    def _check_title(cls, value: str) -> str:
        return _validate_title(value)

    @field_validator("source")
    @classmethod
    def _manual_only(cls, value: Source) -> Source:
        # Only the calendar import may create ics_import rows (Design §8).
        if value is not Source.MANUAL:
            raise ValueError("source must be 'manual'")
        return value


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    deadline: datetime | None = None
    estimated_time: int | None = Field(default=None, gt=0)
    priority: Priority | None = None
    category: Category | None = None
    completion: Completion | None = None

    @field_validator("title")
    @classmethod
    def _check_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_title(value)


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    deadline: datetime | None
    estimated_time: int | None
    priority: Priority
    category: Category
    completion: Completion
    created_at: datetime
    source: Source
