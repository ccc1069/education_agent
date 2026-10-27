"""Debate 流程的 LangGraph StateGraph 编排。

节点: round1_answers -> (可选) critique <-> revise -> synthesize
对外公开 API: build_debate_graph(provider).ainvoke(initial_state)
"""

from __future__ import annotations

import logging
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from llm.prompts import (
    DEBATE_PERSONAS,
    DEBATE_SYNTHESIS_SYSTEM_PROMPT,
    build_debate_critique_user_prompt,
    build_debate_round1_user_prompt,
    build_debate_roundN_user_prompt,
    build_debate_synthesis_user_prompt,
)
from llm.provider import LLMMessage, LLMProvider, LLMRole, LLMUnavailableError

logger = logging.getLogger(__name__)

PERSONA_SOCRATIC = "socratic"
PERSONA_DIRECT = "direct"


class DebateGraphState(TypedDict, total=False):
    """Debate StateGraph 状态。"""

    knowledge_id: str
    level: str
    mastery: float
    question: str
    rounds_total: int
    socratic_current: str
    direct_current: str
    crit_s_to_d: str
    crit_d_to_s: str
    current_round: int
    rounds_log: list[dict[str, Any]]
    consensus: str
    total_tokens: int
    llm_calls: int
    llm_used: bool
    abort: bool
    error: str


async def _call_llm(
    provider: LLMProvider,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 400,
) -> tuple[str, dict[str, Any]] | None:
    messages = [
        LLMMessage(role=LLMRole.SYSTEM, content=system_prompt),
        LLMMessage(role=LLMRole.USER, content=user_prompt),
    ]
    try:
        response = await provider.complete(
            messages, temperature=temperature, max_tokens=max_tokens
        )
        return response.content, {
            "model": response.model,
            "tokens": response.total_tokens,
            "latency_ms": response.latency_ms,
        }
    except LLMUnavailableError as e:
        logger.warning("Debate LLM call failed: %s", e)
        return None


