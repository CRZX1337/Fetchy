import os
import uuid
import glob
import logging
import asyncio

import discord
from discord.ext import commands
from dotenv import load_dotenv
import yt_dlp

# Lade lokale .env Datei in die Umgebungsvariablen
load_dotenv()

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MediaBot")

# Die fest definierte Dashboard-Kanal-ID
CHANNEL_ID = 1491040447370362980

# --- HELPER FUNKTION ---
def download_media(url: str, format_type: str) -> str:
    """Lädt Dateien synchron via yt-dlp herunter. Ausführung in einem Background-Thread."""
    job_id = uuid.uuid4().hex
    temp_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(temp_dir, exist_ok=True)
    
    filepath_prefix = os.path.join(temp_dir, job_id)
    
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
            ydl.download([url])
            
        files = glob.glob(f"{filepath_prefix}.*")
        
        if not files:
            raise Exception("Keine Zieldatei gefunden. Evtl. ist der Post privat oder die Plattform blockiert.")
            
        files.sort(key=os.path.getmtime, reverse=True)
        return files[0]
        
    except Exception as e:
        for tmp_file in glob.glob(f"{filepath_prefix}.*"):
            try:
                os.remove(tmp_file)
            except:
                pass
        raise e

# --- UI KOMPONENTEN ---
class FormatSelect(discord.ui.Select):
    def __init__(self, url: str):
        self.url = url
        options = [
            discord.SelectOption(label="Video (MP4)", description="Bestes Video + Audio", emoji="🎬", value="video"),
            discord.SelectOption(label="Audio (MP3)", description="Nur Audio extrahieren", emoji="🎵", value="audio"),
            discord.SelectOption(label="Thumbnail (PNG)", description="Nur das Vorschaubild laden", emoji="🖼️", value="thumbnail")
        ]
        super().__init__(placeholder="Wähle das Ziel-Format...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        # UI Status "Warten" setzen und Dropdown deaktivieren
        self.disabled = True
        selected_format = self.values[0]
        format_labels = {"video": "Video", "audio": "Audio", "thumbnail": "Thumbnail"}
        
        embed = interaction.message.embeds[0]
        embed.title = f"⏳ Download ({format_labels[selected_format]}) wird verarbeitet..."
        embed.description = "Bitte warten, der Download läuft im Hintergrund."
        embed.color = discord.Color.yellow()  
        
        await interaction.response.edit_message(embed=embed, view=self.view)
        
        file_path = None
        try:
            # yt-dlp muss zwingend unblockierend in separatem Thread laufen
            file_path = await asyncio.to_thread(download_media, self.url, selected_format)
            
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb > 25:
                embed.title = "❌ Download fehlgeschlagen"
                embed.description = f"Die Datei ist **{file_size_mb:.2f} MB** groß.\nStandard Discord Upload-Limit ist 25 MB."
                embed.color = discord.Color.red()
                await interaction.edit_original_response(embed=embed, view=None)
            else:
                embed.title = "✅ Download erfolgreich!"
                embed.description = f"Dein **{format_labels[selected_format]}** ist fertig."
                embed.color = discord.Color.green()
                
                # Datei an die (ephemerale) Original-Response anhängen
                discord_file = discord.File(file_path)
                await interaction.edit_original_response(embed=embed, view=None, attachments=[discord_file])
                
        except Exception as e:
            logger.error(f"Download Error für {self.url}: {str(e)}")
            embed.title = "❌ Es ist ein Fehler aufgetreten"
            embed.description = f"Beim Verarbeiten der Anfrage ist ein Fehler aufgetreten:\n```{str(e)[:700]}```"
            embed.color = discord.Color.red()
            await interaction.edit_original_response(embed=embed, view=None)
            
        finally:
            # Zwingendes Cleanup unabhängig von Erfolg/Fehler
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Cleanup erfolgreich: {file_path}")
                except Exception as cleanup_err:
                    logger.error(f"Fehler beim Dateicache löschen: {cleanup_err}")

class DownloadView(discord.ui.View):
    def __init__(self, url: str):
        super().__init__(timeout=300) # View bleibt zur Auswahl 5 min aktiv (ephemeral unproblematisch)
        self.add_item(FormatSelect(url))


class DownloadModal(discord.ui.Modal, title='Medien Link eingeben'):
    # Text-Input für die Modal View
    url_input = discord.ui.TextInput(
        label='Video- / Audio-URL',
        style=discord.TextStyle.short,
        placeholder='https://www...',
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Vom User eigegebene URL greifen
        url = self.url_input.value
        
        embed = discord.Embed(
            title="📥 Format wählen",
            description=f"Quelle: `{url}`\nWähle das gewünschte Format im Dropdown-Menü.",
            color=discord.Color.blurple()
        )
        view = DownloadView(url)
        
        # WICHTIG: Die gesamte weitere Interaktion passiert ab hier zwingend ephemeral (unsichtbar)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class DashboardView(discord.ui.View):
    def __init__(self):
        # Das Timeout MUSS None sein, damit Component Listeners unendlich aktiv bleiben
        super().__init__(timeout=None) 
        
    @discord.ui.button(label="Medium herunterladen", style=discord.ButtonStyle.green, custom_id="persistent_dashboard_btn", emoji="⬇️")
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Callback für den Button öffnet das Modal
        await interaction.response.send_modal(DownloadModal())

# --- BOT SETUP ---
class MediaBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self):
        # ZWINGEND: Persistenz der View sicherstellen
        self.add_view(DashboardView())
        logger.info("Dashboard View wurde instanziiert und dem System hinzugefügt.")

    async def on_ready(self):
        logger.info(f"Bot ist online als {self.user} (ID: {self.user.id})")
        
        # 1. Dashboard Kanal holen
        channel = self.get_channel(CHANNEL_ID)
        if channel:
            # 2. Den bisherigen Channel leeren um Sauberkeit sicherzustellen
            try:
                await channel.purge(limit=100)
                logger.info(f"Channel '{channel.name}' wurde erfolgreich gesäubert.")
            except discord.Forbidden:
                logger.error("Keine Rechte, Nachrichten in dem Channel zu löschen!")
            except Exception as e:
                logger.error(f"Fehler beim Aufräumen des Channels: {e}")
                
            # 3. Das persistente UI / Die Zentrale aufbauen
            dash_embed = discord.Embed(
                title="📥 Media Downloader Dashboard",
                description=(
                    "Willkommen im Downloader-Zentrum!\n\n"
                    "Klicke auf den **grünen Button unten**, um einen Link von Plattformen wie "
                    "`YouTube`, `TikTok`, `Twitter/X` oder `Reddit` zu hinterlegen.\n\n"
                    "💡 *Keine Sorge, deine Vorgänge sind für niemanden in diesem Channel sichtbar.*"
                ),
                color=discord.Color.blurple()
            )
            dash_embed.set_footer(text="Vollautomatisiert, Clean & High Quality")
            
            # Postet das Dashboard zusammen mit unserem persistierendem Button
            await channel.send(embed=dash_embed, view=DashboardView())
        else:
            logger.error(f"Initialisierung fehlgeschlagen. Kein Channel mit der ID {CHANNEL_ID} zugänglich!")
            
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="dem Dashboard zu"))


bot = MediaBot()

# --- BOT ENTRYPOINT ---
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        logger.error("Kein Token gefunden! Bitte DISCORD_BOT_TOKEN Umgebungsvariable befüllen.")
    else:
        bot.run(TOKEN)
