from pathlib import Path
from uuid import UUID

from fastapi import UploadFile

from app.core.config import get_settings


def storage_root() -> Path:
    root = Path(get_settings().storage_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def storage_path(storage_key: str) -> Path:
    root = storage_root()
    path = (root / storage_key).resolve()
    if root not in path.parents and path != root:
        raise ValueError("Invalid storage key.")
    return path


def presentation_upload_key(user_id: UUID, presentation_id: UUID) -> str:
    return f"presentations/{user_id}/{presentation_id}/source.pptx"


def slide_image_key(user_id: UUID, presentation_id: UUID, slide_number: int) -> str:
    return f"presentations/{user_id}/{presentation_id}/slides/slide_{slide_number}.png"


def agenda_deck_key(user_id: UUID, presentation_id: UUID) -> str:
    return f"presentations/{user_id}/{presentation_id}/agenda-enhanced.pptx"


def upload_practice_source_key(user_id: UUID, session_id: UUID) -> str:
    return f"temporary/upload-practice/{user_id}/{session_id}/source.mp4"


def upload_practice_evidence_key(user_id: UUID, session_id: UUID, index: int) -> str:
    return f"practice-reports/{user_id}/{session_id}/evidence_{index:03d}.jpg"


async def save_limited_upload(
    upload: UploadFile,
    storage_key: str,
    max_bytes: int,
    too_large_message: str,
) -> int:
    destination = storage_path(storage_key)
    destination.parent.mkdir(parents=True, exist_ok=True)
    total_bytes = 0

    try:
        with destination.open("wb") as file_handle:
            while chunk := await upload.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise ValueError(too_large_message)
                file_handle.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return total_bytes


async def save_upload(upload: UploadFile, storage_key: str, max_bytes: int) -> int:
    return await save_limited_upload(
        upload,
        storage_key,
        max_bytes,
        "The presentation is larger than the 30 MB upload limit.",
    )
