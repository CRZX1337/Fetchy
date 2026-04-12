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


def get_media_info(url):
    """
    Analyzes a URL to extract title and available video resolutions.
    """
    logger.info(f"Extracting info for {url}")
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
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
    """
    Fetches rich metadata for the preview embed without downloading.
    Returns dict with title, thumbnail, duration, uploader, is_playlist, playlist_count.
    """
    logger.info(f"Fetching preview info for {url}")
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,  # fast for playlists
    }
    if os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = 'cookies.txt'
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        is_playlist = info.get('_type') == 'playlist'
        playlist_count = len(info.get('entries', [])) if is_playlist else 0
        duration = info.get('duration')  # seconds, may be None for playlists
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


def download_media(url, format_type, quality="1080", extension="mp3", status_hook=None, cancel_event: threading.Event = None):
    """
    Downloads media from a URL based on user preferences.
    Returns (file_path, file_size_mb).
    """
    logger.info(f"Downloading {format_type} from {url} (Quality: {quality}, Ext: {extension})")

    is_tiktok = "tiktok.com" in url

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

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'restrictfilenames': True,
        'outtmpl': output_tpl,
        'progress_hooks': [progress_handler],
    }
    if os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = 'cookies.txt'

    if format_type == "video":
        ydl_opts['format'] = f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]'
        ydl_opts['merge_output_format'] = 'mp4'
        # TikTok: remove watermark
        if is_tiktok:
            ydl_opts['format'] = 'bestvideo[format_id*=no_watermark]+bestaudio/bestvideo+bestaudio/best'
            logger.info("TikTok URL detected — using no-watermark format selector")
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
                logger.info(f"Download complete: {actual_path} ({file_size_mb:.2f} MB)")
                return actual_path, file_size_mb
            else:
                matching = [
                    os.path.join("downloads", f)
                    for f in os.listdir("downloads")
                    if unique_id in f
                ]
                if matching:
                    actual_path = matching[0]
                    file_size_mb = os.path.getsize(actual_path) / (1024 * 1024)
                    logger.info(f"Download complete (fallback path): {actual_path} ({file_size_mb:.2f} MB)")
                    return actual_path, file_size_mb

            raise Exception("File not found after successful download.")
    except Exception as e:
        logger.error(f"download_media failed: {e}")
        raise e


async def download_playlist(url, format_type, quality="1080", extension="mp3", progress_callback=None, cancel_event: threading.Event = None):
    """
    Downloads each video in a playlist one by one.
    Calls progress_callback(current, total, title, filepath) after each successful download.
    Returns list of (filepath, size_mb) tuples.
    """
    logger.info(f"Starting playlist download: {url}")

    # Step 1: Get playlist metadata
    ydl_meta_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
    }
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
    """
    Creates Instaloader instance and loads session if available.
    """
    L = instaloader.Instaloader(
        quiet=True,
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        save_metadata=False,
        compress_json=False
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
            quiet=True,
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            save_metadata=False,
            compress_json=False
        )


def get_instagram_carousel(url):
    """
    Extracts carousel entries from an Instagram post using Instaloader.
    Returns a list of dicts: [{'index': 1, 'url': '...', 'title': '...', 'ext': 'jpg', 'media_type': 'image'}, ...]
    """
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
                media_type = 'video' if is_video else 'image'
                if media_url:
                    entries.append({
                        'index': i,
                        'url': media_url,
                        'title': caption,
                        'ext': ext,
                        'media_type': media_type,
                    })
                    logger.info(f"Got {media_type} URL for entry {i}")
        else:
            logger.info("Post is a single image/video")
            is_video = getattr(post, 'is_video', False)
            media_url = getattr(post, 'video_url', None) if is_video else getattr(post, 'url', None)
            ext = 'mp4' if is_video else 'jpg'
            media_type = 'video' if is_video else 'image'
            if media_url:
                entries.append({
                    'index': 1,
                    'url': media_url,
                    'title': caption,
                    'ext': ext,
                    'media_type': media_type,
                })
                logger.info(f"Got {media_type} URL for single entry")

        logger.info(f"Found {len(entries)} entries for Instagram post.")
        return entries
    except Exception as e:
        logger.error(f"get_instagram_carousel failed: {e}")
        return []


async def download_instagram_photo(url, index=None):
    """
    Downloads one or all media items from an Instagram post or carousel.
    Returns list of file paths.
    """
    entries = get_instagram_carousel(url)
    if not entries:
        return []

    to_download = entries
    if index is not None:
        to_download = [e for e in entries if e['index'] == index]

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
                media_type = entry.get('media_type', 'image')
                file_path = f"downloads/{clean_title}_{short_hash}.{ext}"

                max_attempts = 3
                downloaded = False
                for attempt in range(1, max_attempts + 1):
                    async with session.get(entry['url']) as resp:
                        if resp.status == 200:
                            content = await resp.read()
                            with open(file_path, "wb") as f:
                                f.write(content)
                            results.append(file_path)
                            logger.info(f"Downloaded Instagram {media_type}: {file_path}")
                            downloaded = True
                            break
                        elif resp.status == 429:
                            retry_after = resp.headers.get("Retry-After")
                            if retry_after:
                                wait_time = float(retry_after)
                                logger.warning(
                                    f"Instagram rate-limited (429). Respecting Retry-After: {wait_time}s "
                                    f"(attempt {attempt}/{max_attempts})"
                                )
                            else:
                                wait_time = 2 ** attempt
                                logger.warning(
                                    f"Instagram rate-limited (429). Backing off {wait_time}s "
                                    f"(attempt {attempt}/{max_attempts})"
                                )
                            if attempt < max_attempts:
                                await asyncio.sleep(wait_time)
                        else:
                            logger.warning(
                                f"Unexpected HTTP {resp.status} for entry {entry['index']} "
                                f"(attempt {attempt}/{max_attempts})"
                            )
                            break

                if not downloaded:
                    logger.error(
                        f"All {max_attempts} attempts exhausted for entry {entry['index']} — skipping."
                    )
            except Exception as e:
                logger.error(f"Failed to download photo {entry['index']}: {e}")

    return results
