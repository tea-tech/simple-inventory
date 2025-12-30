"""Application configuration."""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.
    
    Environment variables take precedence over .env file.
    This makes it compatible with Docker (uses env vars) and 
    local development (uses .env file).
    """
    
    APP_NAME: str = "Simple Inventory"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str = "sqlite:///./inventory.db"
    
    # JWT Settings
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    
    model_config = SettingsConfigDict(
        # Only load .env file if it exists (for local dev)
        # Docker will use environment variables directly
        env_file=".env" if Path(".env").exists() else None,
        env_file_encoding="utf-8",
        # Environment variables take precedence over .env file
        extra="ignore",
    )


settings = Settings()
