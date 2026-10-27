"""LLM 接入层: 统一抽象 + 多 Provider + 重试 + 熔断。"""

from llm.provider import LLMProvider, LLMResponse, LLMError, LLMUnavailableError
from llm.openai_provider import OpenAIProvider
from llm.minimax_provider import MiniMaxProvider
from llm.mock_provider import MockLLMProvider
from llm.factory import get_llm_provider
from llm.tutor_service import TutorLLMService, HintLLMService
from llm.question_service import QuestionLLMService, QuestionParseError
from llm.critic_service import CriticLLMService, CritiqueResult, CriticParseError
from llm.debate_service import DebateLLMService, DebateResult, DebateRound
from llm.vision_service import (
    VisionTutorService,
    VisionInputError,
    validate_images,
    validate_data_url,
    validate_http_url,
    MAX_IMAGE_BYTES,
    MAX_IMAGES_PER_REQUEST,
    SUPPORTED_IMAGE_MIME,
)

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "LLMError",
    "LLMUnavailableError",
    "OpenAIProvider",
    "MiniMaxProvider",
    "MockLLMProvider",
    "get_llm_provider",
    "TutorLLMService",
    "HintLLMService",
    "QuestionLLMService",
    "QuestionParseError",
    "CriticLLMService",
    "CritiqueResult",
    "CriticParseError",
    "DebateLLMService",
    "DebateResult",
    "DebateRound",
    "VisionTutorService",
    "VisionInputError",
    "validate_images",
    "validate_data_url",
    "validate_http_url",
    "MAX_IMAGE_BYTES",
    "MAX_IMAGES_PER_REQUEST",
    "SUPPORTED_IMAGE_MIME",
]
