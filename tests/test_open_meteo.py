"""Tests for Open-Meteo poll response parsing."""

from __future__ import annotations

import json

from src.config.models import HandleConfig
from src.events.models import EventSourceKind
from src.sources.open_meteo import describe_weather_code, parse_open_meteo_forecast
from src.sources.rest_poll_parse import parse_poll_body

SAMPLE_WARSAW_HOURLY = {
    "timezone": "Europe/Warsaw",
    "hourly": {
        "time": [
            "2026-06-15T16:00",
            "2026-06-15T17:00",
            "2026-06-15T18:00",
            "2026-06-15T19:00",
            "2026-06-15T20:00",
            "2026-06-15T21:00",
        ],
        "temperature_2m": [16.6, 16.7, 17.3, 16.3, 15.5, 15.1],
        "precipitation_probability": [66, 71, 76, 81, 80, 70],
        "weather_code": [61, 63, 95, 81, 61, 2],
        "precipitation": [0.2, 0.5, 1.0, 2.0, 0.3, 0.0],
        "wind_speed_10m": [12.0, 14.0, 18.0, 22.0, 15.0, 10.0],
    },
}

SAMPLE_WARSAW_DAILY = {
    "daily": {
        "time": ["2026-06-15"],
        "weather_code": [53],
        "temperature_2m_max": [17.3],
        "temperature_2m_min": [11.7],
        "precipitation_sum": [1.80],
    },
}


def test_describe_weather_code() -> None:
    assert describe_weather_code(0) == "Clear sky"
    assert describe_weather_code(53) == "Moderate drizzle"
    assert describe_weather_code(99) == "Thunderstorm with heavy hail"


def test_parse_open_meteo_hourly_warsaw() -> None:
    body = json.dumps(SAMPLE_WARSAW_HOURLY)
    handle = HandleConfig(
        response_format="open_meteo",
        location_name="Warsaw, PL",
        forecast_hours=6,
        default_event_type="weather",
    )
    parsed = parse_open_meteo_forecast(
        body,
        entry_point_id="weather_warsaw",
        handle=handle,
    )
    assert len(parsed) == 1
    event, key = parsed[0]
    assert event.event_type == "weather"
    assert event.source == EventSourceKind.HTTP_POLL
    assert "Weather next 6h" in event.text
    assert "Thunderstorm" in event.text
    assert "Ride/outdoors:" in event.text
    assert event.priority >= 15
    assert key == "open-meteo:Warsaw, PL:2026-06-15T16:00"
    assert event.metadata["mode"] == "hourly"
    assert len(event.metadata["alerts"]) >= 1


def test_parse_open_meteo_daily_fallback() -> None:
    body = json.dumps(SAMPLE_WARSAW_DAILY)
    handle = HandleConfig(
        response_format="open_meteo",
        location_name="Warsaw, PL",
        forecast_hours=0,
        default_event_type="weather",
    )
    parsed = parse_open_meteo_forecast(
        body,
        entry_point_id="weather_warsaw",
        handle=handle,
    )
    assert len(parsed) == 1
    assert "Daily weather forecast" in parsed[0][0].text
    assert parsed[0][1] == "open-meteo:Warsaw, PL:2026-06-15"


def test_parse_poll_body_open_meteo_integration() -> None:
    body = json.dumps(SAMPLE_WARSAW_HOURLY)
    handle = HandleConfig(
        response_format="open_meteo",
        location_name="Warsaw, PL",
        forecast_hours=6,
        default_event_type="weather",
    )
    parsed = parse_poll_body(body, entry_point_id="weather_warsaw", handle=handle)
    assert len(parsed) == 1
    assert parsed[0][0].metadata["forecast_hours"] == 6


def test_parse_open_meteo_invalid_json() -> None:
    handle = HandleConfig(response_format="open_meteo", forecast_hours=6)
    assert parse_open_meteo_forecast("not json", entry_point_id="x", handle=handle) == []
