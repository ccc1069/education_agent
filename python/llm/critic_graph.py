"""Critic 自反思链的 LangGraph StateGraph。

节点: evaluate -> (条件) regenerate -> END
对外: build_critic_reflection_graph(service).ainvoke(...)
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from llm.critic_service import CritiqueResult, CriticLLMService


class CriticGraphState(TypedDict, total=False):
    knowledge_id: str
    level: str
    mastery: float
    is_correct: bool | None
    question: str
    initial_response: str
    initial_meta: dict[str, Any]
    rag_context: str | None
    critique: CritiqueResult | None
    final_text: str
    final_meta: dict[str, Any]


def build_critic_reflection_graph(service: CriticLLMService):
    """编译 Critic 自反思 StateGraph。"""

    async def evaluate_node(state: CriticGraphState) -> dict[str, Any]:
        critique = await service.evaluate(
            knowledge_id=state["knowledge_id"],
            level=state["level"],
            mastery=state["mastery"],
            is_correct=state.get("is_correct"),
            teaching_response=state["initial_response"],
            learner_message=state.get("question", ""),
        )
        return {"critique": critique}

    async def pass_through(state: CriticGraphState) -> dict[str, Any]:
        critique = state.get("critique")
        initial_meta = dict(state.get("initial_meta") or {})
        if critique is None:
            return {
                "final_text": state["initial_response"],
                "final_meta": initial_meta,
            }
        merged = {
            **initial_meta,
            "critic": {
                "overall": critique.overall,
                "scores": critique.scores,
                "model": critique.model,
                "tokens": critique.tokens,
            },
            "regenerated": False,
            "orchestrator": "langgraph",
        }
        return {
            "final_text": state["initial_response"],
            "final_meta": merged,
        }

    async def regenerate_node(state: CriticGraphState) -> dict[str, Any]:
        critique = state["critique"]
        assert critique is not None
        initial_meta = dict(state.get("initial_meta") or {})
        new_text, regen_meta = await service.regenerate(
            knowledge_id=state["knowledge_id"],
            level=state["level"],
            mastery=state["mastery"],
            is_correct=state.get("is_correct"),
            original_response=state["initial_response"],
            critique=critique.critique,
            learner_message=state.get("question", ""),
            rag_context=state.get("rag_context"),
        )
        merged = {
            **initial_meta,
            **regen_meta,
            "critic": {
                "overall": critique.overall,
                "scores": critique.scores,
                "critique": critique.critique,
                "model": critique.model,
                "tokens": critique.tokens,
            },
            "orchestrator": "langgraph",
        }
        return {"final_text": new_text, "final_meta": merged}

    def after_evaluate(
        state: CriticGraphState,
    ) -> Literal["regenerate", "pass_through"]:
        critique = state.get("critique")
        if critique is not None and critique.needs_regeneration:
            return "regenerate"
        return "pass_through"

    g = StateGraph(CriticGraphState)
    g.add_node("evaluate", evaluate_node)
    g.add_node("pass_through", pass_through)
    g.add_node("regenerate", regenerate_node)
    g.add_edge(START, "evaluate")
    g.add_conditional_edges(
        "evaluate",
        after_evaluate,
        {"regenerate": "regenerate", "pass_through": "pass_through"},
    )
    g.add_edge("pass_through", END)
    g.add_edge("regenerate", END)
    return g.compile()
