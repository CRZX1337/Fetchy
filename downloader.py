import os
import glob
import re
import uuid
import yt_dlp

def sanitize_filename(name: str) -> str:
    """Removes invalid or problematic characters from a filename."""
    name = re.sub(r'[^\w\s\-\.]', '', name)
    name = re.sub(r'\s+', '_', name)
    return name.strip('_.-')

def get_media_info(url: str):
    """Fetches metadata without downloading."""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            
            metadata = {
                "title": info.get("title", "Unknown Title"),
                "platform": info.get("extractor", "Unknown"),
                "heights": []
            }
            
            # Extract distinct available heights
            formats = info.get("formats", [])
            heights = set()
            for f in formats:
                h = f.get("height")
                if h:
                    heights.add(h)
            
            metadata["heights"] = sorted(list(heights))
            return metadata
        except Exception:
            return None

def download_media(url: str, format_type: str, quality: str = "1080", extension: str = None, status_hook: callable = None) -> str:
    """
    Enhanced download media function supporting granular format and extension selection.
    """
    temp_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(temp_dir, exist_ok=True)
    
    unique_id = str(uuid.uuid4())[:8]
    filepath_prefix = os.path.join(temp_dir, f'%(title)s_{unique_id}')
    
    current_phase = {"value": "SEARCHING"}
    
    def progress_handler(d):
        if status_hook:
            if d['status'] == 'downloading' and current_phase["value"] != "DOWNLOADING":
                current_phase["value"] = "DOWNLOADING"
                status_hook("DOWNLOADING")
            elif d['status'] == 'finished' and current_phase["value"] != "PROCESSING":
                current_phase["value"] = "PROCESSING"
                status_hook("PROCESSING")

    ydl_opts = {
        'outtmpl': f'{filepath_prefix}.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [progress_handler],
    }
    
    if format_type == "video":
        # Video: specify quality or default to best available under quality
        ydl_opts['format'] = f"bestvideo[height<={quality}]+bestaudio/best"
        ydl_opts['merge_output_format'] = 'mp4'
    elif format_type == "audio":
        # Audio: specify extension (mp3, wav, flac, etc)
        ydl_opts['format'] = 'bestaudio/best'
        target_ext = extension or "mp3"
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': target_ext,
            'preferredquality': '192',
        }]
    elif format_type == "picture":
        # Picture: thumbnails
        ydl_opts['skip_download'] = True
        ydl_opts['writethumbnail'] = True
        target_ext = extension or "png"
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegThumbnailsConvertor',
            'format': target_ext,
        }]

    try:
        if status_hook:
            status_hook("SEARCHING")
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)
            
        files = glob.glob(os.path.join(temp_dir, f"*_{unique_id}.*"))
        if not files:
            raise Exception("Download failed: No output file recorded.")
            
        files.sort(key=os.path.getmtime, reverse=True)
        original_file = files[0]
        
        dirname, basename = os.path.split(original_file)
        name_only, ext = os.path.splitext(basename)
        sanitized_name = sanitize_filename(name_only) + ext
        sanitized_path = os.path.join(dirname, sanitized_name)
        
        if original_file != sanitized_path:
            os.rename(original_file, sanitized_path)
            
        return sanitized_path
        
    except Exception as e:
        try:
            for tmp_file in glob.glob(os.path.join(temp_dir, f"*_{unique_id}.*")):
                os.remove(tmp_file)
        except Exception:
            pass
        raise e
