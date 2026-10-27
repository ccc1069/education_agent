"""应用配置管理，通过环境变量加载。"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 相对本文件定位 code/python/.env,不依赖进程 cwd
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """全局配置。所有值可通过环境变量覆盖。"""

    # LLM
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"
    # 拍题 Vision 专用模型;空则自动推断(DashScope→qwen-vl-plus, 否则 gpt-4o)
    openai_vision_model: str = ""
    minimax_api_key: str = ""
    minimax_model: str = "MiniMax-M2.7"
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 3

    # Embedding(独立于聊天模型;空字段则回退到 OPENAI_* / 按 base_url 推断)
    # DashScope 兼容模式建议: text-embedding-v3 或 text-embedding-v4
    # OpenAI 官方建议: text-embedding-3-large / text-embedding-3-small
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = ""
    embedding_dimensions: int = 0  # 0=按模型默认推断

    # Database (PostgreSQL + asyncpg)
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/edu_agent"
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT / Auth
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # CORS
    cors_origins: str = "*"

    # Server
    api_port: int = 8000
    log_level: str = "INFO"
    env: str = "dev"  # dev / staging / prod
    debug: bool = False

    # Observability
    otel_exporter_endpoint: str = ""  # 空字符串=禁用 tracing
    enable_tracing: bool = False

    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_redis_url: str = ""  # 空字符串=用内存
    rate_limit_global_per_min: int = 100  # 全局 IP 限流
    rate_limit_login_per_min: int = 5  # 登录端点防爆破
    rate_limit_register_per_min: int = 3  # 注册端点
    rate_limit_refresh_per_min: int = 10  # 刷新 token

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_dev(self) -> bool:
        """开发环境: env=dev 或显式开启 debug。"""
        return self.env == "dev" or self.debug


settings = Settings()
