"""Conversation endpoints (api-structure-en.md section 1.3)."""

import logging
import re
import time
import uuid
from typing import Any

from flask import Blueprint, abort, jsonify, request

from api.agent_client import get_agent_reply
from api.current_user import get_current_user
from api.extensions import db
from api.job_scan_cursor import reset_job_scan_cursor
from api.models import Application, BuildingBlock, Company, Conversation, Job, Message, User

logger = logging.getLogger(__name__)

conversations_bp = Blueprint("conversations", __name__)


def _get_conversation_or_404(conversation_id: str) -> Conversation:
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        abort(404, description="Conversation not found")
    conversation = db.session.get(Conversation, conv_uuid)
    if conversation is None:
        abort(404, description="Conversation not found")
    return conversation


def _build_context(conversation: Conversation, user: User) -> dict[str, Any]:
    """Pre-loads everything Agent 1 could need for this turn (wire contract section 3)."""
    context: dict[str, Any] = {
        "existing_building_blocks": None,
        "target_building_block": None,
        "job": None,
    }

    if conversation.type == "profiling":
        blocks = BuildingBlock.query.filter_by(user_id=user.id).all()
        context["existing_building_blocks"] = [b.to_dict() for b in blocks]
        return context

    # 'refinement' and 'application_edit' both reference the block being reworded/replaced.
    if conversation.building_block_id is not None:
        block = db.session.get(BuildingBlock, conversation.building_block_id)
        if block is None:
            abort(500, description="Conversation references a missing building_block_id")
        context["target_building_block"] = block.to_dict()

    if conversation.type == "application_edit":
        if conversation.application_id is None:
            abort(500, description="'application_edit' conversation missing application_id")
        application = db.session.get(Application, conversation.application_id)
        if application is None:
            abort(500, description="Conversation references a missing application_id")
        job = db.session.get(Job, application.job_id)
        if job is None:
            abort(500, description="Application references a missing job_id")
        job_dict = job.to_dict()
        job_dict.pop("discovered_at", None)
        job_dict.pop("updated_at", None)
        company = db.session.get(Company, job.company_id)
        job_dict["company"] = (
            {"id": company.id, "name": company.name, "website": company.website} if company else None
        )
        context["job"] = job_dict

    return context


# Categories that are quantifiable achievement narratives (drafted as 3 bullet-variant
# angles, created only after a separate confirmation turn) vs. simple stated facts (recorded
# immediately, never carry variants). Mirrors profiler_agent's prompts.py phase split.
_ACHIEVEMENT_CATEGORIES = {"project", "role"}
_SIMPLE_FACT_CATEGORIES = {"technical_skills", "education", "about_user"}
# Of the simple-fact categories, only these two are meant to be grounded in a single turn's
# `user_message` (agent-structure-en.md: "record exactly what they said [this turn]") -
# `about_user` is a deliberately paraphrased, multi-turn summary, so it's exempt.
_SINGLE_TURN_GROUNDED_CATEGORIES = {"technical_skills", "education"}
_REQUIRED_VARIANT_COUNT = 3

