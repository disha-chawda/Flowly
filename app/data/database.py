from sqlalchemy import create_engine
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