import uuid
import time
from config import CONFIG

# token -> (filepath, expiry_timestamp)
_file_tokens: dict[str, tuple[str, float]] = {}

# FIX 8: hard cap to prevent unbounded growth under heavy load.
MAX_TOKEN_STORE_SIZE = 500
_EVICTION_BATCH = 50
TOKEN_TTL_SECONDS = 3600  # 1 hour (was 24 hours)


def _evict_oldest(n: int = _EVICTION_BATCH) -> None:
    """Remove the `n` soonest-to-expire tokens from the store."""
    sorted_keys = sorted(_file_tokens, key=lambda k: _file_tokens[k][1])
    for key in sorted_keys[:n]:
        del _file_tokens[key]


def generate_file_token(filepath: str) -> str:
    """
    Generate a 1-hour download token for a file.

    Returns the full authenticated download URL that the user can click.
    The token stays valid for re-downloads within the 1-hour window.
    If the token store is at capacity, the 50 oldest entries are evicted first.
    """
    if len(_file_tokens) >= MAX_TOKEN_STORE_SIZE:
        _evict_oldest(_EVICTION_BATCH)

    token = str(uuid.uuid4())
    expiry = time.time() + TOKEN_TTL_SECONDS
    _file_tokens[token] = (filepath, expiry)
    base_url = CONFIG.get("BASE_URL", "http://localhost:8080").rstrip("/")
    return f"{base_url}/downloads?token={token}"
