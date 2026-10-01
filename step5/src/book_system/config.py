from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseSettings):
    DATABASE_URL: str
    model_config = SettingsConfigDict(
        env_file = BASE_DIR / ".env",
        extra = "ignore"
    )

Config = Settings()

if __name__ == "__main__":
    print(BASE_DIR)