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
    upload_practice_pose_model: str = "yolo11n-pose.pt"
    upload_practice_whisper_model: str = "whisper-large-v3-turbo"
    upload_practice_sensitive_terms: str = ""
    upload_practice_max_evidence_frames: int = 12
    live_target_fps: float = 15.0
    live_front_facing_low: float = 0.60
    live_front_facing_high: float = 0.70
    live_front_facing_window_seconds: float = 10.0
    live_front_facing_yaw_threshold: float = 0.16
    live_thinking_grace_seconds: float = 2.0
    live_gaze_calibration_frames: int = 15
    live_gaze_calibration_horizontal_spread: float = 0.08
    live_gaze_calibration_vertical_spread: float = 0.10
    live_gaze_horizontal_threshold: float = 0.08
    live_gaze_vertical_threshold: float = 0.10
    live_gaze_smoothing_frames: int = 5
    live_landmark_loss_grace_seconds: float = 0.8
    live_head_yaw_threshold: float = 0.22
    live_head_yaw_recovery_threshold: float = 0.14
    live_head_yaw_grace_seconds: float = 0.75
    live_event_recovery_seconds: float = 0.75
    live_max_session_events: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
