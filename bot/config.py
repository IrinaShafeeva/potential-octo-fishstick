from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str
    openai_api_key: str

    editor_model: str = "gpt-4o"
    fast_model: str = "gpt-4o-mini"
    whisper_model: str = "gpt-4o-transcribe"

    database_url: str = "postgresql+asyncpg://memoir:memoir@localhost:5432/memoir_bot"

    @field_validator("database_url", mode="before")
    @classmethod
    def fix_database_url(cls, v: str) -> str:
        # Render provides postgres:// or postgresql:// — asyncpg needs the +asyncpg dialect
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and "+asyncpg" not in v:
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    free_memories_limit: int = 5
    free_chapters_limit: int = 1
    free_questions_limit: int = 3

    # Tribute payment integration
    tribute_api_key: str = ""
    tribute_webhook_secret: str = ""
    tribute_product_link: str = ""
    tribute_family_product_link: str = ""

    # Webhook server
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080

    # Mini App URL (HTTPS required for production, e.g. https://your-domain.com/miniapp)
    mini_app_url: str = ""

    # Admin (your Telegram ID for /admin commands)
    admin_telegram_id: int = 0

    # Premium duration in days
    premium_days: int = 90

    # API auth (for mobile app)
    jwt_secret: str = "k9V4sQ2mZx8T1rYpWc6L0JdA3uN7eHfG5BqRzXnCw4UoS8tE1KpM6aV2yD9hFjLs"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 168  # 7 days
    google_client_id: str = ""  # for verifying Google idToken
    google_ios_client_id: str = ""  # optional, for iOS

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
