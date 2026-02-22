from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str
    openai_api_key: str

    editor_model: str = "gpt-4o"
    fast_model: str = "gpt-4o-mini"
    whisper_model: str = "whisper-1"

    database_url: str = "postgresql+asyncpg://memoir:memoir@localhost:5432/memoir_bot"

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

    # Admin (your Telegram ID for /admin commands)
    admin_telegram_id: int = 0

    # Premium duration in days
    premium_days: int = 90

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
