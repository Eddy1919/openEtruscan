"""Pydantic Settings configuration management for OpenEtruscan."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """OpenEtruscan application settings.
    
    All settings can be overridden via environment variables.
    Environment variable names are case-insensitive and use the same
    name as the field (e.g., DATABASE_URL for database_url).
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Database
    database_url: str = Field(
        default="sqlite:///data/corpus.db",
        description="Database connection URL",
    )
    
    # API Keys
    gemini_api_key: str | None = Field(
        default=None,
        description="Google Gemini API key for semantic search",
    )
    
    # Directories
    images_dir: str = Field(
        default="data/images",
        description="Directory containing inscription images",
    )
    
    # Environment
    environment: Literal["production", "development", "testing"] = Field(
        default="production",
        description="Application environment",
    )
    
    # Rate Limiting
    rate_limit_per_minute: int = Field(
        default=60,
        ge=1,
        le=10000,
        description="Default rate limit per minute per client",
    )
    
    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )
    
    # Documentation
    enable_docs: bool = Field(
        default=False,
        description="Enable FastAPI documentation endpoints (/docs, /openapi.json)",
    )
    
    @field_validator("database_url", "images_dir")
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Ensure string fields are not empty."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v
    
    @property
    def cors_origins(self) -> list[str]:
        """Compute CORS allowed origins based on environment."""
        production_origins = [
            "https://openetruscan.com",
            "https://www.openetruscan.com",
            "https://open-etruscan.vercel.app",
            "https://open-etruscan-edoardopanichi.vercel.app",
            "https://eddy1919.github.io",
        ]
        
        if self.environment == "production":
            return production_origins
        
        # Development/testing origins include localhost
        return production_origins + [
            "http://localhost",
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
        ]
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"
    
    @property
    def is_testing(self) -> bool:
        """Check if running in testing mode."""
        return self.environment == "testing"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached Settings instance.
    
    This function is cached to ensure the settings are only loaded once
    per process, making it efficient to import and use anywhere.
    """
    return Settings()


# Singleton instance for easy import
settings = get_settings()
