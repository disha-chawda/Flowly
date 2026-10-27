from sqlalchemy import create_engine, inspect
from app.config import settings
from sqlalchemy.orm import DeclarativeBase, sessionmaker

#database.py will import that settings object.
engine = create_engine(settings.DATABASE_URL)

class Base(DeclarativeBase):
    pass # because we are not adding anything to our base class yet

SessionLocal = sessionmaker(bind = engine)


def get_db():
    db = SessionLocal()  # This actually creates the database session.
    try:
        yield db         # Here is the database session. You can use it.
    finally:
        db.close()

def create_all():
    Base.metadata.create_all(bind = engine)

def check_schema(engine) -> None:
    # create_all() never adds columns to an existing table, so an old flowly.db
    # would otherwise fail later on individual requests. Fail at startup instead.
    inspector = inspect(engine)
    if "commitments" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("commitments")}
        if "import_key" not in columns:
            raise RuntimeError(
                "The commitments table in the database at "
                f"{engine.url.render_as_string(hide_password=True)} has no 'import_key' column. "
                "Stop the server, delete flowly.db (this erases its data), and start again. "
                "See README 'Calendar import'.")