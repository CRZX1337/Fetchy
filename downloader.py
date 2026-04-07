import yt_dlp
import os
import uuid
import logging
import re
import time
import threading
import subprocess
import json
import asyncio

logger = logging.getLogger("MediaBot.Downloader")

# Absolute path to cookies file inside the container
COOKIES_FILE = "/app/cookies.txt"


def _ydl_opts_base() -> dict:
    opts = {
        'quiet': True,
        'no_warnings': True,
    }
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
    return opts


def _gallery_dl_cmd(extra_args: list) -> list:
    """Build gallery-dl command, injecting --cookies if available."""
    cmd = ["gallery-dl"]
    if os.path.exists(COOKIES_FILE):
        cmd += ["--cookies", COOKIES_FILE]
    return cmd + extra_args


def get_media_info(url):
    logger.info(f"Extracting info for {url}")
    try:
        with yt_dlp.YoutubeDL(_ydl_opts_base()) as ydl:
            info = ydl.extract_info(url, download=False)
            heights = []
            if 'formats' in info:
                for f in info['formats']:
                    h = f.get('height')
                    if h and f.get('vcodec') != 'none':
                        heights.append(h)
            return {
                'title': info.get('title', 'Unknown Media'),
                'heights': list(set(heights))
            }
    except Exception as e:
        logger.warning(f"get_media_info failed for {url}: {e}")
        return None


def download_media(url, format_type, quality="1080", extension="mp3", status_hook=None, cancel_event: threading.Event = None):
    logger.info(f"Downloading {format_type} from {url} (Quality: {quality}, Ext: {extension})")

    current_phase = {"value": "SEARCHING"}
    last_update = {"time": 0}

    def progress_handler(d):
        if status_hook is None:
            return
        now = time.time()
        if d['status'] == "downloading":
            if cancel_event and cancel_event.is_set():
                raise Exception("Download cancelled by user.")
            if now - last_update["time"] < 2.0 and current_phase["value"] == "DOWNLOADING":
                return
            last_update["time"] = now
            current_phase["value"] = "DOWNLOADING"
            downloaded = d.get('downloaded_bytes', 0) or 0
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            speed = d.get('speed') or 0
            percent = (downloaded / total * 100) if total > 0 else 0
            status_hook({
                "phase": "DOWNLOADING",
                "percent": round(percent, 1),
                "downloaded_mb": round(downloaded / 1024 / 1024, 1),
                "total_mb": round(total / 1024 / 1024, 1),
                "speed_mb": round(speed / 1024 / 1024, 2) if speed else 0,
            })
        elif d['status'] == "finished":
            if cancel_event and cancel_event.is_set():
                raise Exception("Download cancelled by user.")
            if current_phase["value"] != "PROCESSING":
                current_phase["value"] = "PROCESSING"
                status_hook({"phase": "PROCESSING"})

    os.makedirs("downloads", exist_ok=True)
    unique_id = str(uuid.uuid4())[:8]
    output_tpl = f'downloads/%(title)s_{unique_id}.%(ext)s'

    ydl_opts = _ydl_opts_base()
    ydl_opts.update({
        'restrictfilenames': True,
        'outtmpl': output_tpl,
        'progress_hooks': [progress_handler],
    })

    if format_type == "video":
        ydl_opts['format'] = f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]'
        ydl_opts['merge_output_format'] = 'mp4'
    elif format_type == "audio":
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': extension,
            'preferredquality': '192',
        }]
    elif format_type == "picture":
        ydl_opts['writethumbnail'] = True
        ydl_opts['skip_download'] = True
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegThumbnailsConvertor',
            'format': extension,
        }]

    try:
        if status_hook is not None:
            status_hook({"phase": "SEARCHING"})

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=True)

            requested = result.get('requested_downloads')
            if requested and len(requested) > 0:
                actual_path = requested[0].get('filepath')
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
# Instagram helpers
# ---------------------------------------------------------------------------

def _is_instagram_video_url(url: str) -> bool:
    return bool(re.search(r'instagram\.com/(?:reel|tv)/', url))


