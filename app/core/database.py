from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

# Create engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,    # Check connection health before using
    pool_size=5,           # Keep 5 connections ready
    max_overflow=10        # Allow up to 10 extra connections
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for all models
class Base(DeclarativeBase):
    pass


def get_db():
    """
    FastAPI dependency — yields a DB session.
    Closes session after request completes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables if they don't exist."""
    from app.models import db_models  # noqa
    Base.metadata.create_all(bind=engine)