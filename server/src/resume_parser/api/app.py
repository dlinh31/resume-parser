import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI

from ..db.session import make_engine, make_session_factory
from ..llm.claude import ClaudeAdapter
from .routes import jobs, resumes


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    engine = make_engine()
    app.state.SessionLocal = make_session_factory(engine)
    app.state.adapter = ClaudeAdapter()
    app.state.openai_client = OpenAI()
    app.state.engine = engine
    yield
    engine.dispose()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(resumes.router)
app.include_router(jobs.router)
