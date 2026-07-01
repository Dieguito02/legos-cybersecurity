from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # Auth
    app_username: str = os.getenv("APP_USERNAME", "admin")
    app_password: str = os.getenv("APP_PASSWORD", "admin")
    secret_key: str = os.getenv("SECRET_KEY", "change-me")
    session_cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "legos_session")
    session_max_age_seconds: int = int(os.getenv("SESSION_MAX_AGE_SECONDS", "43200"))

    # Network validation
    wifi_ssid: str = os.getenv("WIFI_SSID", "")
    wifi_password: str = os.getenv("WIFI_PASSWORD", "")

    # OT targets
    broker: str = os.getenv("BROKER", "192.168.0.10")
    broker_port: int = int(os.getenv("BROKER_PORT", "1883"))
    plc_endpoint: str = os.getenv("PLC_ENDPOINT", "opc.tcp://192.168.0.1:4840")

    # Server
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "0"))


settings = Settings()
