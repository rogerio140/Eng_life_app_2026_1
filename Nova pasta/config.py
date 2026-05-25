import os

class Config:
    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "raeb449140"
    )

    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:RAEB449140@localhost:5432/esp32_monitoring"
    )