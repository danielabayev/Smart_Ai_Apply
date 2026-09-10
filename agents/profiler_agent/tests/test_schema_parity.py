"""Guards `state.py` TypedDicts and `llm.py` Pydantic models against drift.

The two modules define parallel shapes for the same data: TypedDicts in
`state.py` for the LangGraph state / `/reply` wire contract, and Pydantic
models in `llm.py` for the LLM structured-output schema (Pydantic is needed
there for `with_structured_output` and the `Field(description=...)` prompts -
see `llm.py`'s module docstring). Because they can't just be one class, this
test fails loudly if a field is added to one side without the other.
"""

from typing import get_type_hints

from profiler_agent import llm, state


def _typeddict_fields(td: type) -> set[str]:
    return set(get_type_hints(td))


def _model_fields(model: type) -> set[str]:
    return set(model.model_fields)


def test_variant_shape_matches() -> None:
    assert _typeddict_fields(state.VariantDict) == _model_fields(llm.VariantOut)


def test_created_block_shape_matches() -> None:
    assert _typeddict_fields(state.CreatedBlockDict) == _model_fields(llm.CreatedBlockOut)


def test_updated_block_shape_matches() -> None:
    assert _typeddict_fields(state.UpdatedBlockDict) == _model_fields(llm.UpdatedBlockOut)


def test_generate_output_fields_exist_on_agent_state() -> None:
    generate_fields = _model_fields(llm.GenerateOutput)
    agent_state_fields = _typeddict_fields(state.AgentState)
    missing = generate_fields - agent_state_fields
    assert not missing, f"GenerateOutput fields missing from AgentState: {missing}"
