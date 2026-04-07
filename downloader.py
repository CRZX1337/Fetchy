import yt_dlp
import os
import uuid
import logging
import re
import json
import time
import threading
import subprocess
import asyncio
import urllib.request

logger = logging.getLogger("MediaBot.Downloader")

COOKIES_FILE = "/app/cookies.txt"

# Instagram mobile User-Agent that returns full JSON in page HTML
_IG_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Mobile/15E148 Safari/604.1"
)


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

def _load_cookies_dict() -> dict:
    cookies = {}
    if not os.path.exists(COOKIES_FILE):
        return cookies
    try:
        with open(COOKIES_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    domain, _, path, secure, expires, name, value = parts[:7]
                    if "instagram.com" in domain:
                        cookies[name] = value
    except Exception as e:
        logger.warning(f"Could not parse cookies.txt: {e}")
    return cookies


def _cookies_header() -> str:
    c = _load_cookies_dict()
    if not c:
        return ""
    return "; ".join(f"{k}={v}" for k, v in c.items())


# ---------------------------------------------------------------------------
# yt-dlp base options
# ---------------------------------------------------------------------------

def _ydl_opts_base() -> dict:
    opts = {"quiet": True, "no_warnings": True}
    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    return opts


# ---------------------------------------------------------------------------
# General media download (YouTube, TikTok, etc.)
# ---------------------------------------------------------------------------

def get_media_info(url):
    logger.info(f"Extracting info for {url}")
    try:
        with yt_dlp.YoutubeDL(_ydl_opts_base()) as ydl:
            info = ydl.extract_info(url, download=False)
            heights = []
            if "formats" in info:
                for f in info["formats"]:
                    h = f.get("height")
                    if h and f.get("vcodec") != "none":
                        heights.append(h)
            return {
                "title": info.get("title", "Unknown Media"),
                "heights": list(set(heights)),
            }
    except Exception as e:
        logger.warning(f"get_media_info failed for {url}: {e}")
        return None


def download_media(url, format_type, quality="1080", extension="mp3",
                  status_hook=None, cancel_event: threading.Event = None):
    logger.info(f"Downloading {format_type} from {url} (Quality: {quality}, Ext: {extension})")

    current_phase = {"value": "SEARCHING"}
    last_update = {"time": 0}

    def progress_handler(d):
        if status_hook is None:
            return
        now = time.time()
        if d["status"] == "downloading":
            if cancel_event and cancel_event.is_set():
                raise Exception("Download cancelled by user.")
            if now - last_update["time"] < 2.0 and current_phase["value"] == "DOWNLOADING":
                return
            last_update["time"] = now
            current_phase["value"] = "DOWNLOADING"
            downloaded = d.get("downloaded_bytes", 0) or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed = d.get("speed") or 0
            percent = (downloaded / total * 100) if total > 0 else 0
            status_hook({
                "phase": "DOWNLOADING",
                "percent": round(percent, 1),
                "downloaded_mb": round(downloaded / 1024 / 1024, 1),
                "total_mb": round(total / 1024 / 1024, 1),
                "speed_mb": round(speed / 1024 / 1024, 2) if speed else 0,
            })
        elif d["status"] == "finished":
            if cancel_event and cancel_event.is_set():
                raise Exception("Download cancelled by user.")
            if current_phase["value"] != "PROCESSING":
                current_phase["value"] = "PROCESSING"
                status_hook({"phase": "PROCESSING"})

    os.makedirs("downloads", exist_ok=True)
    unique_id = str(uuid.uuid4())[:8]
    output_tpl = f"downloads/%(title)s_{unique_id}.%(ext)s"

    ydl_opts = _ydl_opts_base()
    ydl_opts.update({
        "restrictfilenames": True,
        "outtmpl": output_tpl,
        "progress_hooks": [progress_handler],
    })

    if format_type == "video":
        ydl_opts["format"] = f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]"
        ydl_opts["merge_output_format"] = "mp4"
    elif format_type == "audio":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": extension,
            "preferredquality": "192",
        }]
    elif format_type == "picture":
        ydl_opts["writethumbnail"] = True
        ydl_opts["skip_download"] = True
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegThumbnailsConvertor",
            "format": extension,
        }]

    try:
        if status_hook is not None:
            status_hook({"phase": "SEARCHING"})

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=True)

            requested = result.get("requested_downloads")
            if requested:
                actual_path = requested[0].get("filepath")
                if actual_path and os.path.exists(actual_path):
                    file_size_mb = os.path.getsize(actual_path) / (1024 * 1024)
                    logger.info(f"Download complete (requested_downloads): {actual_path} ({file_size_mb:.2f} MB)")
                    return actual_path, file_size_mb

            file_path = ydl.prepare_filename(result)
            base, _ = os.path.splitext(file_path)
            actual_path = file_path
            if format_type == "audio":
                actual_path = f"{base}.{extension}"
            elif format_type == "video":
                actual_path = f"{base}.mp4"
            elif format_type == "picture":
                actual_path = f"{base}.{extension}"

            if os.path.exists(actual_path):
                file_size_mb = os.path.getsize(actual_path) / (1024 * 1024)
                logger.info(f"Download complete (prepare_filename): {actual_path} ({file_size_mb:.2f} MB)")
                return actual_path, file_size_mb

            files = [os.path.join("downloads", f) for f in os.listdir("downloads")]
            if files:
                actual_path = max(files, key=os.path.getmtime)
                file_size_mb = os.path.getsize(actual_path) / (1024 * 1024)
                logger.warning(f"Download complete (mtime fallback): {actual_path} ({file_size_mb:.2f} MB)")
                return actual_path, file_size_mb

            raise Exception("File not found after successful download.")
    except Exception as e:
        logger.error(f"download_media failed: {e}")
        raise e


# ---------------------------------------------------------------------------
# Instagram scraper (HTML + embedded JSON, no third-party tools needed)
# ---------------------------------------------------------------------------

def _scrape_instagram_page(url: str) -> str | None:
    headers = {
        "User-Agent": _IG_UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    cookie_header = _cookies_header()
    if cookie_header:
        headers["Cookie"] = cookie_header
    else:
        logger.warning("No Instagram cookies found — scraping may fail for private/login-required posts")

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to fetch Instagram page: {e}")
        return None


def _find_items_in_json(obj):
    """Recursively find 'items' list from Instagram's embedded JSON."""
    if isinstance(obj, dict):
        if "xdt_api__v1__media__shortcode__web_info" in obj:
            items = obj["xdt_api__v1__media__shortcode__web_info"].get("items") or []
            return items
        for v in obj.values():
            r = _find_items_in_json(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_items_in_json(v)
            if r:
                return r
    return None


def _extract_entries_from_html(html: str) -> list:
    scripts = re.findall(
        r'<script type="application/json"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )

    for s in scripts:
        if "xdt_api__v1__media__shortcode__web_info" not in s:
            continue
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            continue

        items = _find_items_in_json(data)
        if not items:
            continue

        item = items[0]
        entries = []

        # Carousel post — guard against explicit null from API
        carousel = item.get("carousel_media") or []
        for i, media in enumerate(carousel, start=1):
            entry = _media_node_to_entry(media, i)
            if entry:
                entries.append(entry)

        # Single image / video
        if not entries:
            entry = _media_node_to_entry(item, 1)
            if entry:
                entries.append(entry)

        if entries:
            logger.info(f"HTML scraper found {len(entries)} entries")
            return entries

    return []


def _media_node_to_entry(node: dict, index: int) -> dict | None:
    """Convert a single media node to a normalised entry dict."""
    # Video
    video_versions = node.get("video_versions") or []
    if video_versions:
        best = max(video_versions, key=lambda v: v.get("width", 0))
        return {
            "index": index,
            "url": best["url"],
            "title": "Instagram Video",
            "ext": "mp4",
            "media_type": "video",
        }

    # Image
    candidates = (node.get("image_versions2") or {}).get("candidates") or []
    if candidates:
        best = candidates[0]  # first = highest resolution
        return {
            "index": index,
            "url": best["url"],
            "title": "Instagram Image",
            "ext": "jpg",
            "media_type": "image",
        }

    return None


def get_instagram_carousel(url: str) -> list:
    """
    Main entry point for Instagram media extraction.
    1. HTML scraping (fast, no deps, works for public + logged-in posts)
    2. yt-dlp fallback (Reels/videos that aren't in the HTML JSON)
    """
    clean_url = re.sub(r"[?&]img_index=\d+", "", url).rstrip("/") + "/"
    logger.info(f"Extracting Instagram carousel for {clean_url}")

    html = _scrape_instagram_page(clean_url)
    if html:
        entries = _extract_entries_from_html(html)
        if entries:
            return entries
        logger.warning("HTML scraper found no entries — falling back to yt-dlp")
    else:
        logger.warning("Could not fetch Instagram page — falling back to yt-dlp")

    # yt-dlp fallback (good for Reels)
    return _get_instagram_entries_via_ytdlp(clean_url)


def _get_instagram_entries_via_ytdlp(url: str) -> list:
    logger.info(f"Extracting Instagram via yt-dlp: {url}")
    ydl_opts = _ydl_opts_base()
    ydl_opts["extract_flat"] = False
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        entries = []
        title = info.get("title", "Instagram Post")[:100]

        if info.get("_type") == "playlist" and info.get("entries"):
            for i, entry in enumerate(info["entries"], start=1):
                if not entry:
                    continue
                media_url = _best_video_url(entry) or entry.get("url")
                if media_url:
                    entries.append({
                        "index": i,
                        "url": media_url,
                        "title": entry.get("title", title)[:100],
                        "ext": "mp4",
                        "media_type": "video",
                    })
        else:
            media_url = _best_video_url(info) or info.get("url")
            if media_url:
                entries.append({
                    "index": 1,
                    "url": media_url,
                    "title": title,
                    "ext": "mp4",
                    "media_type": "video",
                })

        logger.info(f"yt-dlp found {len(entries)} entries")
        return entries
    except Exception as e:
        logger.error(f"yt-dlp Instagram extraction failed: {e}")
        return []


def _best_video_url(info: dict) -> str | None:
    formats = info.get("formats", [])
    video_formats = [f for f in formats if f.get("vcodec", "none") != "none" and f.get("url")]
    if not video_formats:
        return info.get("url")
    return max(video_formats, key=lambda f: f.get("height") or 0).get("url")


async def download_instagram_photo(url, index=None):
    """
    Downloads one or all media items from an Instagram post/carousel.
    Returns list of downloaded file paths.
    """
    entries = get_instagram_carousel(url)
    if not entries:
        return []

    to_download = entries if index is None else [e for e in entries if e["index"] == index]
    os.makedirs("downloads", exist_ok=True)
    results = []

    for entry in to_download:
        try:
            unique_id = str(uuid.uuid4())[:8]
            ext = entry.get("ext", "jpg")
            out_path = f"downloads/ig_{entry['index']}_{unique_id}.{ext}"
            media_url = entry["url"]

            if entry.get("media_type") == "video":
                ydl_opts = _ydl_opts_base()
                ydl_opts["outtmpl"] = out_path
                ydl_opts["quiet"] = True

                def _dl_video():
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([media_url])

                await asyncio.to_thread(_dl_video)
            else:
                # Direct CDN download — no auth needed, URL already signed
                import aiohttp
                headers = {
                    "User-Agent": _IG_UA,
                    "Referer": "https://www.instagram.com/",
                }
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(media_url) as resp:
                        if resp.status == 200:
                            content = await resp.read()
                            with open(out_path, "wb") as f:
                                f.write(content)
                        else:
                            logger.warning(f"CDN returned HTTP {resp.status} for entry {entry['index']}")

            if os.path.exists(out_path):
                results.append(out_path)
                logger.info(f"Downloaded Instagram entry {entry['index']}: {out_path}")
            else:
                logger.warning(f"File not found after download for entry {entry['index']}")

        except Exception as e:
            logger.error(f"Failed to download Instagram entry {entry['index']}: {e}")

    return results
