import yt_dlp
import os
import uuid
import asyncio
import logging
import hashlib
import re
import time
import threading
import aiohttp
import instaloader

# --- LOGGING SETUP ---
logger = logging.getLogger("MediaBot.Downloader")

# Extensions yt-dlp may write before FFmpeg converts them
_INTERMEDIATE_EXTS = {".image", ".webp", ".jfif", ".jpeg", ".jpg", ".png"}

# How many times to retry a download on DNS/network failure
_DOWNLOAD_RETRIES = 3
_RETRY_DELAY = 3  # seconds between retries


def _find_and_fix_picture(base: str, wanted_ext: str) -> str | None:
    """
    After yt-dlp thumbnail download, the file may sit as .image / .webp / etc.
    This finds whatever was written and renames it to <base>.<wanted_ext>.
    Returns final path or None.
    """
    wanted_ext = wanted_ext.lstrip(".")
    target = f"{base}.{wanted_ext}"

    if os.path.exists(target):
        return target

    folder = os.path.dirname(base) or "downloads"
    stem = os.path.basename(base)
    for fname in os.listdir(folder):
        fbase, fext = os.path.splitext(fname)
        if fbase == stem and fext.lower() in _INTERMEDIATE_EXTS:
            src = os.path.join(folder, fname)
            logger.info(f"Renaming thumbnail {src} -> {target}")
            os.rename(src, target)
            return target

    return None


def _parse_timestamp(ts: str) -> float | None:
    """
    Parses a timestamp string like '1:30', '1:30:00' or '90' into seconds.
    Returns None if invalid.
    """
    ts = ts.strip()
    try:
        parts = ts.split(":")
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except (ValueError, IndexError):
        return None
    return None


def get_platform(url: str) -> dict:
    """
    Returns platform metadata (name, emoji, color) based on URL.
    Color is a discord.Color-compatible integer (hex).
    """
    u = url.lower()
    if "tiktok.com" in u:
        return {"name": "TikTok", "emoji": "🎵", "color": 0x010101}
    if "youtube.com" in u or "youtu.be" in u:
        return {"name": "YouTube", "emoji": "▶️", "color": 0xFF0000}
    if "instagram.com" in u:
        return {"name": "Instagram", "emoji": "📸", "color": 0xE1306C}
    if "twitter.com" in u or "x.com" in u:
        return {"name": "X / Twitter", "emoji": "🐦", "color": 0x1DA1F2}
    if "soundcloud.com" in u:
        return {"name": "SoundCloud", "emoji": "🔊", "color": 0xFF5500}
    if "spotify.com" in u:
        return {"name": "Spotify", "emoji": "🎧", "color": 0x1DB954}
    if "reddit.com" in u or "redd.it" in u:
        return {"name": "Reddit", "emoji": "🤖", "color": 0xFF4500}
    if "facebook.com" in u or "fb.watch" in u:
        return {"name": "Facebook", "emoji": "📘", "color": 0x1877F2}
    if "twitch.tv" in u:
        return {"name": "Twitch", "emoji": "🟣", "color": 0x9146FF}
    if "vimeo.com" in u:
        return {"name": "Vimeo", "emoji": "🎬", "color": 0x1AB7EA}
    if "pinterest.com" in u:
        return {"name": "Pinterest", "emoji": "📌", "color": 0xE60023}
    if "bandcamp.com" in u:
        return {"name": "Bandcamp", "emoji": "🎸", "color": 0x1DA0C3}
    return {"name": "Web", "emoji": "🌐", "color": 0x5865F2}


def get_media_info(url):
    logger.info(f"Extracting info for {url}")
    ydl_opts = {'quiet': True, 'no_warnings': True}
    if os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = 'cookies.txt'
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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


