"""
weather_alert_agent.py — Heat safety alert agent for outdoor work crews.

Fetches current conditions from three weather sources (NWS, Open-Meteo,
OpenWeatherMap), averages them, classifies heat risk using OSHA thresholds,
then uses Claude to generate a natural-language alert with specific supply
and scheduling recommendations for safety managers.

Usage:
    python weather_alert_agent.py --lat 30.26 --lon -97.74 --channel stdout
    python weather_alert_agent.py --lat 30.26 --lon -97.74 --channel email
    python weather_alert_agent.py --lat 30.26 --lon -97.74 --channel slack

Environment variables (set in .env or export directly):
    ANTHROPIC_API_KEY          Required for alert generation
    OPENWEATHERMAP_API_KEY     Optional; skipped if absent
    SMTP_USER                  Gmail address (e.g. you@gmail.com)
    SMTP_PASS                  Gmail App Password (16-char, 2FA must be on)
    ALERT_TO                   Recipient email(s), comma-separated
    SLACK_WEBHOOK_URL          Slack incoming webhook URL
"""

import argparse
import json
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage

import anthropic
import requests
from dotenv import load_dotenv

import mcp_server

load_dotenv()

SYSTEM_PROMPT = """You are a workplace heat safety advisor. You help safety managers
protect outdoor work crews from heat illness.

OSHA heat index risk levels:
- Low       (<91°F):   Normal precautions
- Moderate  (91-103°F): Extra water every 15 min, self-monitoring
- High      (103-115°F): Electrolytes each hour, 10-min rest per hour, buddy system
- Very High (115-130°F): Stop all non-essential outdoor work
- Extreme   (>130°F):  Stop all outdoor work immediately

When given conditions and a risk level, produce a structured safety alert with these sections:
## Summary
## Risk Level
## Required Actions (bulleted)
## Supplies to Order (bulleted, with quantities if possible)
## Work Schedule Adjustments

Be specific and actionable. Include electrolytes, water, cooling towels, misting fans,
shade structures, and sunscreen as appropriate to the risk level."""


# ---------------------------------------------------------------------------
# Source fetchers — each returns a normalized dict or None on failure
# ---------------------------------------------------------------------------

def fetch_nws(lat: float, lon: float) -> dict | None:
    """Fetch current conditions from the NWS REST API (no key required, US only)."""
    try:
        points_raw = mcp_server.fetch_json(
            f"https://api.weather.gov/points/{lat},{lon}",
            headers={"User-Agent": "WeatherAlertAgent/1.0 (safety-tool)"},
        )
        forecast_url = json.loads(points_raw)["data"]["properties"]["forecastHourly"]

        forecast_raw = mcp_server.fetch_json(
            forecast_url,
            headers={"User-Agent": "WeatherAlertAgent/1.0 (safety-tool)"},
        )
        period = json.loads(forecast_raw)["data"]["properties"]["periods"][0]
        temp_f = float(period["temperature"])
        return {
            "temp_f": temp_f,
            "apparent_temp_f": temp_f,  # NWS hourly doesn't include feels-like
            "conditions": period.get("shortForecast", ""),
            "source": "nws",
        }
    except Exception as e:
        print(f"  [NWS] unavailable: {e}")
        return None


def fetch_open_meteo(lat: float, lon: float) -> dict | None:
    """Fetch current conditions from Open-Meteo (no key required, global)."""
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,apparent_temperature"
            f"&temperature_unit=fahrenheit&forecast_days=1"
        )
        raw = mcp_server.fetch_json(url)
        data = json.loads(raw)["data"]
        return {
            "temp_f": float(data["hourly"]["temperature_2m"][0]),
            "apparent_temp_f": float(data["hourly"]["apparent_temperature"][0]),
            "conditions": "",
            "source": "open_meteo",
        }
    except Exception as e:
        print(f"  [Open-Meteo] unavailable: {e}")
        return None


def fetch_openweathermap(lat: float, lon: float, api_key: str) -> dict | None:
    """Fetch current conditions from OpenWeatherMap (free API key required, global)."""
    try:
        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?lat={lat}&lon={lon}&units=imperial&appid={api_key}"
        )
        raw = mcp_server.fetch_json(url)
        data = json.loads(raw)["data"]
        return {
            "temp_f": float(data["main"]["temp"]),
            "apparent_temp_f": float(data["main"]["feels_like"]),
            "conditions": data.get("weather", [{}])[0].get("description", ""),
            "source": "owm",
        }
    except Exception as e:
        print(f"  [OpenWeatherMap] unavailable: {type(e).__name__}")
        return None


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def average_conditions(readings: list[dict]) -> dict:
    """Average temp and apparent temp across all valid readings."""
    valid = [r for r in readings if r is not None]
    if not valid:
        raise RuntimeError("All weather sources failed — cannot produce an alert.")

    avg_temp = sum(r["temp_f"] for r in valid) / len(valid)
    avg_apparent = sum(r["apparent_temp_f"] for r in valid) / len(valid)
    conditions = next((r["conditions"] for r in valid if r["conditions"]), "")
    sources = [r["source"] for r in valid]

    return {
        "temp_f": round(avg_temp, 1),
        "apparent_temp_f": round(avg_apparent, 1),
        "conditions": conditions,
        "sources": sources,
        "raw_readings": valid,
    }


# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------

def classify_risk(conditions: dict) -> dict:
    """Apply OSHA heat index thresholds to the averaged apparent temperature."""
    hi = conditions["apparent_temp_f"]
    if hi < 91:
        level, color = "low", "green"
    elif hi < 103:
        level, color = "moderate", "yellow"
    elif hi < 115:
        level, color = "high", "orange"
    elif hi < 130:
        level, color = "very_high", "red"
    else:
        level, color = "extreme", "purple"

    return {"level": level, "color": color, **conditions}


# ---------------------------------------------------------------------------
# Alert generation via Claude
# ---------------------------------------------------------------------------

def generate_alert(risk: dict, lat: float, lon: float) -> str:
    """Call claude-sonnet-4-6 to produce a structured safety alert."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to your .env file or export it before running."
        )

    client = anthropic.Anthropic(api_key=api_key)

    user_prompt = (
        f"Location: {lat}, {lon}\n"
        f"Temperature: {risk['temp_f']}°F\n"
        f"Apparent temperature (heat index): {risk['apparent_temp_f']}°F\n"
        f"Conditions: {risk['conditions'] or 'Not available'}\n"
        f"Risk level: {risk['level'].upper()} ({risk['color']})\n"
        f"Data sources: {', '.join(risk['sources'])}\n\n"
        "Generate a safety alert for the field safety manager."
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    return message.content[0].text


# ---------------------------------------------------------------------------
# Alert delivery
# ---------------------------------------------------------------------------

def send_alert(message: str, risk: dict, lat: float, lon: float, channel: str) -> None:
    """Route the alert to stdout, Gmail, or Slack."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"[HEAT ALERT] {risk['level'].upper()} — {lat},{lon} — {timestamp}"

    if channel == "stdout":
        print("\n" + "=" * 60)
        print(subject)
        print("=" * 60)
        print(message)
        return

    if channel == "email":
        smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.environ.get("SMTP_PORT", "465"))
        smtp_user = os.environ["SMTP_USER"]
        smtp_pass = os.environ["SMTP_PASS"]
        alert_to = [a.strip() for a in os.environ["ALERT_TO"].split(",")]

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = ", ".join(alert_to)
        msg.set_content(message)

        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"Alert emailed to: {', '.join(alert_to)}")
        return

    if channel == "slack":
        webhook_url = os.environ["SLACK_WEBHOOK_URL"]
        payload = {"text": f"*{subject}*\n\n{message}"}
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        print("Alert posted to Slack.")
        return

    raise ValueError(f"Unknown channel: {channel!r}. Use stdout, email, or slack.")


# ---------------------------------------------------------------------------
# Delivery config validation
# ---------------------------------------------------------------------------

def validate_delivery_config(channel: str) -> None:
    """Raise early with a clear message if delivery credentials are missing."""
    if channel == "email":
        missing = [v for v in ("SMTP_USER", "SMTP_PASS", "ALERT_TO") if not os.environ.get(v)]
        if missing:
            raise RuntimeError(
                f"Missing env vars for email delivery: {', '.join(missing)}\n"
                "Set them in .env or export before running."
            )
    elif channel == "slack":
        if not os.environ.get("SLACK_WEBHOOK_URL"):
            raise RuntimeError(
                "SLACK_WEBHOOK_URL is not set.\n"
                "Set it in .env or export before running."
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Heat safety alert agent")
    parser.add_argument("--lat", type=float, required=True, help="Latitude")
    parser.add_argument("--lon", type=float, required=True, help="Longitude")
    parser.add_argument(
        "--channel",
        choices=["stdout", "email", "slack"],
        default="stdout",
        help="Delivery channel (default: stdout)",
    )
    args = parser.parse_args()

    validate_delivery_config(args.channel)

    print(f"Fetching weather for {args.lat}, {args.lon}...")
    owm_key = os.environ.get("OPENWEATHERMAP_API_KEY")

    readings = [
        fetch_nws(args.lat, args.lon),
        fetch_open_meteo(args.lat, args.lon),
        fetch_openweathermap(args.lat, args.lon, owm_key) if owm_key else None,
    ]

    conditions = average_conditions(readings)
    risk = classify_risk(conditions)

    print(
        f"Averaged conditions from {conditions['sources']}:\n"
        f"  Temp: {conditions['temp_f']}°F | "
        f"Apparent: {conditions['apparent_temp_f']}°F | "
        f"Risk: {risk['level'].upper()}"
    )

    print("Generating alert via Claude...")
    alert = generate_alert(risk, args.lat, args.lon)

    send_alert(alert, risk, args.lat, args.lon, args.channel)


if __name__ == "__main__":
    main()
