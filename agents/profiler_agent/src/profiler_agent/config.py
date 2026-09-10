"""Configuration for the profiler-agent microservice, loaded from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Runtime configuration for the profiler-agent Flask app.

    Attributes:
        PORT (int): TCP port the HTTP server listens on.
        MODEL_NAME (str): Google Generative AI (Gemini) model name used for
            interview/generation calls.
        MODEL_TEMPERATURE (float): Sampling temperature for the structured-output LLM call.
        GOOGLE_API_KEY (str): Google AI Studio API key used to authenticate
            with the Gemini API.
        CHECKPOINT_DB_PATH (str): Path to the private SQLite checkpoint store
            used for LangGraph's per-conversation state. Never the shared
            platform Postgres DB.
    """

    PORT = int(os.environ.get("PROFILER_AGENT_PORT", "8001"))
    MODEL_NAME = os.environ.get("PROFILER_AGENT_MODEL", "gemini-3.6-flash")
    MODEL_TEMPERATURE = float(os.environ.get("PROFILER_AGENT_MODEL_TEMPERATURE", "0.4"))
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
    CHECKPOINT_DB_PATH = os.environ.get(
        "PROFILER_AGENT_CHECKPOINT_DB", "profiler_agent_state.sqlite3"
    )
