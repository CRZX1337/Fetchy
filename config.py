import os
import logging
import sys
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("MediaBot.Config")

class ConfigLoader:
    _instance = None
    _config = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigLoader, cls).__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        env_channel = os.getenv("CHANNEL_ID")
        if env_channel:
            try:
                self._config["CHANNEL_ID"] = int(env_channel)
            except ValueError:
                logger.error("Environment variable CHANNEL_ID is not a valid integer.")

        if not self._config.get("CHANNEL_ID"):
            logger.critical("CRITICAL: CHANNEL_ID is missing in .env! Shutdown initiated.")
            sys.exit(1)

        self._config["STATUS_ROTATION_SPEED"] = int(os.getenv("STATUS_ROTATION_SPEED", 10))
        self._config["LINK_REGEX"] = os.getenv(
            "LINK_REGEX",
            r'(https?://)?(www\.)?(youtube\.com|youtu\.be|tiktok\.com|twitter\.com|x\.com|instagram\.com)/[^\s]+'
        )
        self._config["BASE_URL"] = os.getenv("BASE_URL", "http://localhost:8080")

    @property
    def config(self):
        return self._config

CONFIG = ConfigLoader().config