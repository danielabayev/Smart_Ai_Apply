"""LLM call wrapper: one structured-output call per turn (state.py::AgentState)."""

from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

from profiler_agent.config import Config
from profiler_agent.state import BuildingBlockCategory, Phase


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


def get_structured_llm():
    """Builds the chat model bound to the `GenerateOutput` schema.

    Returns:
        Runnable: A LangChain runnable whose `.invoke(messages)` returns a
        `GenerateOutput` instance.
    """
    model = ChatOllama(
        model=Config.MODEL_NAME,
        base_url=Config.OLLAMA_BASE_URL,
        temperature=Config.MODEL_TEMPERATURE,
    )
    return model.with_structured_output(GenerateOutput)