def get_preview_info(url):
    logger.info(f"Fetching preview info for {url}")
    ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True}
    if os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = 'cookies.txt'
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        is_playlist = info.get('_type') == 'playlist'
        playlist_count = len(info.get('entries', [])) if is_playlist else 0
        duration = info.get('duration')
        duration_str = None
        if duration:
            mins, secs = divmod(int(duration), 60)
            hrs, mins = divmod(mins, 60)
            duration_str = f"{hrs}:{mins:02d}:{secs:02d}" if hrs else f"{mins}:{secs:02d}"

        return {
            'title': info.get('title', 'Unknown Media'),
            'thumbnail': info.get('thumbnail'),
            'duration': duration_str,
            'uploader': info.get('uploader') or info.get('channel') or info.get('creator'),
            'is_playlist': is_playlist,
            'playlist_count': playlist_count,
        }
    except Exception as e:
        logger.warning(f"get_preview_info failed for {url}: {e}")
        return None


def _build_ydl_opts(format_type, quality, extension, output_tpl, progress_handler):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'restrictfilenames': True,
        'outtmpl': output_tpl,
        'progress_hooks': [progress_handler],
    }
    if os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = 'cookies.txt'
    return ydl_opts


def _apply_format(ydl_opts, url, format_type, quality, extension):
    is_tiktok = "tiktok.com" in url

    if format_type == "video":
        if is_tiktok:
            ydl_opts['format'] = (
                'bestvideo[vcodec^=h264]+bestaudio/'
                'bestvideo+bestaudio/'
                'best'
            )
            logger.info("TikTok video: using broad h264 format chain")
        else:
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


def _resolve_output(base, unique_id, format_type, extension):
    if format_type == "audio":
        p = f"{base}.{extension}"
        if os.path.exists(p):
            return p, os.path.getsize(p) / (1024 * 1024)

    elif format_type == "video":
        p = f"{base}.mp4"
        if os.path.exists(p):
            return p, os.path.getsize(p) / (1024 * 1024)

    elif format_type == "picture":
        p = _find_and_fix_picture(base, extension)
        if p:
            return p, os.path.getsize(p) / (1024 * 1024)

    folder = "downloads"
    matching = [os.path.join(folder, f) for f in os.listdir(folder) if unique_id in f]
    if matching:
        actual = matching[0]
        if format_type == "picture":
            wanted = f"{os.path.splitext(actual)[0]}.{extension}"
            if actual != wanted:
                logger.info(f"Renaming fallback: {actual} -> {wanted}")
                os.rename(actual, wanted)
                actual = wanted
        return actual, os.path.getsize(actual) / (1024 * 1024)

    raise Exception("File not found after successful download.")


