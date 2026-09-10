"""The LangGraph state machine: load_state -> (one node per interview phase).

Matches the graph shape decided in `agent-structure-en.md` section 5. `profiling`
conversations route to a dedicated node per phase (intro/background/skills/education/
projects/summary_and_confirm), each running its own narrow, phase-specific prompt -
see `prompts.py`'s module docstring. `refinement`/`application_edit` conversations
(narrow, single-purpose, phase-less) route to a single shared node instead.

Routing is entirely driven by data already in the state - conversation_type and the
agent's own previous `phase` output - never by graph.py deciding that a topic is
"done"; that judgment call always belongs to the node's own LLM call and prompt.

The one exception is the loop breaker in `_run_llm_turn`: if a phase makes zero progress
(phase unchanged AND no building blocks created/updated) for `_MAX_STUCK_TURNS` turns in a
row, code forces the next phase regardless of what the LLM decided. This still never
decides *when a topic is done* under normal circumstances - it only ever fires as a last
resort against a genuine stuck loop, after several turns of measurable non-progress.
"""

import json
import sqlite3
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from profiler_agent.config import Config
from profiler_agent.llm import GenerateOutput, get_structured_llm
from profiler_agent.logging_utils import (
    ANGLE_SYNTHESIS,
    DB_PAYLOAD_PREP,
    FACT_EXTRACTION,
    GENERATION_TRUNCATED,
    INPUT_PROCESSING,
    PHASE_ADVANCE_WITH_PENDING_DRAFT_CLAMPED,
    PHASE_FORCE_ADVANCE,
    PHASE_OUTPUT_CLAMPED,
    log_event,
)
from profiler_agent.prompts import (
    BACKGROUND_SYSTEM_PROMPT,
    EDUCATION_SYSTEM_PROMPT,
    INTRO_SYSTEM_PROMPT,
    PROJECTS_SYSTEM_PROMPT,
    SKILLS_SYSTEM_PROMPT,
    SUMMARY_CONFIRM_SYSTEM_PROMPT,
    system_prompt_for,
)
from profiler_agent.state import AgentState

_conn = sqlite3.connect(Config.CHECKPOINT_DB_PATH, check_same_thread=False)
# WAL lets readers/writers overlap instead of blocking each other outright; busy_timeout makes
# a writer that still collides retry for up to 5s instead of failing immediately with
# "database is locked" - both needed once multiple threads hit this connection concurrently
# (SqliteSaver's own internal lock only serializes checkpoint ops, not raw SQLite access).
_conn.execute("PRAGMA journal_mode=WAL")
_conn.execute("PRAGMA busy_timeout=5000")
checkpointer = SqliteSaver(_conn)

# Fixed fallback order the loop breaker advances through - only used when a phase is
# genuinely stuck (see _run_llm_turn). Not a code-enforced interview order otherwise.
_PHASE_SEQUENCE = ["intro", "background", "skills", "education", "projects", "summary_and_confirm"]
_MAX_STUCK_TURNS = 5

_PHASE_TO_NODE = {
    "background": "background_node",
    "skills": "skills_node",
    "education": "education_node",
    "projects": "projects_node",
    "summary_and_confirm": "summary_confirm_node",
}

# Mirrors each node's own "valid_phases" list in prompts.py - a structural check that the
# LLM's outgoing `phase` is actually one this node is allowed to produce, catching e.g. a
# `projects_node` call hallucinating `phase: "intro"` (observed bug) despite the prompt
# explicitly restricting it. Purely a validity check on an already-made output, not a
# decision about when a topic is "done" - an invalid value is clamped to "stay put"
# (the incoming phase), never redirected to some other guessed phase.
_LEGAL_OUTGOING_PHASES = {
    "intro_node": {"background"},
    "background_node": {"background", "skills", "projects"},
    "skills_node": {"skills", "education"},
    "education_node": {"education", "projects"},
    "projects_node": {"projects", "summary_and_confirm"},
    "summary_confirm_node": {"summary_and_confirm"},
}


def _next_phase(phase: str) -> str:
    """Fixed fallback order used only by the loop breaker (see module docstring)."""
    try:
        idx = _PHASE_SEQUENCE.index(phase)
    except ValueError:
        return "background"
    return _PHASE_SEQUENCE[min(idx + 1, len(_PHASE_SEQUENCE) - 1)]


def _log(
    state: AgentState,
    level: str,
    event_category: str,
    details: dict[str, Any],
    message_id: int | None = None,
) -> None:
    """Shared `log_event` call shape for every node below - `session_id`/`user_id` always come
    from `state`, and `role_id` is always None (no active-role concept yet, see
    logging_utils.py). `message_id` defaults to `state["message_id"]`; the override is only
    needed in `load_state_node`, where it's computed locally before being written back into state.
    """
    log_event(
        level=level,
        session_id=state.get("conversation_id"),
        user_id=state.get("user_id"),
        message_id=message_id if message_id is not None else state.get("message_id"),
        role_id=None,
        event_category=event_category,
        details=details,
    )


