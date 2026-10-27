from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.domain.enums import Priority
from app.domain.enums import Category
from app.domain.enums import Completion
from app.domain.enums import Source
from app.data.database import Base
from datetime import datetime, timezone

def _utc_now() -> datetime:
    # Naive UTC, so it compares cleanly with the other naive datetimes in the app.
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Task(Base):
    __tablename__ = "tasks"
    title: Mapped[str] = mapped_column()
    estimated_time: Mapped[int | None] = mapped_column(nullable = True)

    # This column uniquely identifies each row
    id: Mapped[int] = mapped_column(primary_key = True)
    description: Mapped[str] = mapped_column(default = "")
    deadline: Mapped[datetime| None] = mapped_column(nullable = True)
    priority: Mapped[Priority] = mapped_column(default = Priority.MEDIUM)
    category: Mapped[Category] = mapped_column(default = Category.PERSONAL)
    completion: Mapped[Completion] = mapped_column(default = Completion.INCOMPLETE)
    created_at: Mapped[datetime] = mapped_column(default = _utc_now)
    source: Mapped[Source] = mapped_column(default = Source.MANUAL)

class Commitment(Base):
    __tablename__ = "commitments"
    id: Mapped[int] = mapped_column(primary_key = True)
    title: Mapped[str] = mapped_column()
    start_time: Mapped[datetime] = mapped_column()
    end_time: Mapped[datetime] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default = _utc_now)
    source: Mapped[Source] = mapped_column(default = Source.MANUAL)
    # Set only on calendar-imported rows so a re-import can find them; NULL for
    # manual rows. Unique among non-null values (SQL UNIQUE allows many NULLs).
    import_key: Mapped[str | None] = mapped_column(nullable = True, unique = True, default = None)