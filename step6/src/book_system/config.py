from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"

    # 后面的文件优先级更高：src/.env 会覆盖 book_system/.env
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", BASE_DIR.parent / ".env"),
        extra="ignore",
    )


Config = Settings()

if __name__ == "__main__":
    print(BASE_DIR)
