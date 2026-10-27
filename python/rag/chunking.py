"""文本分块: 语义分块(按句子聚合 + overlap)。

设计:
- 按 sentence boundary 切分(。.!?!?)
- 聚合到 max_tokens(默认 500)为一块
- 块之间 overlap 句子(默认 1 句)
- token 计数: 优先 tiktoken(若有),否则用 len/4 近似
"""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_SENTENCE_END_RE = re.compile(r"(?<=[。.!?!?])\s+")
_APPROX_RATIO = 4  # 1 token ≈ 4 chars (英文近似)


def count_tokens(text: str) -> int:
    """估算 token 数。

    优先用 tiktoken(cl100k_base);不可用时用字符数/4 近似。
    """
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return max(1, len(text) // _APPROX_RATIO)


def _split_sentences(text: str) -> list[str]:
    """按句子边界切分。保留分隔符在句子末尾。"""
    text = text.strip()
    if not text:
        return []
    # 中英文句末符号后跟空白 -> 切分
    parts = _SENTENCE_END_RE.split(text)
    # 单句过长(>1000 chars)进一步按段落切
    sentences: list[str] = []
    for p in parts:
        if len(p) <= 1000:
            if p.strip():
                sentences.append(p.strip())
            continue
        # 按段落切分
        for para in p.split("\n\n"):
            para = para.strip()
            if para:
                if len(para) > 1000:
                    # 强制按 1000 字符切(极端情况)
                    for i in range(0, len(para), 1000):
                        sentences.append(para[i : i + 1000])
                else:
                    sentences.append(para)
    return sentences


@dataclass
class Chunk:
    """分块结果。"""

    content: str
    chunk_index: int
    token_count: int


def chunk_text(
    text: str,
    max_tokens: int = 500,
    overlap_sentences: int = 1,
) -> list[Chunk]:
    """语义分块。

    Args:
        text: 原始文本
        max_tokens: 每块最大 token 数(默认 500)
        overlap_sentences: 块间重叠句子数(默认 1)

    Returns:
        list[Chunk]: 分块列表(chunk_index 从 0 开始)
    """
    if not text or not text.strip():
        return []

    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks: list[Chunk] = []
    current_sentences: list[str] = []
    current_tokens = 0
    chunk_idx = 0

    for sent in sentences:
        sent_tokens = count_tokens(sent)
        # 单句就超过 max_tokens: 单独成块
        if sent_tokens >= max_tokens:
            # 先把已聚合的写入
            if current_sentences:
                content = " ".join(current_sentences)
                chunks.append(
                    Chunk(
                        content=content,
                        chunk_index=chunk_idx,
                        token_count=current_tokens,
                    )
                )
                chunk_idx += 1
                # overlap: 保留最后 N 句
                if overlap_sentences > 0 and len(current_sentences) >= overlap_sentences:
                    current_sentences = current_sentences[-overlap_sentences:]
                    current_tokens = sum(count_tokens(s) for s in current_sentences)
                else:
                    current_sentences = []
                    current_tokens = 0
            # 单独成块
            chunks.append(
                Chunk(
                    content=sent,
                    chunk_index=chunk_idx,
                    token_count=sent_tokens,
                )
            )
            chunk_idx += 1
            continue

        if current_tokens + sent_tokens > max_tokens:
            # 写入当前块
            content = " ".join(current_sentences)
            chunks.append(
                Chunk(
                    content=content,
                    chunk_index=chunk_idx,
                    token_count=current_tokens,
                )
            )
            chunk_idx += 1
            # overlap
            if overlap_sentences > 0 and len(current_sentences) >= overlap_sentences:
                current_sentences = current_sentences[-overlap_sentences:]
                current_tokens = sum(count_tokens(s) for s in current_sentences)
            else:
                current_sentences = []
                current_tokens = 0

        current_sentences.append(sent)
        current_tokens += sent_tokens

    # 写入剩余
    if current_sentences:
        content = " ".join(current_sentences)
        chunks.append(
            Chunk(
                content=content,
                chunk_index=chunk_idx,
                token_count=current_tokens,
            )
        )

    logger.debug("chunked: %d sentences -> %d chunks", len(sentences), len(chunks))
    return chunks