# A trailing "." must NOT be swallowed into the token (sentence-ending punctuation, e.g.
# "...and PostgreSQL." would otherwise tokenize as "postgresql." and fail to match the bare
# "postgresql" token from `content`, silently dropping a correctly-extracted skill - observed
# bug). An internal "." stays part of the token (e.g. "Node.js", "ASP.NET") by requiring an
# alnum run on both sides of it.
_TOKEN_RE = re.compile(r"[A-Za-z0-9+#]+(?:\.[A-Za-z0-9+#]+)*")
def _normalize_for_dedup(text: str) -> str:
    """Collapses whitespace/case so near-identical content compares as equal."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _tokenize(text: str) -> set[str]:
    """Splits into lowercase word-ish tokens, keeping tech tokens like 'C++'/'C#' intact."""
    return {t.lower() for t in _TOKEN_RE.findall(text)}


def _content_grounded_in_message(content: str, user_message: str) -> bool:
    """Guards against a fabricated fact (e.g. a skill/degree the user never actually said).

    Requires at least one token of `content` to appear, as a whole token, somewhere in this
    turn's `user_message`. Whole-token comparison (not substring) deliberately avoids a short
    token like "C" falsely "matching" inside an unrelated word like "ARM Cortex-M" - the two
    tokenize to disjoint sets ({"c"} vs {"arm", "cortex", "m"}), while genuine restatements
    (even reworded ones, e.g. "Oscilloscope use" for "oscilloscope") still share a token.
    """
    content_tokens = _tokenize(content)
    if not content_tokens:
        return True
    return bool(content_tokens & _tokenize(user_message))


def _variants_copied_from_another_block(
    category: str, variants: list[dict[str, Any]], known_blocks: list[BuildingBlock]
) -> bool:
    """Guards against cross-contamination: reusing another block's variants verbatim instead
    of drafting this achievement's own (observed bug - a `role` block copying its `variants`
    wholesale from an unrelated, already-existing `project` block).
    """
    if not variants:
        return False
    variant_contents = {_normalize_for_dedup(v.get("content", "")) for v in variants}
    for block in known_blocks:
        if block.category == category:
            continue
        other_contents = {_normalize_for_dedup(v.get("content", "")) for v in (block.variants or [])}
        if variant_contents and variant_contents == other_contents:
            return True
    return False


def _ngrams(text: str, n: int = 3) -> set[str]:
    """Extracts lowercase n-word phrases, for detecting shared distinctive wording."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def _is_duplicate_block(category: str, content: str, known_blocks: list[BuildingBlock]) -> bool:
    """Guards against Agent 1 re-emitting an already-known fact/achievement as a new row.

    `about_user` is meant to be a single evolving summary (agent-structure-en.md section 5) -
    any existing one already covers it, regardless of content. Other categories are deduped by
    near-identical content within the same category: an exact match, or one containing the
    other, catches both literal repeats and minor rewordings (e.g. "ARM Cortex-M" vs
    "ARM Cortex-M7").

    For achievement categories specifically (`project`/`role`), also flags a shared 3-word
    phrase with an existing block of the same category as a likely duplicate - observed bug:
    `profiling` has no "update" path, so once the user adds more detail to an
    already-confirmed achievement (e.g. the final numbers), the agent sometimes creates a
    SECOND block worded differently enough to dodge the containment check above, rather than
    recognizing it's the same achievement. A shared specific multi-word phrase (e.g. "batch
    reconciliation job") is a strong, unlikely-to-be-coincidental signal of that.
    """
    same_category = [b for b in known_blocks if b.category == category]
    if category == "about_user":
        return bool(same_category)
    normalized_new = _normalize_for_dedup(content)
    # Containment alone is only meaningful once both strings have enough characters that a
    # match can't just be a short token (e.g. a bare "C") coincidentally appearing inside an
    # unrelated word (e.g. "ARM Cortex-M", "I2C") - below this length, require an exact match.
    _MIN_LEN_FOR_CONTAINMENT_MATCH = 4
    new_ngrams = _ngrams(content) if category in _ACHIEVEMENT_CATEGORIES else set()
    for block in same_category:
        normalized_existing = _normalize_for_dedup(block.content)
        if normalized_new and normalized_existing:
            if normalized_new == normalized_existing:
                return True
            if (
                len(normalized_new) >= _MIN_LEN_FOR_CONTAINMENT_MATCH
                and len(normalized_existing) >= _MIN_LEN_FOR_CONTAINMENT_MATCH
                and (normalized_new in normalized_existing or normalized_existing in normalized_new)
            ):
                return True
        if new_ngrams and (new_ngrams & _ngrams(block.content)):
            return True
    return False


