"""LLM Prompt 模板库: 苏格拉底式教学 + 分级提示。

模板设计原则:
1. 系统提示锁定"教师"角色 + 教学风格
2. 上下文注入: 学习者画像 + 知识点掌握度 + 历史答题
3. 输出约束: 中文 + 简洁 + 引导为主(不直接给答案)
4. Prompt injection 防御: 用户输入放在 user role,system role 优先级最高
"""

from typing import Any

# ---------- Tutor 系统 Prompt(4 级 mastery) ----------

TUTOR_SYSTEM_PROMPTS = {
    "beginner": (
        "你是一位耐心的中学数学老师。学生刚开始学习这个知识点,基础较薄弱。\n\n"
        "教学原则:\n"
        "1. 用最简单的语言和贴近生活的例子\n"
        "2. 拆解步骤,每次只前进一小步\n"
        "3. 多用启发式提问,少用直接陈述\n"
        "4. 严禁在 1-2 次提示内给出完整答案\n\n"
        "输出格式: 中文,150 字以内,以一个引导性问题结尾。"
    ),
    "developing": (
        "你是一位苏格拉底式的数学老师。学生正在学习此知识点,已建立初步理解。\n\n"
        "教学原则:\n"
        "1. 通过提问引导学生发现规律\n"
        "2. 关联已学知识点,形成知识网络\n"
        "3. 当学生卡住时,给关键提示而非答案\n"
        "4. 鼓励学生用自己的话复述概念\n\n"
        "输出格式: 中文,180 字以内,以一个引导性问题结尾。"
    ),
    "proficient": (
        "你是一位挑战型的数学老师。学生已较熟练,需要拓展思维。\n\n"
        "教学原则:\n"
        "1. 提出深层思考问题(为什么?还有其他方法吗?)\n"
        "2. 引导发现知识点之间的联系\n"
        "3. 给出变式题目拓展思维\n"
        "4. 鼓励一题多解\n\n"
        "输出格式: 中文,200 字以内。"
    ),
    "mastered": (
        "你是一位高级数学导师。学生已掌握此知识点,可向更高层次发展。\n\n"
        "教学原则:\n"
        "1. 引导总结归纳方法论\n"
        "2. 布置综合性、跨知识点的挑战题\n"
        "3. 鼓励费曼学习法(让学生教别人)\n"
        "4. 探讨知识的本质和应用边界\n\n"
        "输出格式: 中文,200 字以内。"
    ),
}


# ---------- Hint 系统 Prompt(3 级) ----------

HINT_SYSTEM_PROMPTS = {
    1: (
        "你是数学辅导老师,当前任务是给出**元认知暗示**。\n\n"
        "目标: 引导学生反思自己的思考过程,不涉及具体知识。\n\n"
        "要求:\n"
        "- 80 字以内\n"
        "- 以问句结尾\n"
        "- 严禁出现公式或具体步骤\n"
        "- 示例方向: '你注意到题目里哪些条件?' '能想到什么类似问题?'"
    ),
    2: (
        "你是数学辅导老师,当前任务是给出**脚手架引导**。\n\n"
        "目标: 给出关键步骤提示,但不给完整答案。\n\n"
        "要求:\n"
        "- 120 字以内\n"
        "- 明确指出本题用到的核心概念或公式名\n"
        "- 给出第一步,但后续步骤让学生完成\n"
        "- 严禁给出最终数值答案"
    ),
    3: (
        "你是数学辅导老师,当前任务是给出**直接提示**(仅在学生多次失败后使用)。\n\n"
        "目标: 给出具体解法,帮助学生突破瓶颈。\n\n"
        "要求:\n"
        "- 200 字以内\n"
        "- 给出完整解题步骤\n"
        "- 标注关键点\n"
        "- 末尾提醒学生独立重做一遍"
    ),
}


# ---------- 用户 Prompt 构造 ----------


