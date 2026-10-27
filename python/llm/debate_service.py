"""Multi-Agent Debate 服务: LangGraph StateGraph 编排 2-persona 辩论 + 综合。

设计:
- 2 个 persona: socratic(启发式提问) vs direct(清晰讲解)
- N 轮辩论(默认 2): 第 1 轮各自作答,第 2 轮互相批评后修订
- synthesizer 综合两版最终回复,产出 consensus
- 失败降级: 任一环节 LLM 不可用,返回已收集的最佳回复

用法:
    service = DebateLLMService()
    result = await service.run_debate(
        knowledge_id="algebra",
        level="beginner",
        mastery=0.3,
        question="什么是方程?",
    )
"""

from dataclasses import dataclass, field
from typing import Any

from llm.debate_graph import PERSONA_DIRECT, PERSONA_SOCRATIC, build_debate_graph
from llm.factory import get_llm_provider
from llm.provider import LLMProvider

DEFAULT_ROUNDS = 2
MAX_ROUNDS = 4

# 再导出 persona 常量,供测试与外部引用
__all__ = [
    "DEFAULT_ROUNDS",
    "MAX_ROUNDS",
    "PERSONA_DIRECT",
    "PERSONA_SOCRATIC",
    "DebateLLMService",
    "DebateResult",
    "DebateRound",
]


@dataclass
class DebateRound:
    """单轮辩论记录。"""

    round_num: int
    socratic_response: str
    direct_response: str
    socratic_critique_of_direct: str
    direct_critique_of_socratic: str


@dataclass
class DebateResult:
    """辩论完整结果。"""

    consensus: str
    rounds: list[DebateRound]
    socratic_final: str
    direct_final: str
    metadata: dict[str, Any] = field(default_factory=dict)


class DebateLLMService:
    """Multi-Agent Debate 服务(LangGraph StateGraph)。

    流程(N=2 轮):
        Round 1:
            - socratic 作答 S1
            - direct 作答 D1
            - socratic 批评 D1 -> C_S
            - direct 批评 S1 -> C_D
        Round 2:
            - socratic 看 C_D 修订 -> S2
            - direct 看 C_S 修订 -> D2
        Synthesis:
            - 综合 S2 + D2 -> consensus
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        rounds: int = DEFAULT_ROUNDS,
    ) -> None:
        self.provider = provider or get_llm_provider()
        self.rounds = max(1, min(rounds, MAX_ROUNDS))
        self._graph = build_debate_graph(self.provider)

    async def run_debate(
        self,
        knowledge_id: str,
        level: str,
        mastery: float,
        question: str,
    ) -> DebateResult:
        """运行完整辩论流程(ainvoke LangGraph)。"""
        final = await self._graph.ainvoke(
            {
                "knowledge_id": knowledge_id,
                "level": level,
                "mastery": mastery,
                "question": question,
                "rounds_total": self.rounds,
                "socratic_current": "",
                "direct_current": "",
                "crit_s_to_d": "",
                "crit_d_to_s": "",
                "current_round": 0,
                "rounds_log": [],
                "consensus": "",
                "total_tokens": 0,
                "llm_calls": 0,
                "llm_used": True,
                "abort": False,
                "error": "",
            }
        )

        rounds = [
            DebateRound(
                round_num=int(r["round_num"]),
                socratic_response=str(r.get("socratic_response", "")),
                direct_response=str(r.get("direct_response", "")),
                socratic_critique_of_direct=str(r.get("socratic_critique_of_direct", "")),
                direct_critique_of_socratic=str(r.get("direct_critique_of_socratic", "")),
            )
            for r in (final.get("rounds_log") or [])
        ]

        meta: dict[str, Any] = {
            "llm_used": bool(final.get("llm_used", False)),
            "llm_calls": int(final.get("llm_calls", 0)),
            "total_tokens": int(final.get("total_tokens", 0)),
            "rounds": self.rounds,
            "personas": [PERSONA_SOCRATIC, PERSONA_DIRECT],
            "orchestrator": "langgraph",
        }
        if final.get("error"):
            meta["error"] = final["error"]

        return DebateResult(
            consensus=str(final.get("consensus", "")),
            rounds=rounds,
            socratic_final=str(final.get("socratic_current", "")),
            direct_final=str(final.get("direct_current", "")),
            metadata=meta,
        )
