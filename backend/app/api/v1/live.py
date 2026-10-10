"""Authenticated WebSocket delivery coaching with no live-frame persistence."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.core.auth import Auth0Principal, get_auth0_principal
from app.core.config import get_settings
from app.services.live_coaching import DebugBounds, FrameObservation, LiveCoachingTracker

router = APIRouter(prefix="/api/v1/live", tags=["live-practice"])
logger = logging.getLogger(__name__)


async def _reject_websocket(websocket: WebSocket, code: str, message: str, close_code: int) -> None:
    await websocket.send_json({"type": "error", "code": code, "message": message})
    await websocket.close(code=close_code)


def _authenticate_websocket_message(payload: Any) -> Auth0Principal | None:
    if not isinstance(payload, dict) or payload.get("type") != "authenticate":
        return None
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        return None
    return get_auth0_principal(token, get_settings())


def _normalized_pair(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    if not all(isinstance(item, (int, float)) and 0 <= item <= 1 for item in value):
        return None
    return float(value[0]), float(value[1])


def _debug_bounds(value: Any) -> DebugBounds | None:
    if not isinstance(value, dict):
        return None
    fields = ("x", "y", "width", "height")
    if not all(isinstance(value.get(field), (int, float)) for field in fields):
        return None
    x, y, width, height = (float(value[field]) for field in fields)
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
        return None
    return DebugBounds(x=x, y=y, width=width, height=height)


def _client_observation(message: Any) -> FrameObservation | None:
    if not isinstance(message, dict) or message.get("type") != "observation":
        return None
    person_detected = message.get("person_detected")
    if not isinstance(person_detected, bool):
        return None
    if not person_detected:
        return FrameObservation(person_detected=False)
    left_gaze_position = _normalized_pair(message.get("left_gaze_position"))
    right_gaze_position = _normalized_pair(message.get("right_gaze_position"))
    head_yaw = message.get("head_yaw")
    if not isinstance(head_yaw, (int, float)) or abs(head_yaw) > 2:
        head_yaw = None
    debug_payload = message.get("debug")
    debug: dict[str, dict[str, float]] = {}
    if isinstance(debug_payload, dict):
        for source, target in (
            ("face", "face"),
            ("left_eye", "left_eye"),
            ("right_eye", "right_eye"),
        ):
            bounds = _debug_bounds(debug_payload.get(source))
            if bounds is not None:
                debug[target] = bounds.as_message()
    return FrameObservation(
        person_detected=True,
        left_gaze_position=left_gaze_position,
        right_gaze_position=right_gaze_position,
        head_yaw=float(head_yaw) if head_yaw is not None else None,
        debug=debug or None,
    )


@router.websocket("/stream")
async def stream_live_feedback(websocket: WebSocket) -> None:
    """Receive browser-derived numerical iris observations after Auth0 authentication."""

    await websocket.accept()
    try:
        auth_payload = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        principal = _authenticate_websocket_message(auth_payload)
    except TimeoutError:
        await _reject_websocket(websocket, "LIVE_AUTH_TIMEOUT", "Authentication timed out.", 4401)
        return
    except HTTPException:
        await _reject_websocket(websocket, "LIVE_AUTH_FAILED", "Authentication failed.", 4401)
        return
    except Exception:
        await _reject_websocket(websocket, "LIVE_AUTH_FAILED", "Authentication failed.", 4401)
        return

    if principal is None:
        await _reject_websocket(
            websocket, "LIVE_AUTH_REQUIRED", "Authentication is required.", 4401
        )
        return

    tracker = LiveCoachingTracker()
    paused = False
    last_sequence = -1
    await websocket.send_json({"type": "ready", "target_fps": get_settings().live_target_fps})
    try:
        while True:
            incoming = await websocket.receive()
            if incoming.get("type") == "websocket.disconnect":
                break
            if incoming.get("text") is not None:
                try:
                    payload = incoming["text"]
                    import json

                    message = json.loads(payload)
                except (TypeError, ValueError):
                    await websocket.send_json(
                        {
                            "type": "warning",
                            "code": "LIVE_INVALID_MESSAGE",
                            "message": "Invalid message.",
                        }
                    )
                    continue
                message_type = message.get("type") if isinstance(message, dict) else None
                if message_type == "observation":
                    if paused:
                        await websocket.send_json(
                            {
                                "type": "warning",
                                "code": "LIVE_SESSION_PAUSED",
                                "message": "Resume the session before sending observations.",
                            }
                        )
                        continue
                    sequence = message.get("sequence")
                    timestamp_ms = message.get("timestamp_ms")
                    if not isinstance(sequence, int) or not isinstance(timestamp_ms, int):
                        await websocket.send_json(
                            {
                                "type": "warning",
                                "code": "LIVE_INVALID_OBSERVATION",
                                "message": "Invalid eye-tracking observation metadata.",
                            }
                        )
                        continue
                    if sequence <= last_sequence:
                        await websocket.send_json(
                            {
                                "type": "warning",
                                "code": "LIVE_STALE_OBSERVATION",
                                "message": "An out-of-order observation was ignored.",
                            }
                        )
                        continue
                    observation = _client_observation(message)
                    if observation is None:
                        await websocket.send_json(
                            {
                                "type": "warning",
                                "code": "LIVE_INVALID_OBSERVATION",
                                "message": "Invalid eye-tracking observation.",
                            }
                        )
                        continue
                    last_sequence = sequence
                    started = time.perf_counter()
                    server_timestamp_ms = round(time.monotonic() * 1000)
                    feedback = tracker.process(
                        observation,
                        sequence,
                        server_timestamp_ms,
                        round((time.perf_counter() - started) * 1000),
                    )
                    await websocket.send_json(feedback.as_message())
                elif message_type == "pause":
                    paused = True
                    events = tracker.pause(round(time.monotonic() * 1000))
                    await websocket.send_json({"type": "paused", "session_events": events})
                elif message_type == "resume":
                    paused = False
                    await websocket.send_json({"type": "resumed"})
                elif message_type == "recalibrate":
                    timestamp_ms = message.get("timestamp_ms")
                    if not isinstance(timestamp_ms, int):
                        await websocket.send_json(
                            {
                                "type": "warning",
                                "code": "LIVE_INVALID_RECALIBRATION",
                                "message": "Invalid recalibration request.",
                            }
                        )
                        continue
                    tracker.recalibrate_gaze(round(time.monotonic() * 1000))
                    await websocket.send_json(
                        {
                            "type": "recalibrating",
                            "calibration_required": get_settings().live_gaze_calibration_frames,
                            "message": (
                                "Look at the camera marker while eye contact is recalibrated."
                            ),
                        }
                    )
                elif message_type == "end":
                    break
                continue

            if incoming.get("bytes") is not None and not paused:
                await websocket.send_json(
                    {
                        "type": "warning",
                        "code": "LIVE_UNEXPECTED_FRAME",
                        "message": (
                            "Camera frames are analysed in the browser and are not uploaded."
                        ),
                    }
                )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Live coaching connection failed")
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "LIVE_CONNECTION_FAILED",
                    "message": "Live coaching stopped.",
                }
            )
        except RuntimeError:
            pass
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass
