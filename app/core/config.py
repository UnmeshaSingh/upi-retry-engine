from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    APP_NAME: str = "UPI Retry Engine"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    DB_HOST:     str = "localhost"
    DB_PORT:     int = 5432
    DB_NAME:     str = "upi_retry_db"
    DB_USER:     str = "postgres"
    DB_PASSWORD: str = "postgres"

    @property
    def DATABASE_URL(self) -> str:
        db_url = os.environ.get("DATABASE_URL")
        if db_url:
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)
            return db_url
        return (
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    model_config = {"env_file": ".env"}

settings = Settings()