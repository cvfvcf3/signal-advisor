"""
main.py
-------
Entry point. Runs the advisor on a timer in a background thread and serves
a read-only dashboard. There is no "mode" flag -- this system only ever
watches and records, it never trades.

Usage:
    python main.py
"""

import logging
import threading
import time

import yaml
from dotenv import load_dotenv

from src.exchange_client import ExchangeClient
from src.journal import Journal
from src.advisor_engine import Advisor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")


def load_config(path="config.yaml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def run_advisor_loop(advisor: Advisor, poll_seconds: int, stop_flag: threading.Event):
    while not stop_flag.is_set():
        try:
            reading = advisor.tick()
            logger.info("Tick complete: %s (confidence %.1f%%)", reading["action"], reading["confidence"])
        except Exception:
            logger.exception("Error during advisor tick")
        time.sleep(poll_seconds)


def main():
    load_dotenv()
    config = load_config()

    exchange = ExchangeClient(config["exchange"])
    journal = Journal()
    advisor = Advisor(config, exchange, journal)

    from dashboard import app as dashboard_app
    dashboard_app.advisor = advisor
    dashboard_app.journal = journal
    dashboard_app.config_data = config

    stop_flag = threading.Event()
    thread = threading.Thread(
        target=run_advisor_loop,
        args=(advisor, config["market"]["poll_interval_seconds"], stop_flag),
        daemon=True,
    )
    thread.start()
    journal.log("Signal advisor started.", "info")

    host = config["dashboard"]["host"]
    port = config["dashboard"]["port"]
    print(f"\nSignal Advisor dashboard running at http://{host}:{port}")
    print("This system is read-only -- it records signals, it never places orders.\n")

    try:
        dashboard_app.app.run(host=host, port=port, debug=False, use_reloader=False)
    finally:
        stop_flag.set()


if __name__ == "__main__":
    main()
