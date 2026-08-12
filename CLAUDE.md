# CLAUDE.md

## Overview
This project is an automated job-application platform built in Python. It uses a **LangGraph** multi-agent architecture to interview users, collect and update their facts, generate tailored resumes, and automatically apply for relevant job openings. The system is deployed and orchestrated on **Kubernetes (k8s)**.

## Tech Stack
- **Language:** Python 3.11+
- **Agentic Framework:** LangGraph / LangChain
- **Package Manager:** `uv`
- **Orchestration & Deployment:** Kubernetes (k8s), Docker

## Development & Environment Setup

### Package Management (`uv`)
- **Install Dependencies:** `uv sync`
- **Add Package:** `uv add <package_name>`
- **Run Scripts / Commands:** `uv run python <script_name>.py`

### Project Commands
*(Commands will be populated as test suites and operational scripts are implemented)*
- **Run Main Application:** `uv run python -m src.main`
- **Run Tests:** `uv run pytest` (Planned)

## Architecture Overview
The system is built on a multi-agent workflow powered by **LangGraph**:
1. **User Interview Agent:** Interacts with the user to gather career history, updates user facts, and refines profile details.
2. **Job Search & Scraper Agent:** Scans target company job boards and identifies relevant roles.
3. **Resume Customization Agent:** Generates tailored, role-specific resumes based on the candidate's profile and target job descriptions.
4. **Application / Submission Agent:** Handles job submission workflows.
5. **Infrastructure:** Microservices containerized with Docker and orchestrated via Kubernetes (`Deployment`, `Job`, `Secret`, `ConfigMap`).

## Coding Conventions & Guidelines

### Language Policy
- **Code, Comments, Docstrings, and Logs:** **MUST BE IN ENGLISH ONLY.**

### Type Hints & Typing
- Strict type hinting is required for all function arguments, return types, and class attributes.
- Use standard `typing` modules (`Optional`, `List`, `Dict`, `Union`, `Tuple`, etc.) or Python 3.10+ native pipe syntax (`str | None`).
```python
def generate_resume(user_id: str, job_description: str) -> Dict[str, Any]:


Logging Standards
All modules must use Python's standard logging library or a structured logging library configured with standard severity levels.

Always include contextual details in log messages.

Log Levels Mapping:

DEBUG: Detailed information, useful during development/diagnostics (e.g., raw API responses, intermediate state changes).

INFO: General operational entries confirming normal functionality (e.g., agent task started, interview session initialized).

WARNING (Important): Non-critical anomalies or recoverable issues (e.g., job portal rate limit reached, retrying request).

ERROR (Error): Errors that prevent a specific task from completing, but keep the process running.

CRITICAL (Critical): Severe failures requiring immediate intervention (e.g., database disconnect, service unavailability).

Documentation & Docstrings
Every public module, class, and function must include a clear docstring in Google Style or Sphinx Style.

Specify argument types, descriptions, return values, and raised exceptions.

def interview_user(session_id: str, prompt: str) -> str:
    """Interviews the user to gather context and updates facts.

    Args:
        session_id (str): The unique identifier for the current session.
        prompt (str): The input prompt or response from the user.

    Returns:
        str: The agent's next follow-up question or response.

    Raises:
        ValueError: If session_id is invalid or missing.
    """