from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # LLM
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    claude_model: str = "claude-sonnet-4-6"
    claude_haiku_model: str = "claude-haiku-4-5-20251001"

    # Database (SQLite for MVP, PostgreSQL for V1)
    database_url: str = "sqlite+aiosqlite:///./immo2.db"

    # Geocoding
    nominatim_user_agent: str = "immo2/0.1 (contact@immo2.de)"
    here_api_key: str = ""  # optional fallback

    # Feature flags (all off in MVP)
    enable_photo_analysis: bool = False   # restb.ai — enable when contracted
    enable_location_api: bool = False     # Overpass — enable when H3 cache built
    enable_rent_ml: bool = False          # XGBoost — enable when training data secured
    enable_playwright: bool = True        # single-URL render, user-triggered

    # Optional API keys (V1)
    restb_api_key: str = ""
    empirica_api_key: str = ""
    here_api_key_v2: str = ""

    # Report settings
    report_retention_days: int = 90       # GDPR: auto-delete after this many days
    max_pdf_size_mb: int = 50

    # Cashflow defaults (user can override)
    default_eigenkapital_pct: float = 20.0
    default_finanzierungszins: float = 3.5
    default_tilgung_pct: float = 2.0
    default_grundanteil_pct: float = 25.0   # Gebäudeanteil = 100 - this
    default_hausgeld_deductible_pct: float = 65.0
    default_makler_pct: float = 3.57        # buyer side for investment properties
    default_notar_grundbuch_pct: float = 1.7
    default_verwaltung_monthly: float = 0.0


settings = Settings()