def download_media(url, format_type, quality="1080", extension="mp3", status_hook=None,
                   cancel_event: threading.Event = None,
                   start_time: str = None, end_time: str = None):
    """
    Downloads media from a URL. Optionally trims audio/video to [start_time, end_time].
    Retries up to _DOWNLOAD_RETRIES times on transient network/DNS errors.
    Returns (file_path, file_size_mb).
    """
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

    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    unique_id = str(uuid.uuid4())[:8]
    output_tpl = f'downloads/%(title)s_{unique_id}.%(ext)s'

    last_error = None
    for attempt in range(1, _DOWNLOAD_RETRIES + 1):
        if cancel_event and cancel_event.is_set():
            raise Exception("Download cancelled by user.")

        ydl_opts = _build_ydl_opts(format_type, quality, extension, output_tpl, progress_handler)
        _apply_format(ydl_opts, url, format_type, quality, extension)

        # Audio trim via FFmpeg postprocessor
        if (start_time or end_time) and format_type in ("audio", "video"):
            start_sec = _parse_timestamp(start_time) if start_time else None
            end_sec = _parse_timestamp(end_time) if end_time else None
            pp_args = []
            if start_sec is not None:
                pp_args += ["-ss", str(start_sec)]
            if end_sec is not None:
                if start_sec is not None:
                    pp_args += ["-t", str(end_sec - start_sec)]
                else:
                    pp_args += ["-to", str(end_sec)]
            if pp_args:
                existing_pps = ydl_opts.get('postprocessors', [])
                ydl_opts['postprocessors'] = existing_pps + [{
                    'key': 'FFmpegPostProcessor',
                    'preferedformat': extension if format_type == 'audio' else 'mp4',
                    'args': pp_args,
                }]
                # For audio trim, use FFmpegExtractAudio with external time args
                # Simpler: use download_ranges instead (yt-dlp native)
                ydl_opts.pop('postprocessors', None)  # remove manual pp
                ydl_opts['download_ranges'] = yt_dlp.utils.download_range_func(
                    None,
                    [{
                        "start_time": start_sec if start_sec is not None else 0,
                        "end_time": end_sec if end_sec is not None else float('inf'),
                    }]
                )
                ydl_opts['force_keyframes_at_cuts'] = True
                # Re-apply format postprocessors after clearing
                _apply_format(ydl_opts, url, format_type, quality, extension)

        try:
            if status_hook is not None and attempt == 1:
                status_hook({"phase": "SEARCHING"})
            elif attempt > 1:
                logger.info(f"Retry {attempt}/{_DOWNLOAD_RETRIES} for {url}")
                if status_hook:
                    status_hook({"phase": "SEARCHING"})

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(result)

            base, _ = os.path.splitext(file_path)
            actual_path, file_size_mb = _resolve_output(base, unique_id, format_type, extension)
            logger.info(f"Download complete: {actual_path} ({file_size_mb:.2f} MB)")
            return actual_path, file_size_mb

        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            is_network_error = any(x in err_str for x in (
                "name or service not known",
                "failed to resolve",
                "network is unreachable",
                "connection refused",
                "timed out",
                "errno -2",
                "transporterror",
            ))
            if "cancelled by user" in err_str:
                raise
            if is_network_error and attempt < _DOWNLOAD_RETRIES:
                logger.warning(f"Network error on attempt {attempt}/{_DOWNLOAD_RETRIES}: {e} — retrying in {_RETRY_DELAY}s")
                time.sleep(_RETRY_DELAY)
                continue
            break

    logger.error(f"download_media failed after {_DOWNLOAD_RETRIES} attempts: {last_error}")
    raise last_error


async def download_playlist(url, format_type, quality="1080", extension="mp3", progress_callback=None, cancel_event: threading.Event = None):
    logger.info(f"Starting playlist download: {url}")
    ydl_meta_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True}
    if os.path.exists("cookies.txt"):
        ydl_meta_opts['cookiefile'] = 'cookies.txt'

    try:
        with yt_dlp.YoutubeDL(ydl_meta_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f"Playlist metadata fetch failed: {e}")
        raise

    entries = info.get('entries', [])
    total = len(entries)
    if total == 0:
        raise Exception("Playlist appears to be empty.")

    logger.info(f"Playlist has {total} entries.")
    results = []

    for i, entry in enumerate(entries, start=1):
        if cancel_event and cancel_event.is_set():
            logger.info("Playlist download cancelled by user.")
            break

        entry_url = entry.get('url') or entry.get('webpage_url')
        entry_title = entry.get('title', f'Track {i}')

        if not entry_url:
            logger.warning(f"Skipping entry {i}: no URL found")
            continue

        logger.info(f"Downloading playlist entry {i}/{total}: {entry_title}")
        try:
            filepath, size_mb = await asyncio.to_thread(
                download_media, entry_url, format_type, quality, extension, None, cancel_event
            )
            results.append((filepath, size_mb))
            if progress_callback:
                await progress_callback(i, total, entry_title, filepath)
        except Exception as e:
            logger.error(f"Failed to download playlist entry {i} ({entry_title}): {e}")
            if progress_callback:
                await progress_callback(i, total, f"❌ {entry_title} (failed)", None)

    return results


