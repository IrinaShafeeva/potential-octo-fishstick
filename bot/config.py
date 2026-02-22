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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
