import yt_dlp
import os
import uuid
import logging
import hashlib
import re
import aiohttp

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
            
            # Extract distinct heights (only if they have a video stream)
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

def download_media(url, format_type, quality="1080", extension="mp3", status_hook=None):
    """
    Downloads media from a URL based on user preferences.
    Returns (file_path, file_size_mb).
    """
    logger.info(f"Downloading {format_type} from {url} (Quality: {quality}, Ext: {extension})")
    
    # Status Phase Tracking
    current_phase = {"value": "SEARCHING"}

    def progress_handler(d):
        if status_hook is not None:
            if d['status'] == "downloading" and current_phase["value"] != "DOWNLOADING":
                current_phase["value"] = "DOWNLOADING"
                status_hook("DOWNLOADING")
            elif d['status'] == "finished" and current_phase["value"] != "PROCESSING":
                current_phase["value"] = "PROCESSING"
                status_hook("PROCESSING")

    # Ensure downloads directory exists
    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    # Generate a unique filename to prevent collisions
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
        # Select best quality up to the requested one
        ydl_opts['format'] = f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]'
        ydl_opts['merge_output_format'] = 'mp4'
    elif format_type == "audio":
        # Extract audio and convert to requested extension
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': extension,
            'preferredquality': '192',
        }]
    elif format_type == "picture":
        # Strategy: Fetch highest quality thumbnail
        ydl_opts['writethumbnail'] = True
        ydl_opts['skip_download'] = True
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegThumbnailsConvertor',
            'format': extension, # png, jpg, webp
        }]

    try:
        if status_hook is not None:
            status_hook("SEARCHING")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=True)
            # Find the actual final file path (might differ after conversion)
            file_path = ydl.prepare_filename(result)
            
            # Post-processors might change the extension
            base, _ = os.path.splitext(file_path)
            
            # Handle standard naming variations from yt-dlp
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
                # Fallback search
                files = [os.path.join("downloads", f) for f in os.listdir("downloads")]
                if files:
                    actual_path = max(files, key=os.path.getmtime)
                    file_size_mb = os.path.getsize(actual_path) / (1024 * 1024)
                    logger.info(f"Download complete (fallback path): {actual_path} ({file_size_mb:.2f} MB)")
                    return actual_path, file_size_mb
                
            raise Exception("File not found after successful download.")
    except Exception as e:
        logger.error(f"download_media failed: {e}")
        raise e

def get_instagram_carousel(url):
    """
    Extracts carousel entries (multi-photo) from an Instagram post.
    Returns a list of dicts: [{'index': 1, 'url': '...', 'title': '...'}, ...]
    """
    logger.info(f"Extracting Instagram carousel for {url}")
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True,
        'ignore_no_formats_error': True
    }
    if os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = 'cookies.txt'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False, process=True)
            info = ydl.process_ie_result(info, download=False)

            if not info:
                return []
            
            title = info.get('title', 'Instagram Photo')
            entries = []
            
            raw_entries = info.get('entries', [])
            if raw_entries:
                for i, entry in enumerate(raw_entries, 1):
                    # Get best thumbnail: last item in 'thumbnails' or fallback to 'thumbnail'/'url'
                    thumbnails = entry.get('thumbnails', [])
                    img_url = thumbnails[-1].get('url') if thumbnails else (entry.get('thumbnail') or entry.get('url'))
                    
                    if img_url:
                        entries.append({
                            'index': i,
                            'url': img_url,
                            'title': title
                        })
            else:
                # Single photo logic
                thumbnails = info.get('thumbnails', [])
                img_url = thumbnails[-1].get('url') if thumbnails else info.get('thumbnail')
                
                if img_url:
                    entries.append({
                        'index': 1,
                        'url': img_url,
                        'title': title
                    })
            
            logger.info(f"Found {len(entries)} entries for Instagram post.")
            return entries
    except Exception as e:
        logger.error(f"get_instagram_carousel failed: {e}")
        return []

async def download_instagram_photo(url, index=None):
    """
    Downloads one or all photos from an Instagram carousel.
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

    async with aiohttp.ClientSession() as session:
        for entry in to_download:
            try:
                # Sanitize title
                clean_title = re.sub(r'[^\w\-_\. ]', '_', entry['title'])[:30]
                short_hash = hashlib.md5(entry['url'].encode()).hexdigest()[:8]
                file_path = f"downloads/{clean_title}_{short_hash}.jpg"

                async with session.get(entry['url']) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        with open(file_path, "wb") as f:
                            f.write(content)
                        results.append(file_path)
                        logger.info(f"Downloaded Instagram photo: {file_path}")
            except Exception as e:
                logger.error(f"Failed to download photo {entry['index']}: {e}")
    
    return results