def _persist_building_block_changes(
    conversation: Conversation, user: User, agent_result: dict[str, Any], user_message: str = ""
) -> tuple[list[dict], list[dict]]:
    """Writes Agent 1's created/updated blocks to the DB (the API Server is the sole writer).

    Applies structural guards against several observed Agent 1 failure modes before ever
    writing a row - each guard only ever *rejects or normalizes* a malformed item (never
    invents data to complete one), and only checks things that are mechanically verifiable
    from data already at hand (schema shape, dedup, grounding in this turn's own message) -
    never a judgment call about interview pacing, which stays entirely up to the agent.
    """
    created_dicts: list[dict] = []
    updated_dicts: list[dict] = []
    changed = False

    known_blocks = BuildingBlock.query.filter_by(user_id=user.id).all()

    for item in agent_result.get("building_blocks_created", []):
        category = item["category"]
        title = item.get("title", "") or ""
        content = item.get("content", "") or ""
        variants = item.get("variants", []) or []

        # Empty `content` with a non-empty `title` is a safe auto-repair (reuses data already
        # given, invents nothing) - observed bug: the agent leaves content blank for a skill
        # whose name is only in `title`.
        if not content.strip() and title.strip():
            content = title

        # Simple facts never carry variants, regardless of what the agent sent.
        if category in _SIMPLE_FACT_CATEGORIES:
            variants = []

        if category in _SINGLE_TURN_GROUNDED_CATEGORIES and not _content_grounded_in_message(
            content, user_message
        ):
            logger.warning(
                "Skipping ungrounded building_blocks_created item (category=%s, content=%r) - "
                "not present in this turn's user_message=%r for conversation_id=%s",
                category,
                content,
                user_message,
                conversation.id,
            )
            continue

        if _is_duplicate_block(category, content, known_blocks):
            logger.info(
                "Skipping duplicate building_blocks_created item (category=%s, "
                "conversation_id=%s) - matches an existing block for user_id=%s",
                category,
                conversation.id,
                user.id,
            )
            continue

        if category in _ACHIEVEMENT_CATEGORIES:
            if _variants_copied_from_another_block(category, variants, known_blocks):
                logger.warning(
                    "Rejecting building_blocks_created item (category=%s, conversation_id=%s) - "
                    "its variants are copied verbatim from a different, already-existing block "
                    "instead of being drafted for this one",
                    category,
                    conversation.id,
                )
                variants = []
            if len(variants) != _REQUIRED_VARIANT_COUNT:
                logger.warning(
                    "Skipping building_blocks_created item (category=%s, conversation_id=%s) - "
                    "expected exactly %d variants, got %d",
                    category,
                    conversation.id,
                    _REQUIRED_VARIANT_COUNT,
                    len(variants),
                )
                continue
            distinct_variant_contents = {
                _normalize_for_dedup(v.get("content", "")) for v in variants
            }
            if len(distinct_variant_contents) != _REQUIRED_VARIANT_COUNT:
                logger.warning(
                    "Skipping building_blocks_created item (category=%s, conversation_id=%s) - "
                    "variants aren't actually distinct (only %d unique content string(s) among "
                    "%d variants)",
                    category,
                    conversation.id,
                    len(distinct_variant_contents),
                    len(variants),
                )
                continue
        block = BuildingBlock(
            user_id=user.id,
            conversation_id=conversation.id,
            category=category,
            title=title,
            content=content,
            variants=variants,
        )
        db.session.add(block)
        db.session.flush()
        created_dicts.append(block.to_dict())
        known_blocks.append(block)
        changed = True

    building_blocks_updated = agent_result.get("building_blocks_updated", [])
    if building_blocks_updated and conversation.type == "profiling":
        # Wire contract (agent-structure-en.md section 3): `profiling` only ever creates.
        # Agent 1 occasionally emits an unchanged block here anyway - discard rather than
        # apply, since honoring it would violate the "profiling never updates" invariant.
        logger.warning(
            "Agent 1 returned building_blocks_updated on a profiling conversation_id=%s "
            "(should never happen - discarding without persisting): %r",
            conversation.id,
            building_blocks_updated,
        )
        building_blocks_updated = []

    for item in building_blocks_updated:
        try:
            block_uuid = uuid.UUID(item["id"])
        except (KeyError, ValueError):
            logger.error("Agent 1 returned an invalid building_block id: %r", item.get("id"))
            abort(500, description="Agent returned an invalid building_block id")
        if conversation.building_block_id is not None and block_uuid != conversation.building_block_id:
            logger.error(
                "Agent 1 building_blocks_updated id=%s does not match conversation.building_block_id=%s",
                block_uuid,
                conversation.building_block_id,
            )
            abort(500, description="Agent returned a mismatched building_block id")
        block = db.session.get(BuildingBlock, block_uuid)
        if block is None:
            abort(500, description="Agent referenced a missing building_block id")
        block.category = item["category"]
        block.title = item["title"]
        block.content = item["content"]
        block.variants = item.get("variants", [])
        updated_dicts.append(block.to_dict())
        changed = True

    if changed:
        reset_job_scan_cursor(user.id)

    return created_dicts, updated_dicts