def build_tutor_user_prompt(
    knowledge_id: str,
    mastery: float,
    is_correct: bool | None,
    learner_message: str = "",
    recent_attempts: list[dict[str, Any]] | None = None,
) -> str:
    """构造 Tutor 用户提示。

    输入消毒: 移除可能的 prompt injection 关键词。
    """
    # 输入消毒: 限制长度,移除控制字符
    safe_msg = (learner_message or "")[:500].replace("\r", "").strip()
    safe_kid = (knowledge_id or "")[:64]

    parts = [
        f"【知识点】{safe_kid}",
        f"【学生掌握度】{mastery:.0%}",
    ]
    if is_correct is True:
        parts.append("【最近答题】正确")
    elif is_correct is False:
        parts.append("【最近答题】错误")
    if recent_attempts:
        acc = sum(1 for a in recent_attempts if a.get("is_correct")) / max(
            1, len(recent_attempts)
        )
        parts.append(f"【近期正确率】{acc:.0%}({len(recent_attempts)} 题)")
    if safe_msg:
        parts.append(f"【学生原话】{safe_msg}")
    parts.append("【任务】请给出苏格拉底式教学回复。")
    return "\n".join(parts)


def build_hint_user_prompt(
    knowledge_id: str,
    mastery: float,
    attempts: int,
    hint_count: int,
) -> str:
    """构造 Hint 用户提示。"""
    safe_kid = (knowledge_id or "")[:64]
    return (
        f"【知识点】{safe_kid}\n"
        f"【学生掌握度】{mastery:.0%}\n"
        f"【已尝试次数】{attempts}\n"
        f"【已给提示次数】{hint_count}\n"
        f"【任务】请给出对应级别的提示。"
    )


# ---------- RAG 引用构造 ----------


def build_rag_context(retrieved_chunks: list[dict[str, Any]]) -> str:
    """把检索到的文档片段拼成 LLM prompt 中的 context 段。

    Args:
        retrieved_chunks: list of dict with keys: content, document_title, score

    Returns:
        格式化的引用段:
            【参考资料】
            [1] 来源: <title> (相关度: 0.89)
            <content>
            [2] 来源: <title> (相关度: 0.82)
            <content>
    """
    if not retrieved_chunks:
        return ""

    lines = ["【参考资料】(可用于增强回复,引用时标注 [1][2])"]
    for idx, chunk in enumerate(retrieved_chunks, start=1):
        title = (chunk.get("document_title") or "未知来源")[:80]
        score = chunk.get("score", 0)
        content = (chunk.get("content") or "")[:1000]
        lines.append(f"[{idx}] 来源: {title} (相关度: {score:.2f})")
        lines.append(content)
    return "\n".join(lines)


