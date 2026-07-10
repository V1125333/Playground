from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.5", alias="OPENAI_MODEL")
    ai_model_job_intelligence: str = Field(default="gpt-5.5", alias="AI_MODEL_JOB_INTELLIGENCE")
    ai_model_semantic_mapping: str = Field(default="gpt-5.5", alias="AI_MODEL_SEMANTIC_MAPPING")
    ai_model_resume_strategy: str = Field(default="gpt-5.5", alias="AI_MODEL_RESUME_STRATEGY")
    ai_model_resume_generation: str = Field(default="gpt-5.5", alias="AI_MODEL_RESUME_GENERATION")
    ai_model_ats_validation: str = Field(default="gpt-5.5-mini", alias="AI_MODEL_ATS_VALIDATION")
    ai_model_formatting: str = Field(default="gpt-5.5-mini", alias="AI_MODEL_FORMATTING")
    ai_pricing_json: str = Field(default="", alias="AI_PRICING_JSON")
    ai_usage_db_path: str = Field(default="backend/data/ai_usage.sqlite3", alias="AI_USAGE_DB_PATH")
    database_url: str = Field(
        default="postgresql+asyncpg://resumely:resumely_dev_password@localhost:5432/resumely",
        alias="DATABASE_URL",
    )
    jwt_secret: str = Field(default="change-me-before-production", alias="JWT_SECRET")
    frontend_url: str = Field(default="http://127.0.0.1:5173", alias="FRONTEND_URL")

    @property
    def alembic_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "")

    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", Path(".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
