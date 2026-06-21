import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

try:
    import streamlit as st

    for key, value in st.secrets.items():
        os.environ.setdefault(key, str(value))
except Exception:
    pass


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    serper_api_key: str
    fmp_api_key: str
    db_path: str
    research_model: str
    turso_database_url: str
    turso_auth_token: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        serper_api_key=os.environ.get("SERPER_API_KEY", ""),
        fmp_api_key=os.environ.get("FMP_API_KEY", ""),
        db_path=os.environ.get("DB_PATH", "./data/politicianstockai.db"),
        research_model=os.environ.get("RESEARCH_MODEL", "openai-chat:gpt-4o"),
        turso_database_url=os.environ.get("TURSO_DATABASE_URL", ""),
        turso_auth_token=os.environ.get("TURSO_AUTH_TOKEN", ""),
    )
