from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "UPI Retry Engine"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    model_config = {"env_file": ".env"}

settings = Settings()