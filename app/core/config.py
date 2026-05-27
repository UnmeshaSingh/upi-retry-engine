from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "UPI Retry Engine"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    model_config = {"env_file": ".env"}

settings = Settings()