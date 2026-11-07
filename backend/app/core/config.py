from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from the environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    frontend_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"
    database_url: str | None = None
    auth0_domain: str | None = None
    auth0_audience: str | None = None
    openrouter_api_key: str | None = None
    groq_api_key: str | None = None
    storage_root: str = "data"
    upload_practice_max_bytes: int = 500 * 1024 * 1024
    upload_practice_sample_fps: float = 5.0
    # Zero chooses up to four threads, leaving one logical CPU for other work.
    upload_practice_cpu_threads: int = 0
    slide_vision_workers: int = 4
    slide_analysis_workers: int = 5
    slide_analysis_batch_size: int = 3
    transcript_generation_workers: int = 4
    upload_practice_pose_model: str = "yolo11n-pose.pt"
    upload_practice_whisper_model: str = "whisper-large-v3-turbo"
    upload_practice_sensitive_terms: str = ""
    upload_practice_max_evidence_frames: int = 12
    live_target_fps: float = 15.0
    live_calibration_frames: int = 15
    live_max_session_events: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
