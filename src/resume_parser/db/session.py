import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def make_engine():
    return create_engine(os.environ["DATABASE_URL"], pool_size=5, max_overflow=10)


def make_session_factory(engine):
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)