def _gallery_dl_available() -> bool:
    try:
        result = subprocess.run(["gallery-dl", "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def _get_instagram_entries_via_gallery_dl(url: str) -> list:
    logger.info(f"Extracting Instagram post via gallery-dl: {url}")
    try:
        cmd = _gallery_dl_cmd(["--dump-json", url])
        logger.debug(f"gallery-dl cmd: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            logger.warning(f"gallery-dl exited {result.returncode}: {result.stderr[:300]}")
            return []

        entries = []
        for line in result.stdout.strip().splitlines():
            try:
                item = json.loads(line)
                if isinstance(item, list) and len(item) >= 3:
                    media_url = item[2] if isinstance(item[2], str) else None
                    if not media_url:
                        continue
                    ext = media_url.split('?')[0].rsplit('.', 1)[-1].lower() if '.' in media_url else 'jpg'
                    if ext not in ('jpg', 'jpeg', 'png', 'webp', 'mp4', 'mov'):
                        ext = 'jpg'
                    media_type = 'video' if ext in ('mp4', 'mov') else 'image'
                    post_info = item[1] if isinstance(item[1], dict) else {}
                    title = post_info.get('description', 'Instagram Post')[:100]
                    entries.append({
                        'index': len(entries) + 1,
                        'url': media_url,
                        'title': title,
                        'ext': ext,
                        'media_type': media_type,
                    })
            except (json.JSONDecodeError, IndexError):
                continue

        logger.info(f"gallery-dl found {len(entries)} entries")
        return entries
    except subprocess.TimeoutExpired:
        logger.error("gallery-dl timed out (60s)")
        return []
    except Exception as e:
        logger.error(f"gallery-dl extraction failed: {e}")
        return []


def _get_instagram_entries_via_ytdlp(url: str) -> list:
    logger.info(f"Extracting Instagram reel via yt-dlp: {url}")
    ydl_opts = _ydl_opts_base()
    ydl_opts['extract_flat'] = False
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        entries = []
        title = info.get('title', 'Instagram Post')[:100]

        if info.get('_type') == 'playlist' and info.get('entries'):
            for i, entry in enumerate(info['entries'], start=1):
                if not entry:
                    continue
                media_url = _best_video_url(entry) or entry.get('url')
                if media_url:
                    entries.append({
                        'index': i,
                        'url': media_url,
                        'title': entry.get('title', title)[:100],
                        'ext': 'mp4',
                        'media_type': 'video',
                    })
        else:
            media_url = _best_video_url(info) or info.get('url')
            if media_url:
                entries.append({
                    'index': 1,
                    'url': media_url,
                    'title': title,
                    'ext': 'mp4',
                    'media_type': 'video',
                })

        logger.info(f"yt-dlp found {len(entries)} video entries")
        return entries
    except Exception as e:
        logger.error(f"yt-dlp Instagram extraction failed: {e}")
        return []


def get_instagram_carousel(url: str) -> list:
    """
    Smart router:
    - /reel/ or /tv/  -> yt-dlp
    - /p/ image post  -> gallery-dl (with cookies), yt-dlp fallback
    """
    clean_url = re.sub(r'[?&]img_index=\d+', '', url)

    if _is_instagram_video_url(clean_url):
        logger.info("Routing to yt-dlp (Reel/TV)")
        return _get_instagram_entries_via_ytdlp(clean_url)

    if _gallery_dl_available():
        cookies_status = "with cookies" if os.path.exists(COOKIES_FILE) else "WITHOUT cookies (may fail)"
        logger.info(f"Routing to gallery-dl (image post, {cookies_status})")
        entries = _get_instagram_entries_via_gallery_dl(clean_url)
        if entries:
            return entries
        logger.warning("gallery-dl returned no entries, falling back to yt-dlp")

    logger.info("Falling back to yt-dlp for Instagram post")
    return _get_instagram_entries_via_ytdlp(clean_url)


def _best_video_url(info: dict) -> str | None:
    formats = info.get('formats', [])
    video_formats = [f for f in formats if f.get('vcodec', 'none') != 'none' and f.get('url')]
    if not video_formats:
        return info.get('url')
    return max(video_formats, key=lambda f: f.get('height') or 0).get('url')


async def download_instagram_photo(url, index=None):
    entries = get_instagram_carousel(url)
    if not entries:
        return []

    to_download = entries if index is None else [e for e in entries if e['index'] == index]
    os.makedirs("downloads", exist_ok=True)
    results = []

    for entry in to_download:
        try:
            unique_id = str(uuid.uuid4())[:8]
            ext = entry.get('ext', 'jpg')
            out_path = f"downloads/ig_{entry['index']}_{unique_id}.{ext}"
            media_url = entry['url']

            if entry.get('media_type') == 'video':
                ydl_opts = _ydl_opts_base()
                ydl_opts['outtmpl'] = out_path

                def _dl_video():
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([media_url])

                await asyncio.to_thread(_dl_video)
            else:
                # Direct image download via aiohttp (fastest, no extra tools needed)
                import aiohttp
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'https://www.instagram.com/',
                }
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(media_url) as resp:
                        if resp.status == 200:
                            content = await resp.read()
                            with open(out_path, 'wb') as f:
                                f.write(content)
                        else:
                            logger.warning(f"Direct image download returned HTTP {resp.status} for entry {entry['index']}")

            if os.path.exists(out_path):
                results.append(out_path)
                logger.info(f"Downloaded Instagram entry {entry['index']}: {out_path}")
            else:
                logger.warning(f"File not found after download for entry {entry['index']}")

        except Exception as e:
            logger.error(f"Failed to download Instagram entry {entry['index']}: {e}")

    return results
