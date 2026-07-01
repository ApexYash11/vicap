from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    fireworks_api_key: str = Field(default="", alias="FIREWORKS_API_KEY")
    fireworks_base_url: str = Field(
        default="https://api.fireworks.ai/inference/v1",
        alias="FIREWORKS_BASE_URL",
    )
    kimi_model: str = Field(default="accounts/fireworks/models/kimi-k2p5", alias="KIMI_MODEL")
    minimax_model: str = Field(
        default="accounts/fireworks/models/minimax-m2p7", alias="MINIMAX_MODEL"
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    data_dir: Path = Field(default=ROOT / "data", alias="VICAP_DATA_DIR")
    output_dir: Path = Field(default=ROOT / "outputs", alias="VICAP_OUTPUT_DIR")
    chunk_duration_sec: float = Field(default=3.0, alias="CHUNK_DURATION_SEC")
    chunk_overlap_sec: float = Field(default=1.0, alias="CHUNK_OVERLAP_SEC")
    motion_gate_threshold: float = Field(default=0.08, alias="MOTION_GATE_THRESHOLD")
    summary_interval_sec: int = Field(default=30, alias="SUMMARY_INTERVAL_SEC")

    @property
    def clips_dir(self) -> Path:
        return self.data_dir / "clips"

    @property
    def has_api_key(self) -> bool:
        return bool(self.fireworks_api_key and self.fireworks_api_key != "your_fireworks_api_key")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_yaml(name: str) -> dict:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_styles() -> dict:
    return load_yaml("styles.yaml").get("styles", {})


def load_models_config() -> dict:
    return load_yaml("models.yaml")
