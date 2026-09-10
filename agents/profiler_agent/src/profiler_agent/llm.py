"""LLM call wrapper: one structured-output call per turn (state.py::AgentState)."""

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from profiler_agent.config import Config
from profiler_agent.state import BuildingBlockCategory, Phase

# Models where Google has removed custom sampling controls entirely - they always use fixed
# internal sampling defaults and warn (via langchain-google-genai) if `temperature` is passed.
# Mirrors langchain_google_genai's own (private, version-specific) allowlist; kept here as a
# plain set since that name isn't part of its public API and updated model-by-model as Google
# extends the list ("...and all future Gemini model releases" per Google's docs).
_FIXED_SAMPLING_MODELS = frozenset({"gemini-3.5-flash-lite", "gemini-3.6-flash"})


class VariantOut(BaseModel):
    angle: str = Field(description="Free-text focal angle, e.g. 'business_impact'.")
    content: str = Field(description="One resume bullet written from that angle.")


class CreatedBlockOut(BaseModel):
    category: BuildingBlockCategory
    title: str
    content: str
    variants: list[VariantOut] = Field(default_factory=list)


class UpdatedBlockOut(BaseModel):
    id: str
    category: BuildingBlockCategory
    title: str
    content: str
    variants: list[VariantOut] = Field(default_factory=list)


class GenerateOutput(BaseModel):
    """Structured shape the LLM must return for every turn."""

    reply: str
    phase: Phase
    summary: str
    building_blocks_created: list[CreatedBlockOut] = Field(default_factory=list)
    building_blocks_updated: list[UpdatedBlockOut] = Field(default_factory=list)
    # Only meaningful for the `projects`/`summary_and_confirm` draft-then-confirm phases: an
    # explicit, structured echo of "this turn's `reply` just presented a fresh, not-yet-
    # confirmed bullet draft" - mirrors the exact 3 variants shown in `reply`, empty on every
    # other turn (including the confirming turn itself, once they land in
    # `building_blocks_created` instead). Lets graph.py mechanically detect a pending,
    # unconfirmed draft without parsing `reply`'s prose - see graph.py's phase-advance guard.
    drafted_variants: list[VariantOut] = Field(default_factory=list)


def get_structured_llm():
    """Builds the chat model bound to the `GenerateOutput` schema.

    Returns:
        Runnable: A LangChain runnable whose `.invoke(messages)` returns
        `{"raw": AIMessage, "parsed": GenerateOutput | None, "parsing_error": Exception | None}`.
        `include_raw=True` is deliberate: it exposes `raw.response_metadata`
        so callers can tell a normal completion apart from one cut short
        (`finish_reason != "STOP"`), and it turns a schema-parse failure into
        `parsed=None` instead of a raised exception, so the caller can log the
        raw output before deciding how to fail.

    Raises:
        ValueError: If `Config.GOOGLE_API_KEY` is not set.
    """
    if not Config.GOOGLE_API_KEY:
        raise ValueError(
            "GOOGLE_API_KEY is not set - a Google AI Studio API key is required to call Gemini."
        )
    model_kwargs: dict = {
        "model": Config.MODEL_NAME,
        "google_api_key": Config.GOOGLE_API_KEY,
        # Gemini 3+ models reason by default even on trivial prompts (~30s observed for a
        # two-word reply), which blew past the API's 60s request timeout on real interview
        # turns. This structured-output call needs a fast, deterministic reply, not chain-of-
        # thought, so reasoning depth is pinned to its lowest level ("minimal" is Gemini 3+'s
        # floor - there is no full off-switch; `thinking_budget=0` disables it on 2.5 models
        # instead but is deprecated for 3+).
        "thinking_level": "minimal",
    }
    if Config.MODEL_NAME not in _FIXED_SAMPLING_MODELS:
        model_kwargs["temperature"] = Config.MODEL_TEMPERATURE
    model = ChatGoogleGenerativeAI(**model_kwargs)
    return model.with_structured_output(GenerateOutput, include_raw=True)
