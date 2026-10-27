"""Mock LLM: 用于测试和无 API Key 的本地开发。

行为: 根据输入 prompt 关键字返回预设回复,完全不发起网络请求。
"""

import logging
import time
from typing import Any

from llm.provider import LLMMessage, LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class MockLLMProvider(LLMProvider):
    """测试用 Mock Provider。无网络调用,即时返回。"""

    def __init__(self, model: str = "mock-1.0") -> None:
        super().__init__(name="mock", model=model, timeout=1.0, max_retries=1)

    @property
    def supports_vision(self) -> bool:
        """Mock 支持 vision(用于测试 vision 路径)。"""
        return True

    async def _call(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        start = time.monotonic()
        # 取最后一条 user 消息作为输入
        user_msg = ""
        has_image = False
        image_count = 0
        for m in reversed(messages):
            if m.role.value == "user":
                user_msg = m.content
                if m.images:
                    has_image = True
                    image_count = len(m.images)
                break

        content = self._generate_response(user_msg, has_image, image_count)
        latency_ms = (time.monotonic() - start) * 1000
        token_count = len(content) // 4

        return LLMResponse(
            content=content,
            model=self.model,
            prompt_tokens=len(user_msg) // 4,
            completion_tokens=token_count,
            total_tokens=len(user_msg) // 4 + token_count,
            finish_reason="stop",
            latency_ms=latency_ms,
            metadata={"provider": self.name, "mock": True, "vision": has_image},
        )

    def _generate_response(
        self, user_input: str, has_image: bool = False, image_count: int = 0
    ) -> str:
        """根据输入关键字生成教学性回复。"""
        if has_image:
            return self._generate_vision_response(user_input, image_count)
        if "题型" in user_input and "难度" in user_input:
            return self._generate_question_json(user_input)
        if "判断学生答案" in user_input and "参考答案" in user_input:
            return self._generate_verify_json(user_input)
        if "提示" in user_input or "hint" in user_input.lower():
            return (
                "【Mock 提示】请回顾该知识点的核心概念:\n"
                "1. 它解决什么问题?\n"
                "2. 关键变量有哪些?\n"
                "3. 与已学知识如何关联?\n"
                "试着用 1 分钟写出你的思路,然后再看下一步。"
            )
        if "教学" in user_input or "teach" in user_input.lower():
            return (
                "【Mock 教学】让我们一步步思考:\n"
                "首先,这个问题的本质是什么?\n"
                "你之前学过的哪个知识点和它相关?\n"
                "试着用一个例子说明你的理解。"
            )
        if "提问" in user_input or "question" in user_input.lower():
            return (
                "【Mock 回答】这是一个很好的问题。\n"
                "我注意到你关注的是核心概念。让我们从定义开始,\n"
                "然后逐步推导到应用场景。你觉得这个方向对吗?"
            )
        # 兜底
        return (
            f"【Mock 回复】已收到你的输入({len(user_input)} 字符)。\n"
            "在配置真实 LLM API Key 后,这里会返回个性化的教学回复。"
        )

    def _generate_question_json(self, user_input: str) -> str:
        """Mock 题目生成: 解析知识点/题型/难度,返回 JSON。"""
        import json as _json
        import re

        kid = "mock-knowledge"
        m = re.search(r"【知识点】(.+?)$", user_input, re.MULTILINE)
        if m:
            kid = m.group(1).strip()[:64]

        qtype = "multiple_choice"
        m = re.search(r"【题型】(\w+)", user_input)
        if m:
            qtype = m.group(1).strip()

        difficulty = 3
        m = re.search(r"【难度】(\d+)/5", user_input)
        if m:
            try:
                difficulty = int(m.group(1))
            except ValueError:
                difficulty = 3

        if qtype == "multiple_choice":
            data = {
                "stem": f"关于「{kid}」的难度 {difficulty} Mock 选择题",
                "options": [
                    {"key": "A", "text": "Mock 选项 A"},
                    {"key": "B", "text": "Mock 选项 B"},
                    {"key": "C", "text": "Mock 选项 C"},
                    {"key": "D", "text": "Mock 选项 D"},
                ],
                "answer_key": "A",
                "analysis": f"Mock 解析: 考查 {kid} 的基础概念。",
            }
        elif qtype == "fill_blank":
            data = {
                "stem": f"{kid}的核心公式是 ___ (Mock)",
                "answer": "Mock答案",
                "analysis": f"Mock 解析: 考查 {kid} 的定义。",
            }
        elif qtype == "true_false":
            data = {
                "stem": f"掌握 {kid} 即可解决所有相关问题。(Mock)",
                "answer": False,
                "analysis": "Mock 解析: 知识点需结合情境应用。",
            }
        else:  # open_ended
            data = {
                "stem": f"请用自己的话解释 {kid} 并举例。(Mock)",
                "reference_answer": f"Mock 参考答案: {kid} 的定义 + 示例",
                "analysis": "Mock 解析: 考查概念理解与举例。",
            }
        return _json.dumps(data, ensure_ascii=False)

    def _generate_verify_json(self, user_input: str) -> str:
        """Mock 答案校验: 严格匹配参考答案。"""
        import json as _json
        import re

        ref = ""
        m = re.search(r"【参考答案】(.+?)$", user_input, re.MULTILINE)
        if m:
            ref = m.group(1).strip()[:200]

        stu = ""
        m = re.search(r"【学生答案】(.+?)$", user_input, re.MULTILINE)
        if m:
            stu = m.group(1).strip()[:200]

        is_correct = ref == stu and bool(ref)
        feedback = "Mock: 答案匹配" if is_correct else "Mock: 答案不匹配"
        return _json.dumps(
            {"is_correct": is_correct, "feedback": feedback}, ensure_ascii=False
        )

    def _generate_vision_response(self, user_input: str, image_count: int) -> str:
        """Mock 视觉响应: 描述"看到了"图片并给出教学引导。"""
        return (
            f"【Mock 视觉分析】已收到 {image_count} 张图片。\n"
            "我能看到这是一道数学题,让我引导你思考:\n"
            "1. 题目中给出了哪些已知条件?\n"
            "2. 要求解的是什么?\n"
            "3. 你能想到用哪个公式或定理?\n"
            f"({len(user_input)} 字符的文本提示已纳入考虑)\n"
            "试着先写出你的思路,再告诉我卡在哪一步。"
        )
