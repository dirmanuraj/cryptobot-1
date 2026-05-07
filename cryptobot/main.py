"""
Entry point. Run with: python main.py

In paper mode (default), no API keys needed.
Dashboard at http://localhost:8080
"""
import logging
import sys

from config import CONFIG
from dashboard.app import run


def setup_logging():
    logging.basicConfig(
        level=getattr(logging, CONFIG.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # quiet noisy deps
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


if __name__ == "__main__":
    setup_logging()
    run()
