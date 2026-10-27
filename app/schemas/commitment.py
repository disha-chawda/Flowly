from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.domain.enums import Source

TITLE_MAX = 200


def _validate_title(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("title must not be empty or whitespace-only")
    if len(trimmed) > TITLE_MAX:
        raise ValueError(f"title must be at most {TITLE_MAX} characters")
    return trimmed


class CommitmentCreate(BaseModel):
    title: str
    start_time: datetime
    end_time: datetime
    source: Source = Source.MANUAL

    @field_validator("title")
    @classmethod
    def _check_title(cls, value: str) -> str:
        return _validate_title(value)

    @model_validator(mode="after")
    def _check_times(self) -> "CommitmentCreate":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be strictly later than start_time")
        return self


class CommitmentUpdate(BaseModel):
    title: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None

    @field_validator("title", "start_time", "end_time")
    @classmethod
    def _reject_null(cls, value):
        # Omitting a field is allowed; sending an explicit null is not.
        if value is None:
            raise ValueError("must not be null")
        return value

    @field_validator("title")
    @classmethod
    def _check_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_title(value)

    @model_validator(mode="after")
    def _check_times(self) -> "CommitmentUpdate":
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError("end_time must be strictly later than start_time")
        return self


class CommitmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    start_time: datetime
    end_time: datetime
    created_at: datetime
    source: Source
