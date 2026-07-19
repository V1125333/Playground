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
    openai_summary_model: str = Field(default="gpt-5.5", alias="OPENAI_SUMMARY_MODEL")
    openai_summary_max_output_tokens: int = Field(default=500, alias="OPENAI_SUMMARY_MAX_OUTPUT_TOKENS")
    openai_summary_timeout_seconds: int = Field(default=30, alias="OPENAI_SUMMARY_TIMEOUT_SECONDS")
    ai_summary_generation_enabled: bool = Field(default=False, alias="AI_SUMMARY_GENERATION_ENABLED")
    ai_experience_generation_enabled: bool = Field(default=True, alias="AI_EXPERIENCE_GENERATION_ENABLED")
    openai_experience_model: str = Field(default="gpt-5.5", alias="OPENAI_EXPERIENCE_MODEL")
    openai_experience_max_output_tokens: int = Field(default=1500, alias="OPENAI_EXPERIENCE_MAX_OUTPUT_TOKENS")
    openai_experience_timeout_seconds: int = Field(default=45, alias="OPENAI_EXPERIENCE_TIMEOUT_SECONDS")
    experience_writer_prompt_version: str = Field(default="experience-writer-v1", alias="EXPERIENCE_WRITER_PROMPT_VERSION")
    ai_experience_max_role_calls: int = Field(default=6, alias="AI_EXPERIENCE_MAX_ROLE_CALLS")
    ai_experience_concurrency: int = Field(default=2, alias="AI_EXPERIENCE_CONCURRENCY")
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