def load_state_node(state: AgentState) -> dict:
    """Phase 1 (Context Retrieval): ensure defaults exist, trace the incoming turn."""
    had_checkpoint = bool(state.get("phase"))
    phase = state.get("phase") or "intro"
    summary = state.get("summary") or ""
    phase_streak = state.get("phase_streak") or 0
    message_id = len(state.get("message_history") or []) + 1

    details = {
        "conversation_type": state.get("conversation_type"),
        "checkpoint_found": had_checkpoint,
        "user_message": state.get("user_message"),
    }
    _log(state, "DEBUG", INPUT_PROCESSING, details, message_id=message_id)
    return {
        "phase": phase,
        "summary": summary,
        "phase_streak": phase_streak,
        "message_id": message_id,
    }


def route_turn(state: AgentState) -> str:
    """Picks which node's prompt applies to this turn.

    Only decides *which* prompt fits (from conversation_type and the agent's own last
    `phase` output) - never *whether* a phase/achievement is "done"; that judgment call
    always belongs to the chosen node's own LLM call.
    """
    if state["conversation_type"] != "profiling":
        return "other_node"
    if state["user_message"] == "":
        return "intro_node"
    # "intro" here means a stale/lost checkpoint (or an unrecognized value) rather than a
    # genuine mid-kickoff turn - the kickoff itself is only ever reached via the empty
    # user_message check above. "background" is the safe re-entry point in that case.
    return _PHASE_TO_NODE.get(state.get("phase") or "intro", "background_node")


def _run_llm_turn(state: AgentState, system_prompt: str, node_name: str) -> dict:
    """Shared LLM-call + trace-logging body for every node (agent-structure-en.md section 5)."""
    llm = get_structured_llm()

    turn_payload = {
        "summary": state.get("summary", ""),
        "phase": state.get("phase", "intro"),
        "user_message": state["user_message"],
        "context": state.get("context") or {},
        # Always included, not just when `summary` is empty (first turn / lost checkpoint):
        # `summary` is a lossy, model-written paraphrase, never a verbatim record - a phase
        # like `projects`/`summary_and_confirm` that must reuse its OWN previous turn's exact
        # drafted wording (per those phases' prompts) has no way to do that from `summary`
        # alone. Observed bug: the model would re-draft fresh bullet variants instead of
        # reusing the ones it had just shown, because the exact prior wording had already
        # been lost - it never made it into `summary`, and this field wasn't sent to recover
        # it. Sending the real message history every turn removes that gap.
        "message_history": state.get("message_history"),
    }
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(turn_payload, ensure_ascii=False, default=str)),
    ]

    llm_call = llm.invoke(messages)
    raw_message = llm_call["raw"]
    result: GenerateOutput | None = llm_call["parsed"]
    response_meta = raw_message.response_metadata or {}
    # `finish_reason` is Gemini's own account of why generation stopped - "STOP" is a normal
    # completion, anything else (e.g. "MAX_TOKENS") means the model was cut off mid-output
    # before it finished the JSON, which is a direct, verifiable cause for a truncated
    # building_blocks_created array (as opposed to the model choosing to close it early) -
    # see the skills-phase omission bug investigation (2026-09-07).
    finish_reason = response_meta.get("finish_reason")
    usage = getattr(raw_message, "usage_metadata", None) or {}
    output_tokens = usage.get("output_tokens")
    input_tokens = usage.get("input_tokens")

    if result is None:
        details = {
            "error": "LLM output failed to parse into GenerateOutput",
            "parsing_error": str(llm_call.get("parsing_error")),
            "finish_reason": finish_reason,
            "output_tokens": output_tokens,
            "input_tokens": input_tokens,
            "raw_content": raw_message.content,
        }
        _log(state, "ERROR", "ERROR", details)
        raise RuntimeError(
            f"{node_name}: LLM output failed to parse into GenerateOutput "
            f"(finish_reason={finish_reason!r}): {llm_call.get('parsing_error')!r}"
        )

    if finish_reason is not None and finish_reason != "STOP":
        details = {
            "node": node_name,
            "finish_reason": finish_reason,
            "output_tokens": output_tokens,
            "input_tokens": input_tokens,
        }
        _log(state, "WARNING", GENERATION_TRUNCATED, details)

    details = {
        "raw_user_message": state["user_message"],
        "reply": result.reply,
        "phase": result.phase,
        "summary": result.summary,
        "finish_reason": finish_reason,
        "output_tokens": output_tokens,
        "input_tokens": input_tokens,
    }
    _log(state, "DEBUG", FACT_EXTRACTION, details)
    created = [b.model_dump() for b in result.building_blocks_created]
    updated = [b.model_dump() for b in result.building_blocks_updated]

    if created or updated:
        details = {
            "building_blocks_created": created,
            "building_blocks_updated": updated,
        }
        _log(state, "DEBUG", ANGLE_SYNTHESIS, details)

    details = {
        "building_blocks_created_count": len(created),
        "building_blocks_updated_count": len(updated),
    }
    _log(state, "DEBUG", DB_PAYLOAD_PREP, details)

    incoming_phase = state.get("phase", "intro")
    outgoing_phase = result.phase

    legal_phases = _LEGAL_OUTGOING_PHASES.get(node_name)
    if legal_phases is not None and outgoing_phase not in legal_phases:
        details = {
            "node": node_name,
            "invalid_phase": outgoing_phase,
            "clamped_to": incoming_phase,
            "legal_phases": sorted(legal_phases),
        }
        _log(state, "WARNING", PHASE_OUTPUT_CLAMPED, details)
        outgoing_phase = incoming_phase

    # A draft-then-confirm phase (`projects`/`summary_and_confirm`) must not leave its own
    # phase in the same turn it just presented a fresh, not-yet-confirmed draft - observed bug:
    # projects_node drafted 3 project-bullet variants AND output phase="summary_and_confirm" in
    # the same turn, so the user's next message (meant to confirm that draft) got routed to
    # summary_confirm_node instead, silently orphaning the achievement (0 created, forever).
    # `drafted_variants` is this turn's own structured echo of "reply just presented a draft"
    # (see llm.py/prompts.py) - purely mechanical, never a guess at reply's prose.
    if result.drafted_variants and not created and outgoing_phase != incoming_phase:
        details = {
            "node": node_name,
            "attempted_phase": outgoing_phase,
            "clamped_to": incoming_phase,
            "drafted_variants": [v.model_dump() for v in result.drafted_variants],
        }
        _log(state, "WARNING", PHASE_ADVANCE_WITH_PENDING_DRAFT_CLAMPED, details)
        outgoing_phase = incoming_phase

    # Deliberately phase-change-only, NOT "or created/updated blocks": a stuck node can keep
    # creating (even spurious) blocks turn after turn without ever actually advancing the
    # interview, which would otherwise mask exactly the stuck loop this breaker exists to catch.
    made_progress = outgoing_phase != incoming_phase
    streak = 0 if made_progress else state.get("phase_streak", 0) + 1

    if streak >= _MAX_STUCK_TURNS:
        forced_phase = _next_phase(incoming_phase)
        details = {
            "stuck_phase": incoming_phase,
            "forced_next_phase": forced_phase,
            "consecutive_no_progress_turns": streak,
        }
        _log(state, "WARNING", PHASE_FORCE_ADVANCE, details)
        outgoing_phase = forced_phase
        streak = 0

    return {
        "reply": result.reply,
        "phase": outgoing_phase,
        "phase_streak": streak,
        "summary": result.summary,
        "building_blocks_created": created,
        "building_blocks_updated": updated,
    }