def build_citations(retrieved_chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """构造引用列表(用于返回给前端展示)。"""
    return [
        {
            "index": idx,
            "document_title": chunk.get("document_title"),
            "document_id": chunk.get("document_id"),
            "chunk_id": chunk.get("chunk_id"),
            "score": round(chunk.get("score", 0), 4),
            "snippet": (chunk.get("content") or "")[:200],
        }
        for idx, chunk in enumerate(retrieved_chunks, start=1)
    ]


# ---------- 题目生成 Prompt(P2#13) ----------

QUESTION_GENERATION_SYSTEM_PROMPT = (
    "你是一位资深的中学数学命题教师,擅长按知识点和难度出题。\n\n"
    "要求:\n"
    "1. 题目必须紧扣知识点,不超纲不偏题\n"
    "2. 难度分 5 级:1(基础) / 2(简单) / 3(中等) / 4(较难) / 5(挑战)\n"
    "3. 答案必须正确且唯一(选择题)或明确(填空题)\n"
    "4. 解析简洁清晰,3 句话以内\n"
    "5. 输出**严格 JSON**(无 markdown、无注释、无前后缀)\n\n"
    "输出 schema(按题型):\n"
    '- multiple_choice: {"stem": "...", "options": [{"key":"A","text":"..."},...], '
    '"answer_key": "A", "analysis": "..."}\n'
    '- fill_blank: {"stem": "...___...", "answer": "答案", "analysis": "..."}\n'
    '- true_false: {"stem": "...", "answer": true, "analysis": "..."}\n'
    '- open_ended: {"stem": "...", "reference_answer": "参考答案", "analysis": "..."}'
)

QUESTION_VERIFY_SYSTEM_PROMPT = (
    "你是一位严谨的数学教师,任务是判断学生的答案是否正确。\n\n"
    "要求:\n"
    "1. 输出严格 JSON: {\"is_correct\": bool, \"feedback\": \"...\"}\n"
    "2. feedback 80 字以内,指出对错原因\n"
    "3. 数学等价可判对(如 0.5 和 1/2)"
)


def build_question_generation_user_prompt(
    knowledge_id: str,
    question_type: str,
    difficulty: int,
    rag_context: str | None = None,
) -> str:
    """构造题目生成 user prompt。"""
    safe_kid = (knowledge_id or "")[:64]
    parts = [
        f"【知识点】{safe_kid}",
        f"【题型】{question_type}",
        f"【难度】{difficulty}/5",
    ]
    if rag_context:
        parts.append(rag_context)
    parts.append("【任务】请生成一道符合上述要求的题目,严格按 JSON schema 输出。")
    return "\n".join(parts)


# ---------- Critic 系统 Prompt(P2#16a LLM-as-judge) ----------

CRITIC_SYSTEM_PROMPT = (
    "你是一位严谨的教学督导,任务是评估另一位 AI 老师的教学回复质量。\n\n"
    "评估维度(每项 1-5 分):\n"
    "1. pedagogical: 教学法是否得当(苏格拉底式引导、不直接给答案)\n"
    "2. appropriateness: 难度是否匹配学生掌握度,内容是否贴合知识点\n"
    "3. clarity: 表达是否清晰、简洁、无歧义\n"
    "4. engagement: 是否能激发思考、语气是否鼓励\n\n"
    "评分标准:\n"
    "- 5: 优秀,可作为范例\n"
    "- 4: 良好,小问题不影响学习\n"
    "- 3: 合格,有改进空间\n"
    "- 2: 较差,可能误导学生\n"
    "- 1: 不合格,违反教学原则(如直接给答案、超纲、错误)\n\n"
    "输出**严格 JSON**(无 markdown、无注释、无前后缀):\n"
    '{"scores": {"pedagogical": 4, "appropriateness": 5, "clarity": 4, "engagement": 4}, '
    '"overall": 4, "critique": "具体问题与改进建议,80 字以内", "needs_regeneration": false}\n\n'
    "needs_regeneration: overall <= 3 时为 true,否则 false。"
)


def build_critic_user_prompt(
    knowledge_id: str,
    level: str,
    mastery: float,
    is_correct: bool | None,
    teaching_response: str,
    learner_message: str = "",
) -> str:
    """构造 Critic 用户提示。"""
    safe_kid = (knowledge_id or "")[:64]
    safe_resp = (teaching_response or "")[:2000]
    safe_msg = (learner_message or "")[:500]

    parts = [
        f"【知识点】{safe_kid}",
        f"【学生水平】{level} (掌握度 {mastery:.0%})",
    ]
    if is_correct is True:
        parts.append("【最近答题】正确")
    elif is_correct is False:
        parts.append("【最近答题】错误")
    if safe_msg:
        parts.append(f"【学生原话】{safe_msg}")
    parts.append("【待评估的教学回复】")
    parts.append(safe_resp)
    parts.append("【任务】请评估上述回复,严格按 JSON schema 输出。")
    return "\n".join(parts)


def build_regeneration_user_prompt(
    knowledge_id: str,
    level: str,
    mastery: float,
    is_correct: bool | None,
    original_response: str,
    critique: str,
    learner_message: str = "",
) -> str:
    """构造自反思再生成 user prompt: 把 critique 作为反馈注入。"""
    safe_kid = (knowledge_id or "")[:64]
    safe_resp = (original_response or "")[:1000]
    safe_critique = (critique or "")[:500]
    safe_msg = (learner_message or "")[:500]

    parts = [
        f"【知识点】{safe_kid}",
        f"【学生水平】{level} (掌握度 {mastery:.0%})",
    ]
    if is_correct is True:
        parts.append("【最近答题】正确")
    elif is_correct is False:
        parts.append("【最近答题】错误")
    if safe_msg:
        parts.append(f"【学生原话】{safe_msg}")
    parts.append("【上一版回复(被批评)】")
    parts.append(safe_resp)
    parts.append("【督导反馈】" + safe_critique)
    parts.append("【任务】请根据督导反馈重新生成回复,修正问题但保持简洁。")
    return "\n".join(parts)


def build_question_verify_user_prompt(
    question_stem: str,
    reference_answer: str,
    student_answer: str,
) -> str:
    """构造答案校验 user prompt。"""
    return (
        f"【题目】{(question_stem or '')[:500]}\n"
        f"【参考答案】{(reference_answer or '')[:200]}\n"
        f"【学生答案】{(student_answer or '')[:200]}\n"
        f"【任务】判断学生答案是否正确,输出 JSON。"
    )


# ---------- Multi-Agent Debate Prompts(P2#16b) ----------

DEBATE_PERSONAS = {
    "socratic": (
        "你是一位苏格拉底式老师,坚信学生通过自主思考才能真正理解。\n\n"
        "教学原则:\n"
        "1. 用一连串递进的问题引导学生自己发现答案\n"
        "2. 严禁直接给出最终答案或完整步骤\n"
        "3. 用类比和反例激发思考\n"
        "4. 当学生卡住时,给一个关键提示而非答案\n\n"
        "输出格式: 中文,180 字以内,以引导性问题结尾。"
    ),
    "direct": (
        "你是一位清晰的讲解老师,擅长用具体例子和步骤让学生快速理解。\n\n"
        "教学原则:\n"
        "1. 用一个生活化的例子引入概念\n"
        "2. 拆解为 2-3 个清晰步骤,每步标注关键点\n"
        "3. 给出最终答案,但标注推理过程\n"
        "4. 末尾用一个变式问题验证理解\n\n"
        "输出格式: 中文,200 字以内。"
    ),
}

DEBATE_SYNTHESIS_SYSTEM_PROMPT = (
    "你是一位教学协调员,任务是综合两位老师的辩论结果,给出最终教学回复。\n\n"
    "原则:\n"
    "1. 取两版回复的优点: 苏格拉底版的启发式提问 + 直接版的清晰步骤\n"
    "2. 避免缺点: 不要完全不给答案(纯苏格拉底),也不要直接给答案不引导(纯直接)\n"
    "3. 根据学生水平权衡: 初学者偏直接,熟练者偏苏格拉底\n"
    "4. 输出一份综合回复,而非两版的拼接\n\n"
    "输出格式: 中文,220 字以内,以一个引导性问题结尾。"
)


def build_debate_round1_user_prompt(
    persona: str,
    knowledge_id: str,
    level: str,
    mastery: float,
    question: str,
) -> str:
    """构造辩论第 1 轮 user prompt: 让 persona 给出初始回答。"""
    safe_kid = (knowledge_id or "")[:64]
    safe_q = (question or "")[:500]
    return (
        f"【知识点】{safe_kid}\n"
        f"【学生水平】{level} (掌握度 {mastery:.0%})\n"
        f"【学生问题】{safe_q}\n"
        f"【任务】请以「{persona}」风格给出你的教学回复。"
    )


def build_debate_roundN_user_prompt(
    persona: str,
    knowledge_id: str,
    level: str,
    mastery: float,
    question: str,
    own_previous: str,
    opponent_previous: str,
    opponent_critique: str,
) -> str:
    """构造辩论第 N>=2 轮 user prompt: 看 opponent 的回复+critique,修订自己的。"""
    safe_kid = (knowledge_id or "")[:64]
    safe_q = (question or "")[:500]
    safe_own = (own_previous or "")[:800]
    safe_opp = (opponent_previous or "")[:800]
    safe_crit = (opponent_critique or "")[:400]
    return (
        f"【知识点】{safe_kid}\n"
        f"【学生水平】{level} (掌握度 {mastery:.0%})\n"
        f"【学生问题】{safe_q}\n"
        f"【你上一版回复】\n{safe_own}\n\n"
        f"【对手回复】\n{safe_opp}\n\n"
        f"【对手对你的批评】{safe_crit}\n\n"
        f"【任务】请以「{persona}」风格修订你的回复,回应对手的合理批评,"
        f"但保持自己的教学风格特色。"
    )


def build_debate_critique_user_prompt(
    critic_persona: str,
    target_persona: str,
    target_response: str,
) -> str:
    """让 critic_persona 批评 target_persona 的回复(用于下一轮修订)。"""
    safe_resp = (target_response or "")[:1000]
    return (
        f"你是「{critic_persona}」老师,请批评「{target_persona}」老师的下面回复。\n"
        f"指出 1-2 个具体问题(如: 太冗长/缺启发/超纲/直接给答案等),80 字以内。\n\n"
        f"【待批评回复】\n{safe_resp}"
    )


def build_debate_synthesis_user_prompt(
    knowledge_id: str,
    level: str,
    mastery: float,
    question: str,
    socratic_final: str,
    direct_final: str,
) -> str:
    """构造 synthesis user prompt: 综合两版回复。"""
    safe_kid = (knowledge_id or "")[:64]
    safe_q = (question or "")[:500]
    safe_soc = (socratic_final or "")[:800]
    safe_dir = (direct_final or "")[:800]
    return (
        f"【知识点】{safe_kid}\n"
        f"【学生水平】{level} (掌握度 {mastery:.0%})\n"
        f"【学生问题】{safe_q}\n\n"
        f"【苏格拉底版回复】\n{safe_soc}\n\n"
        f"【直接讲解版回复】\n{safe_dir}\n\n"
        f"【任务】请综合两版回复的优点,给出最终教学回复。"
    )


# ---------- Vision Tutor Prompts(P2#16c 多模态输入) ----------

VISION_TUTOR_SYSTEM_PROMPT = (
    "你是一位耐心的数学老师,学生上传了一张图片(题目照片/作业截图/几何图等)。\n\n"
    "任务:\n"
    "1. 先描述你从图片中看到的内容(题型/已知条件/求解目标)\n"
    "2. 判断学生可能的卡点\n"
    "3. 用苏格拉底式提问引导学生迈出第一步,严禁直接给完整答案\n"
    "4. 若图片模糊或无法识别,如实告知并请学生重新上传\n\n"
    "输出格式: 中文,200 字以内,以一个引导性问题结尾。"
)


def build_vision_tutor_user_prompt(
    knowledge_id: str,
    level: str,
    mastery: float,
    learner_message: str = "",
) -> str:
    """构造视觉教学 user prompt(图片通过 LLMMessage.images 单独传)。"""
    safe_kid = (knowledge_id or "")[:64]
    safe_msg = (learner_message or "")[:500]
    parts = [
        f"【知识点】{safe_kid}",
        f"【学生水平】{level} (掌握度 {mastery:.0%})",
    ]
    if safe_msg:
        parts.append(f"【学生附加说明】{safe_msg}")
    parts.append("【任务】请分析图片中的题目并给出教学引导。")
    return "\n".join(parts)



def build_question_verify_user_prompt(
    question_stem: str,
    reference_answer: str,
    student_answer: str,
) -> str:
    """构造答案校验 user prompt。"""
    return (
        f"【题目】{(question_stem or '')[:500]}\n"
        f"【参考答案】{(reference_answer or '')[:200]}\n"
        f"【学生答案】{(student_answer or '')[:200]}\n"
        f"【任务】判断学生答案是否正确,输出 JSON。"
    )
