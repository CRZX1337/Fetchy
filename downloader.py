import os
import glob
import re
import uuid
import yt_dlp

def sanitize_filename(name: str) -> str:
    """Entfernt ungültige oder problematische Zeichen aus einem Dateinamen."""
    # Erlaube nur Buchstaben, Zahlen, Bindestriche, Unterstriche und Punkte
    name = re.sub(r'[^\w\s\-\.]', '', name)
    # Ersetze Leerzeichen (inkl. Tabs etc.) durch Unterstriche für höhere Kompatibilität
    name = re.sub(r'\s+', '_', name)
    # Entferne überschüssige Zeichen am Anfang/Ende
    return name.strip('_.-')

def download_media(url: str, format_type: str) -> str:
    """
    Lädt Dateien synchron via yt-dlp herunter und verwendet den echten Titel.
    Darf im Bot-Kontext nur aus asyncio.to_thread aufgerufen werden!
    """
    temp_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(temp_dir, exist_ok=True)
    
    # Unique ID für kollisionsfreie Downloads erzeugen
    unique_id = str(uuid.uuid4())[:8]
    
    # Echter Videotitel + unique_id kombiniert, um Überschreibungen bei denselben Titeln zu vermeiden
    filepath_prefix = os.path.join(temp_dir, f'%(title)s_{unique_id}')
    
    ydl_opts = {
        'outtmpl': f'{filepath_prefix}.%(ext)s',
        'quiet': True,
        'no_warnings': True,
    }
    
    if format_type == "video":
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        ydl_opts['merge_output_format'] = 'mp4'
    elif format_type == "audio":
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    elif format_type == "thumbnail":
        ydl_opts['skip_download'] = True
        ydl_opts['writethumbnail'] = True
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegThumbnailsConvertor',
            'format': 'png',
        }]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Download und Extraktion durchführen
            info = ydl.extract_info(url, download=True)
            
        # Datei suchen über die im Pattern vergebene unique_id
        files = glob.glob(os.path.join(temp_dir, f"*_{unique_id}.*"))
        
        if not files:
            raise Exception("Keine Zieldatei generiert. Evtl. ist der Post privat oder die Plattform hat die Anfrage blockiert.")
            
        # Neueste modifizierte Datei an die Spitze
        files.sort(key=os.path.getmtime, reverse=True)
        original_file = files[0]
        
        # Originalen Namen in sicheren Namen konvertieren
        dirname, basename = os.path.split(original_file)
        name_only, ext = os.path.splitext(basename)
        
        sanitized_name = sanitize_filename(name_only) + ext
        sanitized_path = os.path.join(dirname, sanitized_name)
        
        # Datei umbenennen, um Server/Discord Probleme mit Emojis oder Leerzeichen zu vermeiden
        if original_file != sanitized_path:
            os.rename(original_file, sanitized_path)
            
        return sanitized_path
        
    except Exception as e:
        # Emergency Cleanup, falls das yt_dlp Plugin unvollständige Fragmente übrig lässt.
        try:
            for tmp_file in glob.glob(os.path.join(temp_dir, f"*_{unique_id}.*")):
                os.remove(tmp_file)
        except Exception:
            pass
        raise e