def build_debate_graph(provider: LLMProvider):
    """编译 Debate StateGraph(绑定具体 LLMProvider)。"""

    async def round1_answers(state: DebateGraphState) -> dict[str, Any]:
        kid = state["knowledge_id"]
        level = state["level"]
        mastery = state["mastery"]
        question = state["question"]
        total_tokens = state.get("total_tokens", 0)
        llm_calls = state.get("llm_calls", 0)

        r1_socratic = await _call_llm(
            provider,
            DEBATE_PERSONAS[PERSONA_SOCRATIC],
            build_debate_round1_user_prompt(
                PERSONA_SOCRATIC, kid, level, mastery, question
            ),
        )
        r1_direct = await _call_llm(
            provider,
            DEBATE_PERSONAS[PERSONA_DIRECT],
            build_debate_round1_user_prompt(
                PERSONA_DIRECT, kid, level, mastery, question
            ),
        )

        if r1_socratic is None and r1_direct is None:
            logger.warning("Debate aborted: both personas failed in round 1")
            return {
                "abort": True,
                "error": "all personas failed",
                "llm_used": False,
                "socratic_current": "",
                "direct_current": "",
                "rounds_log": [],
                "consensus": "",
                "current_round": 1,
            }

        socratic_current = r1_socratic[0] if r1_socratic else ""
        direct_current = r1_direct[0] if r1_direct else ""
        if r1_socratic:
            total_tokens += r1_socratic[1]["tokens"]
            llm_calls += 1
        if r1_direct:
            total_tokens += r1_direct[1]["tokens"]
            llm_calls += 1

        return {
            "abort": False,
            "socratic_current": socratic_current,
            "direct_current": direct_current,
            "crit_s_to_d": "",
            "crit_d_to_s": "",
            "current_round": 1,
            "rounds_log": [],
            "total_tokens": total_tokens,
            "llm_calls": llm_calls,
            "llm_used": True,
            "error": "",
        }

    async def critique(state: DebateGraphState) -> dict[str, Any]:
        socratic_current = state.get("socratic_current", "")
        direct_current = state.get("direct_current", "")
        total_tokens = state.get("total_tokens", 0)
        llm_calls = state.get("llm_calls", 0)
        crit_s_to_d = ""
        crit_d_to_s = ""

        if direct_current and socratic_current:
            c = await _call_llm(
                provider,
                DEBATE_PERSONAS[PERSONA_SOCRATIC],
                build_debate_critique_user_prompt(
                    PERSONA_SOCRATIC, PERSONA_DIRECT, direct_current
                ),
                temperature=0.3,
                max_tokens=200,
            )
            if c:
                crit_s_to_d = c[0]
                total_tokens += c[1]["tokens"]
                llm_calls += 1

        if socratic_current and direct_current:
            c = await _call_llm(
                provider,
                DEBATE_PERSONAS[PERSONA_DIRECT],
                build_debate_critique_user_prompt(
                    PERSONA_DIRECT, PERSONA_SOCRATIC, socratic_current
                ),
                temperature=0.3,
                max_tokens=200,
            )
            if c:
                crit_d_to_s = c[0]
                total_tokens += c[1]["tokens"]
                llm_calls += 1

        rounds_log = list(state.get("rounds_log") or [])
        # round1 批评后落盘本轮; 后续轮在 revise 后落盘
        if state.get("current_round", 1) == 1 and not rounds_log:
            rounds_log.append(
                {
                    "round_num": 1,
                    "socratic_response": socratic_current,
                    "direct_response": direct_current,
                    "socratic_critique_of_direct": crit_s_to_d,
                    "direct_critique_of_socratic": crit_d_to_s,
                }
            )

        return {
            "crit_s_to_d": crit_s_to_d,
            "crit_d_to_s": crit_d_to_s,
            "rounds_log": rounds_log,
            "total_tokens": total_tokens,
            "llm_calls": llm_calls,
        }

    async def record_round1_only(state: DebateGraphState) -> dict[str, Any]:
        """单轮辩论: 不批评,直接记录 round1。"""
        return {
            "rounds_log": [
                {
                    "round_num": 1,
                    "socratic_response": state.get("socratic_current", ""),
                    "direct_response": state.get("direct_current", ""),
                    "socratic_critique_of_direct": "",
                    "direct_critique_of_socratic": "",
                }
            ]
        }

    async def revise(state: DebateGraphState) -> dict[str, Any]:
        kid = state["knowledge_id"]
        level = state["level"]
        mastery = state["mastery"]
        question = state["question"]
        socratic_current = state.get("socratic_current", "")
        direct_current = state.get("direct_current", "")
        crit_s_to_d = state.get("crit_s_to_d", "")
        crit_d_to_s = state.get("crit_d_to_s", "")
        total_tokens = state.get("total_tokens", 0)
        llm_calls = state.get("llm_calls", 0)
        next_round = state.get("current_round", 1) + 1

        new_socratic = socratic_current
        new_direct = direct_current

        if crit_d_to_s:
            r = await _call_llm(
                provider,
                DEBATE_PERSONAS[PERSONA_SOCRATIC],
                build_debate_roundN_user_prompt(
                    PERSONA_SOCRATIC,
                    kid,
                    level,
                    mastery,
                    question,
                    own_previous=socratic_current,
                    opponent_previous=direct_current,
                    opponent_critique=crit_d_to_s,
                ),
            )
            if r:
                new_socratic = r[0]
                total_tokens += r[1]["tokens"]
                llm_calls += 1

        if crit_s_to_d:
            r = await _call_llm(
                provider,
                DEBATE_PERSONAS[PERSONA_DIRECT],
                build_debate_roundN_user_prompt(
                    PERSONA_DIRECT,
                    kid,
                    level,
                    mastery,
                    question,
                    own_previous=direct_current,
                    opponent_previous=socratic_current,
                    opponent_critique=crit_s_to_d,
                ),
            )
            if r:
                new_direct = r[0]
                total_tokens += r[1]["tokens"]
                llm_calls += 1

        rounds_log = list(state.get("rounds_log") or [])
        rounds_log.append(
            {
                "round_num": next_round,
                "socratic_response": new_socratic,
                "direct_response": new_direct,
                "socratic_critique_of_direct": "",
                "direct_critique_of_socratic": "",
            }
        )

        return {
            "socratic_current": new_socratic,
            "direct_current": new_direct,
            "current_round": next_round,
            "rounds_log": rounds_log,
            "total_tokens": total_tokens,
            "llm_calls": llm_calls,
            # 清空旧批评; 若还需下一轮会再跑 critique 并回填到上一轮记录
            "crit_s_to_d": "",
            "crit_d_to_s": "",
        }

    async def critique_mid(state: DebateGraphState) -> dict[str, Any]:
        """中间轮批评: 更新最新一轮的 critique 字段。"""
        socratic_current = state.get("socratic_current", "")
        direct_current = state.get("direct_current", "")
        total_tokens = state.get("total_tokens", 0)
        llm_calls = state.get("llm_calls", 0)
        crit_s_to_d = ""
        crit_d_to_s = ""

        if direct_current:
            c = await _call_llm(
                provider,
                DEBATE_PERSONAS[PERSONA_SOCRATIC],
                build_debate_critique_user_prompt(
                    PERSONA_SOCRATIC, PERSONA_DIRECT, direct_current
                ),
                temperature=0.3,
                max_tokens=200,
            )
            if c:
                crit_s_to_d = c[0]
                total_tokens += c[1]["tokens"]
                llm_calls += 1
        if socratic_current:
            c = await _call_llm(
                provider,
                DEBATE_PERSONAS[PERSONA_DIRECT],
                build_debate_critique_user_prompt(
                    PERSONA_DIRECT, PERSONA_SOCRATIC, socratic_current
                ),
                temperature=0.3,
                max_tokens=200,
            )
            if c:
                crit_d_to_s = c[0]
                total_tokens += c[1]["tokens"]
                llm_calls += 1

        rounds_log = list(state.get("rounds_log") or [])
        if rounds_log:
            last = dict(rounds_log[-1])
            last["socratic_critique_of_direct"] = crit_s_to_d
            last["direct_critique_of_socratic"] = crit_d_to_s
            rounds_log[-1] = last

        return {
            "crit_s_to_d": crit_s_to_d,
            "crit_d_to_s": crit_d_to_s,
            "rounds_log": rounds_log,
            "total_tokens": total_tokens,
            "llm_calls": llm_calls,
        }

    async def synthesize(state: DebateGraphState) -> dict[str, Any]:
        if state.get("abort"):
            return {
                "consensus": "",
                "llm_used": False,
            }

        kid = state["knowledge_id"]
        level = state["level"]
        mastery = state["mastery"]
        question = state["question"]
        socratic_current = state.get("socratic_current", "")
        direct_current = state.get("direct_current", "")
        total_tokens = state.get("total_tokens", 0)
        llm_calls = state.get("llm_calls", 0)
        llm_used = state.get("llm_used", True)
        consensus = ""

        if socratic_current or direct_current:
            synth = await _call_llm(
                provider,
                DEBATE_SYNTHESIS_SYSTEM_PROMPT,
                build_debate_synthesis_user_prompt(
                    kid,
                    level,
                    mastery,
                    question,
                    socratic_final=socratic_current,
                    direct_final=direct_current,
                ),
                temperature=0.5,
                max_tokens=400,
            )
            if synth:
                consensus = synth[0]
                total_tokens += synth[1]["tokens"]
                llm_calls += 1
            else:
                consensus = (
                    socratic_current
                    if len(socratic_current) >= len(direct_current)
                    else direct_current
                )
                llm_used = False

        return {
            "consensus": consensus,
            "total_tokens": total_tokens,
            "llm_calls": llm_calls,
            "llm_used": llm_used,
        }

    def after_round1(state: DebateGraphState) -> Literal["critique", "record_round1_only", "synthesize"]:
        if state.get("abort"):
            return "synthesize"
        if state.get("rounds_total", 1) > 1:
            return "critique"
        return "record_round1_only"

    def after_revise(state: DebateGraphState) -> Literal["critique_mid", "synthesize"]:
        if state.get("current_round", 1) < state.get("rounds_total", 1):
            return "critique_mid"
        return "synthesize"

    g = StateGraph(DebateGraphState)
    g.add_node("round1_answers", round1_answers)
    g.add_node("critique", critique)
    g.add_node("record_round1_only", record_round1_only)
    g.add_node("revise", revise)
    g.add_node("critique_mid", critique_mid)
    g.add_node("synthesize", synthesize)

    g.add_edge(START, "round1_answers")
    g.add_conditional_edges(
        "round1_answers",
        after_round1,
        {
            "critique": "critique",
            "record_round1_only": "record_round1_only",
            "synthesize": "synthesize",
        },
    )
    g.add_edge("critique", "revise")
    g.add_edge("record_round1_only", "synthesize")
    g.add_conditional_edges(
        "revise",
        after_revise,
        {
            "critique_mid": "critique_mid",
            "synthesize": "synthesize",
        },
    )
    g.add_edge("critique_mid", "revise")
    g.add_edge("synthesize", END)

    return g.compile()
