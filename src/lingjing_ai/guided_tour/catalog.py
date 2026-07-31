from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
from typing import Any


EXPECTED_CLASSIC_STOPS = (
    "九龙灌浴",
    "天下第一掌",
    "祥符禅寺",
    "灵山大佛",
    "灵山梵宫",
    "五印坛城",
)
LOCAL_AUDIO_PREFIX = "/digital-human/narration/xiaoxiao/"


class GuidedTourCatalog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self._route = _validate_route(payload)
        self._stops = {stop["stop_id"]: stop for stop in self._route["stops"]}

    def get_classic_route(self) -> dict[str, Any]:
        return deepcopy(self._route)

    def get_stop(self, stop_id: str) -> dict[str, Any] | None:
        stop = self._stops.get(str(stop_id or "").strip())
        return deepcopy(stop) if stop is not None else None


def _validate_route(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("guided tour catalog must be an object")
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported schema_version")
    if not str(payload.get("route_id", "")).strip():
        raise ValueError("route_id is required")
    if not str(payload.get("name", "")).strip():
        raise ValueError("route name is required")
    speed = _finite_number(payload.get("default_speed_mps"), "default_speed_mps")
    if speed <= 0 or speed > 100:
        raise ValueError("default_speed_mps is out of range")
    polyline = payload.get("polyline")
    if not isinstance(polyline, list) or len(polyline) < 2:
        raise ValueError("polyline must contain at least two points")
    for point in polyline:
        _parse_point(point, "polyline")

    stops = payload.get("stops")
    if not isinstance(stops, list) or len(stops) != len(EXPECTED_CLASSIC_STOPS):
        raise ValueError("classic route must contain six stops")
    normalized_stops = [_validate_stop(stop) for stop in stops]
    stop_ids = [stop["stop_id"] for stop in normalized_stops]
    if len(set(stop_ids)) != len(stop_ids):
        raise ValueError("stop_id values must be unique")
    names = tuple(stop["attraction_name"] for stop in normalized_stops)
    if names != EXPECTED_CLASSIC_STOPS:
        raise ValueError("classic stop order does not match the approved route")
    return {
        **payload,
        "route_id": str(payload["route_id"]).strip(),
        "name": str(payload["name"]).strip(),
        "default_speed_mps": speed,
        "polyline": list(polyline),
        "stops": normalized_stops,
    }


def _validate_stop(stop: Any) -> dict[str, Any]:
    if not isinstance(stop, dict):
        raise ValueError("each stop must be an object")
    stop_id = str(stop.get("stop_id", "")).strip()
    if not stop_id:
        raise ValueError("stop_id is required")
    attraction_name = str(stop.get("attraction_name", "")).strip()
    if not attraction_name:
        raise ValueError("attraction_name is required")
    longitude = _finite_number(stop.get("longitude"), "coordinate longitude")
    latitude = _finite_number(stop.get("latitude"), "coordinate latitude")
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise ValueError("coordinate is out of range")
    trigger_radius = _finite_number(stop.get("trigger_radius_m"), "trigger_radius_m")
    if trigger_radius <= 0 or trigger_radius > 200:
        raise ValueError("trigger_radius_m is out of range")
    dwell_ms = _finite_number(stop.get("dwell_ms"), "dwell_ms")
    if dwell_ms < 0 or dwell_ms > 60000:
        raise ValueError("dwell_ms is out of range")
    narration = str(stop.get("narration_text", "")).strip()
    if not narration or len(narration) > 1000:
        raise ValueError("narration_text is required and must be concise")
    audio_url = str(stop.get("local_audio_url", "")).strip()
    if (
        not audio_url.startswith(LOCAL_AUDIO_PREFIX)
        or ".." in audio_url
        or not audio_url.lower().endswith(".mp3")
    ):
        raise ValueError("local_audio_url must be a safe Xiaoxiao MP3 path")
    focus_zoom = _finite_number(stop.get("focus_zoom", 18), "focus_zoom")
    if focus_zoom < 3 or focus_zoom > 20:
        raise ValueError("focus_zoom is out of range")
    return {
        **stop,
        "stop_id": stop_id,
        "attraction_name": attraction_name,
        "longitude": longitude,
        "latitude": latitude,
        "trigger_radius_m": trigger_radius,
        "dwell_ms": dwell_ms,
        "narration_text": narration,
        "local_audio_url": audio_url,
        "focus_zoom": focus_zoom,
    }


def _parse_point(value: Any, field: str) -> tuple[float, float]:
    try:
        longitude, latitude = str(value).split(",", maxsplit=1)
        parsed = (float(longitude), float(latitude))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} contains an invalid point") from error
    if not all(math.isfinite(number) for number in parsed):
        raise ValueError(f"{field} contains a non-finite point")
    if not -180 <= parsed[0] <= 180 or not -90 <= parsed[1] <= 90:
        raise ValueError(f"{field} coordinate is out of range")
    return parsed


def _finite_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric") from error
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number
