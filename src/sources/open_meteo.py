"""Parse Open-Meteo forecast API responses into engine events.

Weather-worker/v1 contract (2026-09-23): emit structured JSON Face can verify
without re-pulling. Always include rain_mm (incl. 0.0) and gust_kmh. No ride
verdict — Face owns judgment.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.config.models import HandleConfig
from src.events.models import Event, EventSourceKind

# WMO weather interpretation codes (Open-Meteo / ECMWF).
# https://open-meteo.com/en/docs#weathervariables
WMO_DESCRIPTIONS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

THUNDERSTORM_CODES = frozenset({95, 96, 99})
HEAVY_RAIN_CODES = frozenset({65, 81, 82})
WARSAW_TZ = ZoneInfo("Europe/Warsaw")


def describe_weather_code(code: int | None) -> str:
    """Return a human-readable label for a WMO weather code."""
    if code is None:
        return "Unknown"
    return WMO_DESCRIPTIONS.get(int(code), f"WMO code {code}")


def parse_open_meteo_forecast(
    body: str,
    *,
    entry_point_id: str,
    handle: HandleConfig,
    location_name: str = "Warsaw",
) -> list[tuple[Event, str]]:
    """Turn an Open-Meteo /v1/forecast JSON body into a weather advisory event."""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, dict):
        return []

    hourly = data.get("hourly")
    if isinstance(hourly, dict) and handle.forecast_hours > 0:
        return _parse_hourly_window(data, hourly, entry_point_id=entry_point_id, handle=handle)

    daily = data.get("daily")
    if isinstance(daily, dict):
        return _parse_daily_summary(daily, entry_point_id=entry_point_id, handle=handle)

    return []


def _parse_hourly_window(
    data: dict[str, Any],
    hourly: dict[str, Any],
    *,
    entry_point_id: str,
    handle: HandleConfig,
) -> list[tuple[Event, str]]:
    times = hourly.get("time")
    if not isinstance(times, list) or not times:
        return []

    # URL defines the window (past_hours + forecast_hours); use every returned slot.
    hours = len(times)
    label = handle.location_name or "Warsaw"
    window_start = str(times[0])
    window_end = str(times[hours - 1])
    generated_at = datetime.now(WARSAW_TZ).isoformat(timespec="seconds")

    hour_rows: list[dict[str, Any]] = []
    lines: list[str] = []
    alerts: list[str] = []
    temps: list[float] = []

    for idx in range(hours):
        when = str(times[idx])
        hour_label = when.split("T", 1)[-1] if "T" in when else when
        temp = _series_value(hourly, "temperature_2m", idx)
        code_raw = _series_value(hourly, "weather_code", idx)
        code = int(code_raw) if code_raw is not None else None
        precip_prob = _series_value(hourly, "precipitation_probability", idx)
        precip_mm = _series_value(hourly, "precipitation", idx)
        wind = _series_value(hourly, "wind_speed_10m", idx)
        gust = _series_value(hourly, "wind_gusts_10m", idx)

        if code is not None:
            pass  # alerts below
        if isinstance(temp, (int, float)):
            temps.append(float(temp))

        conditions = describe_weather_code(code)
        # I7: rain_mm ALWAYS present when fetched, including 0.0
        mm_val = float(precip_mm) if precip_mm is not None else None
        row = {
            "time": when,
            "temp_c": float(temp) if temp is not None else 0.0,
            "rain_chance_pct": int(precip_prob) if precip_prob is not None else 0,
            "rain_mm": mm_val if mm_val is not None else 0.0,
            "wind_kmh": float(wind) if wind is not None else 0.0,
            "gust_kmh": float(gust) if gust is not None else 0.0,
            "code": code if code is not None else 0,
            "conditions": conditions,
        }
        hour_rows.append(row)

        prob_bit = f", rain {precip_prob}%" if precip_prob is not None else ""
        mm_bit = f", {row['rain_mm']} mm"
        wind_bit = f", wind {wind} km/h" if wind is not None else ""
        gust_bit = f", gust {gust} km/h" if gust is not None else ""
        lines.append(
            f"  {hour_label}: {temp}°C, {conditions}{prob_bit}{mm_bit}{wind_bit}{gust_bit}"
        )

        if code in THUNDERSTORM_CODES:
            alerts.append(f"  ⚠️ Thunderstorm expected around {hour_label}")
        elif code in HEAVY_RAIN_CODES:
            alerts.append(f"  ⚠️ Heavy rain expected around {hour_label}")
        elif precip_prob is not None and int(precip_prob) >= 80:
            alerts.append(f"  ⚠️ High rain chance ({precip_prob}%) around {hour_label}")

    daily = data.get("daily") if isinstance(data.get("daily"), dict) else {}
    payload = {
        "_contract": "weather-worker/v1 — fill every field, delete nothing, add no prose",
        "_status": "ran",
        "site": label if "," in label else f"{label}, PL",
        "source": "Open-Meteo",
        "generated_at": generated_at,
        "window_start": window_start,
        "window_end": window_end,
        "day_high_c": _series_value(daily, "temperature_2m_max", 0)
        if daily
        else (max(temps) if temps else None),
        "day_low_c": _series_value(daily, "temperature_2m_min", 0)
        if daily
        else (min(temps) if temps else None),
        "sunrise": _series_value(daily, "sunrise", 0) if daily else None,
        "sunset": _series_value(daily, "sunset", 0) if daily else None,
        "hours": hour_rows,
    }

    weather_json = json.dumps(payload, indent=2, ensure_ascii=False)
    alerts_block = "Alerts (facts only):\n" + "\n".join(alerts) + "\n\n" if alerts else ""
    drop_name = f"kanban-report-weather-{window_start[:13].replace('T', '-')}-face.md"

    text = (
        f"[SUBCONSCIOUS] Weather next {hours}h for {label}\n"
        f"Window: {window_start} → {window_end}\n"
        f"status: ran hours={hours}\n\n"
        f"{alerts_block}"
        f"```weather-json\n{weather_json}\n```\n\n"
        f"Hourly (convenience table):\n" + "\n".join(lines) + "\n\n"
        f"Worker: TRANSPORT ONLY — copy the weather-json block verbatim into "
        f"~/vault/COMMS/Inbox/{drop_name} via write-inbox-report.sh. "
        f"Do NOT summarise. Do NOT add a verdict or advice field. "
        f"Face owns judgment. SE will inbox_notify Face. Ack when the file exists.\n"
        f"Source: Open-Meteo (https://open-meteo.com/)"
    )

    dedupe_key = f"open-meteo:{label}:{window_start}"
    priority = handle.default_priority
    if alerts:
        priority = max(priority, 15)

    event = Event(
        text=text,
        event_type=handle.default_event_type,
        source=EventSourceKind.HTTP_POLL,
        entry_point=entry_point_id,
        priority=priority,
        cooldown_key=dedupe_key,
        metadata={
            "handler": "http_poll",
            "response_format": "open_meteo",
            "mode": "hourly",
            "location": label,
            "window_start": window_start,
            "window_end": window_end,
            "forecast_hours": hours,
            "alerts": alerts,
            "contract": "weather-worker/v1",
            "status": "ran",
        },
    )
    return [(event, dedupe_key)]


def _parse_daily_summary(
    daily: dict[str, Any],
    *,
    entry_point_id: str,
    handle: HandleConfig,
) -> list[tuple[Event, str]]:
    times = daily.get("time")
    if not isinstance(times, list) or not times:
        return []

    date = str(times[0])
    temp_max = _series_value(daily, "temperature_2m_max", 0)
    temp_min = _series_value(daily, "temperature_2m_min", 0)
    precip = _series_value(daily, "precipitation_sum", 0)
    weather_code = _series_value(daily, "weather_code", 0)
    conditions = describe_weather_code(
        int(weather_code) if weather_code is not None else None,
    )

    label = handle.location_name or "Warsaw"
    precip_line = f"  Precipitation: {precip} mm\n" if precip is not None else ""
    text = (
        f"[SUBCONSCIOUS] Daily weather forecast for {label} ({date})\n"
        f"status: ran\n\n"
        f"  High: {temp_max}°C\n"
        f"  Low: {temp_min}°C\n"
        f"{precip_line}"
        f"  Conditions: {conditions}\n\n"
        f"Worker: TRANSPORT ONLY — write the numbers above into "
        f"~/vault/COMMS/Inbox/kanban-report-weather-{date}-face.md via write-inbox-report.sh. "
        f"No verdict. SE will inbox_notify Face. Ack when the file exists.\n"
        f"Source: Open-Meteo (https://open-meteo.com/)"
    )

    dedupe_key = f"open-meteo:{label}:{date}"
    event = Event(
        text=text,
        event_type=handle.default_event_type,
        source=EventSourceKind.HTTP_POLL,
        entry_point=entry_point_id,
        priority=handle.default_priority,
        cooldown_key=dedupe_key,
        metadata={
            "handler": "http_poll",
            "response_format": "open_meteo",
            "mode": "daily",
            "location": label,
            "date": date,
            "status": "ran",
        },
    )
    return [(event, dedupe_key)]


def _worse_code(current: int, candidate: int) -> int:
    severity = {95: 100, 96: 99, 99: 98, 65: 80, 82: 85, 81: 75, 63: 60, 61: 50}
    return candidate if severity.get(candidate, 0) > severity.get(current, 0) else current


def _series_value(series: dict[str, Any], key: str, index: int) -> Any:
    values = series.get(key)
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]
