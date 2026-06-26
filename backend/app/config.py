from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    xai_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"
    port: int = 8000
    request_timeout_seconds: int = 25

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
