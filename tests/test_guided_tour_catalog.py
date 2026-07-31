from __future__ import annotations

import json
from pathlib import Path

import pytest

from lingjing_ai.guided_tour.catalog import GuidedTourCatalog


EXPECTED_STOPS = [
    "九龙灌浴",
    "天下第一掌",
    "祥符禅寺",
    "灵山大佛",
    "灵山梵宫",
    "五印坛城",
]


def route_payload() -> dict:
    return {
        "schema_version": 1,
        "route_id": "lingshan-classic-v1",
        "name": "灵山胜境经典文化线",
        "default_speed_mps": 8,
        "polyline": ["120.1,31.4", "120.2,31.5"],
        "stops": [
            {
                "stop_id": f"stop-{index}",
                "attraction_name": name,
                "longitude": 120.1 + index * 0.001,
                "latitude": 31.4 + index * 0.001,
                "trigger_radius_m": 35,
                "dwell_ms": 3000,
                "narration_text": f"{name}的固定讲解词。",
                "local_audio_url": f"/digital-human/narration/xiaoxiao/stop-{index}.mp3",
                "focus_zoom": 18,
            }
            for index, name in enumerate(EXPECTED_STOPS, start=1)
        ],
    }


def write_catalog(path: Path, payload: dict | None = None) -> Path:
    path.write_text(json.dumps(payload or route_payload(), ensure_ascii=False), encoding="utf-8")
    return path


def test_catalog_loads_a_defensive_copy_of_the_classic_route(tmp_path: Path):
    catalog = GuidedTourCatalog(write_catalog(tmp_path / "guided-tour.json"))

    route = catalog.get_classic_route()
    assert route["route_id"] == "lingshan-classic-v1"
    assert [stop["attraction_name"] for stop in route["stops"]] == EXPECTED_STOPS
    assert catalog.get_stop("stop-1")["attraction_name"] == "九龙灌浴"
    assert catalog.get_stop("missing") is None

    route["stops"][0]["attraction_name"] = "被篡改"
    assert catalog.get_stop("stop-1")["attraction_name"] == "九龙灌浴"


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda data: data.update(schema_version=2), "schema_version"),
        (lambda data: data.update(polyline=["bad"]), "polyline"),
        (lambda data: data["stops"].__setitem__(1, data["stops"][0]), "stop_id"),
        (lambda data: data["stops"][0].update(longitude=181), "coordinate"),
        (lambda data: data["stops"][0].update(trigger_radius_m=0), "trigger_radius_m"),
        (lambda data: data["stops"][0].update(dwell_ms=-1), "dwell_ms"),
        (lambda data: data["stops"][0].update(narration_text=""), "narration_text"),
        (
            lambda data: data["stops"][0].update(local_audio_url="https://bad.example/a.mp3"),
            "local_audio_url",
        ),
    ],
)
def test_catalog_rejects_invalid_or_unsafe_configuration(tmp_path: Path, mutate, message: str):
    payload = route_payload()
    mutate(payload)
    path = write_catalog(tmp_path / "invalid.json", payload)
    with pytest.raises(ValueError, match=message):
        GuidedTourCatalog(path)
