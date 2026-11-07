"""Authenticated WebSocket delivery coaching with no live-frame persistence."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.core.auth import Auth0Principal, get_auth0_principal
from app.core.config import get_settings
from app.services.live_coaching import FrameObservation, LiveCoachingTracker

router = APIRouter(prefix="/api/v1/live", tags=["live-practice"])
logger = logging.getLogger(__name__)


async def _reject_websocket(websocket: WebSocket, code: str, message: str, close_code: int) -> None:
    logger.warning(
        "Live connection rejected code=%s close_code=%s reason=%s", code, close_code, message
    )
    await websocket.send_json({"type": "error", "code": code, "message": message})
    await websocket.close(code=close_code)


def _authenticate_websocket_message(payload: Any) -> Auth0Principal | None:
    if not isinstance(payload, dict) or payload.get("type") != "authenticate":
        return None
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        return None
    return get_auth0_principal(token, get_settings())


def _numbers(value, length, low, high):
    if not isinstance(value, list) or len(value) != length:
        return None
    if not all(
        isinstance(n, (int, float))
        and not isinstance(n, bool)
        and math.isfinite(n)
        and low <= n <= high
        for n in value
    ):
        return None
    return tuple(float(n) for n in value)


def _points(value, count):
    if not isinstance(value, list) or len(value) != count:
        return None
    points = [_numbers(p, 4, -5, 5) for p in value]
    return points if all(p is not None for p in points) else None


def _client_observation(message: Any) -> FrameObservation | None:
    if not isinstance(message, dict) or message.get("type") != "observation":
        return None
    if not isinstance(message.get("person_detected"), bool):
        return None
    targets = message.get("face_targets")
    targets = (
        [_numbers(p, 2, -2, 3) for p in targets]
        if isinstance(targets, list) and len(targets) == 4
        else None
    )
    if targets is not None and any(p is None for p in targets):
        targets = None
    hands = message.get("hands")
    hands = [_points(h, 21) for h in hands] if isinstance(hands, list) and len(hands) <= 2 else None
    if hands is not None and any(h is None for h in hands):
        hands = None
    debug = message.get("debug")
    safe_debug = {}
    if isinstance(debug, dict):
        for name in ("face", "left_eye", "right_eye"):
            bounds = debug.get(name)
            if isinstance(bounds, dict):
                values = _numbers([bounds.get(k) for k in ("x", "y", "width", "height")], 4, 0, 1)
                if values:
                    safe_debug[name] = dict(zip(("x", "y", "width", "height"), values))
    return FrameObservation(
        person_detected=message["person_detected"],
        eyes=_numbers(message.get("eyes"), 4, 0, 1),
        head=_numbers(message.get("head"), 3, -180, 180),
        body=_points(message.get("body"), 33),
        hands=hands,
        body_updated=message.get("body_updated") is True,
        hands_updated=message.get("hands_updated") is True,
        face_targets=targets,
        debug=safe_debug or None,
    )


@router.websocket("/stream")
async def stream_live_feedback(websocket: WebSocket) -> None:
    """Receive browser-derived movement landmarks after Auth0 authentication."""

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
                                "message": "Invalid movement observation metadata.",
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
                                "message": "Invalid movement observation.",
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
                            "calibration_required": get_settings().live_calibration_frames,
                            "message": (
                                "Face forward in a comfortable position and look at the marker."
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