# Phrases claiming something was just persisted (e.g. "I've recorded that", "that's been
# saved", "got it, noted") - matched against `reply` to guard against a hallucinated
# confirmation: the agent claims success in words without anything actually being written.
# "created"/"generated" observed missing from the verb list, and "already" missing from the
# modifier list (qwen2.5:14b test, 2026-09-07): "I've created the project building block" and
# "I've already created ..." both claimed persistence but slipped past this guard uncorrected
# even though building_blocks_created was empty both turns - the verb list didn't cover
# "created", and the modifier slot only accepted a single "now"/"been", not "already" or any
# combination of common adverbs between the subject and the verb.
_FALSE_CONFIRMATION_RE = re.compile(
    r"\b(i'?ve|i have|it'?s|it has|that'?s|that has|this is|has been)\s+"
    r"(?:(?:now|already|just|successfully|finally|been)\s+){0,2}"
    r"(recorded|saved|logged|noted|added|stored|created|generated)\b",
    re.IGNORECASE,
)


def reply_falsely_claims_persistence(
    reply: str, created: list[dict[str, Any]], updated: list[dict[str, Any]]
) -> bool:
    """True if `reply` claims something was just saved but nothing was actually persisted.

    Checked against the FINAL `created`/`updated` lists (after every other guard above has
    already run) - so this also catches the case where the agent attempted to save something
    that a different guard correctly rejected, and still told the user it was saved.
    """
    return bool(_FALSE_CONFIRMATION_RE.search(reply)) and not created and not updated


def _correct_false_confirmation(
    reply: str, created: list[dict[str, Any]], updated: list[dict[str, Any]], conversation_id: Any
) -> str:
    """Appends a corrective note when `reply` falsely claims something was saved.

    Deliberately appends rather than rewriting/stripping text from the agent's own reply -
    editing natural language via regex risks producing a garbled sentence; appending a plain,
    separate clarification is safe regardless of the original phrasing.
    """
    if not reply_falsely_claims_persistence(reply, created, updated):
        return reply
    logger.warning(
        "Agent 1 reply claims something was saved but nothing was persisted this turn "
        "(conversation_id=%s): %r",
        conversation_id,
        reply,
    )
    return reply + " (Note: nothing new was actually saved from that - let's go over it again.)"


def _format_agent_result_for_logging(agent_result: dict[str, Any], max_value_len: int = 300) -> str:
    """Formats agent_result as one 'key: value' line per field, truncating long values."""
    lines = []
    for key, value in agent_result.items():
        text = repr(value)
        if len(text) > max_value_len:
            text = f"{text[:max_value_len]}... (truncated, {len(text)} chars total)"
        lines.append(f"{key}: {text}")
    return "\n".join(lines)


def _send_kickoff_message(conversation: Conversation, user: User) -> None:
    """Auto-triggers Agent 1's self-introduction for a fresh `profiling` conversation.

    Calls Agent 1 with an empty `user_message` and no history - the system-triggered
    kickoff signal (agent-structure-en.md section 5, `intro` phase) - so the agent
    introduces itself and explains the interview flow before the user types anything.
    """
    context = _build_context(conversation, user)
    started_at = time.monotonic()
    agent_result = get_agent_reply(
        conversation_id=str(conversation.id),
        conversation_type=conversation.type,
        message_history=[],
        user_message="",
        user_id=str(user.id),
        building_block_id=None,
        application_id=None,
        context=context,
    )
    response_time_ms = int((time.monotonic() - started_at) * 1000)

    if agent_result.get("building_blocks_created") or agent_result.get("building_blocks_updated"):
        logger.warning(
            "Agent 1 returned building block changes on the kickoff turn for conversation_id=%s "
            "(no history/user_message was sent, so this is unexpected - likely a hallucination or "
            "bug; discarding these changes without persisting them). Agent response:\n%s",
            conversation.id,
            _format_agent_result_for_logging(agent_result),
        )
        created, updated = [], []
    else:
        created, updated = _persist_building_block_changes(conversation, user, agent_result)

    reply = _correct_false_confirmation(agent_result["reply"], created, updated, conversation.id)

    agent_message = Message(
        conversation_id=conversation.id,
        sender="agent",
        content=reply,
        response_time_ms=response_time_ms,
    )
    db.session.add(agent_message)
    db.session.commit()
    logger.info("Sent kickoff message for conversation_id=%s", conversation.id)


@conversations_bp.post("/conversations")
def create_conversation():
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    conv_type = body.get("type", "profiling")

    conversation = Conversation(
        user_id=user.id,
        type=conv_type,
        building_block_id=body.get("building_block_id"),
        application_id=body.get("application_id"),
    )
    db.session.add(conversation)
    db.session.commit()
    logger.info("Created conversation id=%s type=%s user_id=%s", conversation.id, conv_type, user.id)

    if conv_type == "profiling":
        _send_kickoff_message(conversation, user)

    return jsonify(conversation.to_dict(include_messages=True)), 201


@conversations_bp.get("/conversations")
def list_conversations():
    user = get_current_user()
    conversations = (
        Conversation.query.filter_by(user_id=user.id).order_by(Conversation.created_at.desc()).all()
    )
    return jsonify([c.to_dict() for c in conversations])


@conversations_bp.get("/conversations/<conversation_id>")
def get_conversation(conversation_id: str):
    conversation = _get_conversation_or_404(conversation_id)
    return jsonify(conversation.to_dict(include_messages=True, include_building_blocks=True))


@conversations_bp.post("/conversations/<conversation_id>/messages")
def post_message(conversation_id: str):
    conversation = _get_conversation_or_404(conversation_id)
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    content = body.get("content")
    if not content:
        abort(400, description="'content' is required")

    user_message = Message(conversation_id=conversation.id, sender="user", content=content)
    db.session.add(user_message)
    db.session.commit()

    history = [msg.to_dict() for msg in conversation.messages]
    context = _build_context(conversation, user)

    started_at = time.monotonic()
    agent_result = get_agent_reply(
        conversation_id=str(conversation.id),
        conversation_type=conversation.type,
        message_history=history,
        user_message=content,
        user_id=str(user.id),
        building_block_id=str(conversation.building_block_id) if conversation.building_block_id else None,
        application_id=str(conversation.application_id) if conversation.application_id else None,
        context=context,
    )
    response_time_ms = int((time.monotonic() - started_at) * 1000)

    created, updated = _persist_building_block_changes(conversation, user, agent_result, content)
    reply = _correct_false_confirmation(agent_result["reply"], created, updated, conversation.id)

    agent_message = Message(
        conversation_id=conversation.id,
        sender="agent",
        content=reply,
        response_time_ms=response_time_ms,
    )
    db.session.add(agent_message)
    db.session.commit()

    logger.info("Processed message in conversation_id=%s", conversation.id)

    return jsonify(
        {
            "agent_reply": reply,
            "building_blocks_created": created,
            "building_blocks_updated": updated,
        }
    )


@conversations_bp.post("/conversations/<conversation_id>/finish")
def finish_conversation(conversation_id: str):
    conversation = _get_conversation_or_404(conversation_id)
    conversation.status = "finished"
    db.session.commit()
    logger.info("Finished conversation_id=%s", conversation.id)
    return jsonify(conversation.to_dict())
