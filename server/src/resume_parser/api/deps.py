from typing import Generator

from fastapi import Request
from openai import OpenAI
from sqlalchemy.orm import Session

from ..llm.claude import ClaudeAdapter


def get_session(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_adapter(request: Request) -> ClaudeAdapter:
    return request.app.state.adapter


def get_openai(request: Request) -> OpenAI:
    return request.app.state.openai_client