def _get_instaloader_instance():
    L = instaloader.Instaloader(
        quiet=True, download_pictures=False, download_videos=False,
        download_video_thumbnails=False, save_metadata=False, compress_json=False
    )
    try:
        username = os.environ.get('INSTAGRAM_USERNAME')
        if username:
            session_file = f"/app/session/session-{username}"
            if os.path.exists(session_file):
                L.load_session_from_file(username, session_file)
                logger.info(f"Successfully loaded Instaloader session for {username}")
            else:
                logger.warning(f"Session file not found at {session_file}")
        else:
            logger.warning("INSTAGRAM_USERNAME not set in environment.")
        return L
    except Exception as e:
        logger.warning(f"Failed to load session ({e}), returning anonymous Instaloader.")
        return instaloader.Instaloader(
            quiet=True, download_pictures=False, download_videos=False,
            download_video_thumbnails=False, save_metadata=False, compress_json=False
        )


def get_instagram_carousel(url):
    logger.info(f"Extracting Instagram carousel for {url}")
    try:
        clean_url = re.sub(r'[\?&]img_index=\d+', '', url)
        match = re.search(r'/(?:p|reel)/([^/?#&]+)', clean_url)
        if not match:
            logger.warning(f"Could not extract shortcode from {url}")
            return []

        shortcode = match.group(1)
        logger.info(f"Extracted shortcode: {shortcode}")

        L = _get_instaloader_instance()
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        caption = post.caption[:100] if post.caption else "Instagram Post"
        entries = []

        if post.typename == 'GraphSidecar':
            logger.info("Post is a GraphSidecar (carousel)")
            for i, node in enumerate(post.get_sidecar_nodes(), start=1):
                is_video = getattr(node, 'is_video', False)
                media_url = getattr(node, 'video_url', None) if is_video else getattr(node, 'display_url', None)
                ext = 'mp4' if is_video else 'jpg'
                if media_url:
                    entries.append({'index': i, 'url': media_url, 'title': caption,
                                    'ext': ext, 'media_type': 'video' if is_video else 'image'})
        else:
            logger.info("Post is a single image/video")
            is_video = getattr(post, 'is_video', False)
            media_url = getattr(post, 'video_url', None) if is_video else getattr(post, 'url', None)
            ext = 'mp4' if is_video else 'jpg'
            if media_url:
                entries.append({'index': 1, 'url': media_url, 'title': caption,
                                'ext': ext, 'media_type': 'video' if is_video else 'image'})

        logger.info(f"Found {len(entries)} entries for Instagram post.")
        return entries
    except Exception as e:
        logger.error(f"get_instagram_carousel failed: {e}")
        return []


async def download_instagram_photo(url, index=None):
    entries = get_instagram_carousel(url)
    if not entries:
        return []

    to_download = entries if index is None else [e for e in entries if e['index'] == index]
    results = []
    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    headers = {'Referer': 'https://www.instagram.com/'}
    async with aiohttp.ClientSession(headers=headers) as session:
        for entry in to_download:
            try:
                clean_title = re.sub(r'[^\w\-_\. ]', '_', entry['title'])[:30]
                short_hash = hashlib.md5(entry['url'].encode()).hexdigest()[:8]
                ext = entry.get('ext', 'jpg')
                file_path = f"downloads/{clean_title}_{short_hash}.{ext}"

                downloaded = False
                for attempt in range(1, 4):
                    async with session.get(entry['url']) as resp:
                        if resp.status == 200:
                            with open(file_path, "wb") as f:
                                f.write(await resp.read())
                            results.append(file_path)
                            logger.info(f"Downloaded Instagram {entry.get('media_type','image')}: {file_path}")
                            downloaded = True
                            break
                        elif resp.status == 429:
                            retry_after = resp.headers.get("Retry-After")
                            wait_time = float(retry_after) if retry_after else 2 ** attempt
                            logger.warning(f"Instagram 429 — backing off {wait_time}s (attempt {attempt}/3)")
                            if attempt < 3:
                                await asyncio.sleep(wait_time)
                        else:
                            logger.warning(f"HTTP {resp.status} for entry {entry['index']} (attempt {attempt}/3)")
                            break

                if not downloaded:
                    logger.error(f"All 3 attempts exhausted for entry {entry['index']} — skipping.")
            except Exception as e:
                logger.error(f"Failed to download photo {entry['index']}: {e}")

    return results
