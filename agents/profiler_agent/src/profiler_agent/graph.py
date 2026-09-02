"""The LangGraph state machine: load_state -> generate.

Matches the graph shape decided in `agent-structure-en.md` section 5. Kept
thin on purpose - a single LLM call per turn does all the interview
judgment (what to ask, when enough detail exists, when to emit variants);
`phase` is a self-reported tracking label, never a code-enforced sequence.
"""

import json
import sqlite3

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from profiler_agent.config import Config
from profiler_agent.llm import GenerateOutput, get_structured_llm
from profiler_agent.logging_utils import (
    ANGLE_SYNTHESIS,
    DB_PAYLOAD_PREP,
    FACT_EXTRACTION,
    INPUT_PROCESSING,
    log_event,
)
from profiler_agent.prompts import system_prompt_for
from profiler_agent.state import AgentState

_conn = sqlite3.connect(Config.CHECKPOINT_DB_PATH, check_same_thread=False)
# WAL lets readers/writers overlap instead of blocking each other outright; busy_timeout makes
# a writer that still collides retry for up to 5s instead of failing immediately with
# "database is locked" - both needed once multiple threads hit this connection concurrently
# (SqliteSaver's own internal lock only serializes checkpoint ops, not raw SQLite access).
_conn.execute("PRAGMA journal_mode=WAL")
_conn.execute("PRAGMA busy_timeout=5000")
checkpointer = SqliteSaver(_conn)


def load_state_node(state: AgentState) -> dict:
    """Phase 1 (Context Retrieval): ensure defaults exist, trace the incoming turn."""
    had_checkpoint = bool(state.get("phase"))
    phase = state.get("phase") or "intro"
    summary = state.get("summary") or ""
    message_id = len(state.get("message_history") or []) + 1

    log_event(
        level="DEBUG",
        session_id=state.get("conversation_id"),
        user_id=state.get("user_id"),
        message_id=message_id,
        role_id=None,
        event_category=INPUT_PROCESSING,
        details={
            "conversation_type": state.get("conversation_type"),
            "checkpoint_found": had_checkpoint,
            "user_message": state.get("user_message"),
        },
    )
    return {"phase": phase, "summary": summary, "message_id": message_id}


def generate_node(state: AgentState) -> dict:
    """Phases 2 & 3: the single LLM call that drives the interview/edit turn."""
    conversation_type = state["conversation_type"]
    llm = get_structured_llm()

    turn_payload = {
        "summary": state.get("summary", ""),
        "phase": state.get("phase", "intro"),
        "user_message": state["user_message"],
        "context": state.get("context") or {},
        # Resilience fallback only - used by the model when `summary` is empty
        # (first turn, or a lost checkpoint), per agent-structure-en.md section 4.
        "message_history_fallback": (
            state.get("message_history") if not state.get("summary") else None
        ),
    }
    messages = [
        SystemMessage(content=system_prompt_for(conversation_type)),
        HumanMessage(content=json.dumps(turn_payload, ensure_ascii=False, default=str)),
    ]

    result: GenerateOutput = llm.invoke(messages)

    log_event(
        level="DEBUG",
        session_id=state.get("conversation_id"),
        user_id=state.get("user_id"),
        message_id=state.get("message_id"),
        role_id=None,
        event_category=FACT_EXTRACTION,
        details={
            "raw_user_message": state["user_message"],
            "reply": result.reply,
            "phase": result.phase,
            "summary": result.summary,
        },
    )
    created = [b.model_dump() for b in result.building_blocks_created]
    updated = [b.model_dump() for b in result.building_blocks_updated]

    if created or updated:
        log_event(
            level="DEBUG",
            session_id=state.get("conversation_id"),
            user_id=state.get("user_id"),
            message_id=state.get("message_id"),
            role_id=None,
            event_category=ANGLE_SYNTHESIS,
            details={
                "building_blocks_created": created,
                "building_blocks_updated": updated,
            },
        )

    log_event(
        level="DEBUG",
        session_id=state.get("conversation_id"),
        user_id=state.get("user_id"),
        message_id=state.get("message_id"),
        role_id=None,
        event_category=DB_PAYLOAD_PREP,
        details={
            "building_blocks_created_count": len(created),
            "building_blocks_updated_count": len(updated),
        },
    )

    return {
        "reply": result.reply,
        "phase": result.phase,
        "summary": result.summary,
        "building_blocks_created": created,
        "building_blocks_updated": updated,
    }


def build_graph():
    """Compiles the load_state -> generate graph."""
    graph = StateGraph(AgentState)
    graph.add_node("load_state", load_state_node)
    graph.add_node("generate", generate_node)
    graph.set_entry_point("load_state")
    graph.add_edge("load_state", "generate")
    graph.add_edge("generate", END)
    return graph.compile(checkpointer=checkpointer)


_compiled_graph = build_graph()


def run_turn(payload: dict) -> dict:
    """Runs one `/reply` turn end-to-end.

    Args:
        payload (dict): The `/reply` request body, per agent-structure-en.md section 3.
            Always present: 
                `conversation_id`, 
                `conversation_type` (`profiling`,`refinement`, or `application_edit`),
                `user_message`, `message_history`.
            Type-dependent: 
                `building_block_id`, 
                `application_id`, 
                `context` 
            - each still present but set to `null` when not relevant to the given type.

    Returns:
        dict: `{"reply": str, "building_blocks_created": list, "building_blocks_updated": list}`.

    Raises:
        ValueError: If required fields are missing or `conversation_type` is unknown.
    """
    conversation_id = payload.get("conversation_id")
    if not conversation_id:
        raise ValueError("'conversation_id' is required")
    conversation_type = payload.get("conversation_type")
    if conversation_type not in ("profiling", "refinement", "application_edit"):
        raise ValueError(f"Unknown conversation_type: {conversation_type!r}")
    # An empty string is a valid, deliberate value here: it signals a system-triggered
    # conversation kickoff (agent-structure-en.md section 5, `intro` phase) sent before the
    # user has typed anything. Only a missing/None `user_message` is a caller error.
    user_message = payload.get("user_message")
    if user_message is None:
        raise ValueError("'user_message' is required")

    input_state: AgentState = {
        "conversation_id": conversation_id,
        "conversation_type": conversation_type,
        "user_id": payload.get("user_id"),
        "message_history": payload.get("message_history") or [],
        "user_message": user_message,
        "building_block_id": payload.get("building_block_id"),
        "application_id": payload.get("application_id"),
        "context": payload.get("context") or {},
    }
    config = {"configurable": {"thread_id": conversation_id}}
    final_state = _compiled_graph.invoke(input_state, config=config)

    return {
        "reply": final_state["reply"],
        "building_blocks_created": final_state.get("building_blocks_created", []),
        "building_blocks_updated": final_state.get("building_blocks_updated", []),
    }
