"""Configuration for the profiler-agent microservice, loaded from environment variables."""

import os


class Config:
    """Runtime configuration for the profiler-agent Flask app.

    Attributes:
        PORT (int): TCP port the HTTP server listens on.
        MODEL_NAME (str): Local Ollama model tag used for interview/generation calls.
        MODEL_TEMPERATURE (float): Sampling temperature for the structured-output LLM call.
        OLLAMA_BASE_URL (str): Base URL of the local Ollama server.
        CHECKPOINT_DB_PATH (str): Path to the private SQLite checkpoint store
            used for LangGraph's per-conversation state. Never the shared
            platform Postgres DB.
    """

    PORT = int(os.environ.get("PROFILER_AGENT_PORT", "8001"))
    MODEL_NAME = os.environ.get("PROFILER_AGENT_MODEL", "llama3.1:8b")
    MODEL_TEMPERATURE = float(os.environ.get("PROFILER_AGENT_MODEL_TEMPERATURE", "0.4"))
    OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    CHECKPOINT_DB_PATH = os.environ.get(
        "PROFILER_AGENT_CHECKPOINT_DB", "profiler_agent_state.sqlite3"
    )