def intro_node(state: AgentState) -> dict:
    """`intro` phase: the one-time conversation kickoff."""
    return _run_llm_turn(state, INTRO_SYSTEM_PROMPT, node_name="intro_node")


def background_node(state: AgentState) -> dict:
    """`background` phase: role/company overview -> `about_user` block."""
    return _run_llm_turn(state, BACKGROUND_SYSTEM_PROMPT, node_name="background_node")


def skills_node(state: AgentState) -> dict:
    """`skills` phase: technical skills -> `technical_skills` blocks."""
    return _run_llm_turn(state, SKILLS_SYSTEM_PROMPT, node_name="skills_node")


def education_node(state: AgentState) -> dict:
    """`education` phase: degrees/certifications -> `education` blocks."""
    return _run_llm_turn(state, EDUCATION_SYSTEM_PROMPT, node_name="education_node")


def projects_node(state: AgentState) -> dict:
    """`projects` phase: STAR-driven achievement mining -> `project` blocks."""
    return _run_llm_turn(state, PROJECTS_SYSTEM_PROMPT, node_name="projects_node")


def summary_confirm_node(state: AgentState) -> dict:
    """`summary_and_confirm` phase: final synthesis -> `role` block."""
    return _run_llm_turn(state, SUMMARY_CONFIRM_SYSTEM_PROMPT, node_name="summary_confirm_node")


def other_node(state: AgentState) -> dict:
    """`refinement`/`application_edit`: narrow, single-purpose, phase-less conversations."""
    return _run_llm_turn(
        state, system_prompt_for(state["conversation_type"]), node_name="other_node"
    )


def build_graph():
    """Compiles the load_state -> (phase/type-routed node) graph."""
    graph = StateGraph(AgentState)
    graph.add_node("load_state", load_state_node)
    graph.add_node("intro_node", intro_node)
    graph.add_node("background_node", background_node)
    graph.add_node("skills_node", skills_node)
    graph.add_node("education_node", education_node)
    graph.add_node("projects_node", projects_node)
    graph.add_node("summary_confirm_node", summary_confirm_node)
    graph.add_node("other_node", other_node)

    graph.set_entry_point("load_state")
    graph.add_conditional_edges("load_state", route_turn)
    for node_name in (
        "intro_node",
        "background_node",
        "skills_node",
        "education_node",
        "projects_node",
        "summary_confirm_node",
        "other_node",
    ):
        graph.add_edge(node_name, END)

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
