import os
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Importiere unsere saubere UI Architektur
from ui import DashboardView

load_dotenv()

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MediaBot")

CHANNEL_ID = 1491040447370362980

class MediaBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self):
        # 1. Zwingend für die Erhaltung der Button-Funktionalität nach Bot-Neustarts:
        self.add_view(DashboardView())
        
        # Synchronisiere (bzw. lösche) Slash-Commands, falls alte gelistet sind
        await self.tree.sync()
        logger.info("Bot Setup abgeschlossen, Dashboard View registriert.")

    async def on_ready(self):
        logger.info(f"Bot ist online als {self.user} (ID: {self.user.id})")
        
        # 2. Setup des dedizierten Dashboard Channels
        channel = self.get_channel(CHANNEL_ID)
        if channel:
            # Purge löscht alte Nachrichten vollständig aus dem Channel
            try:
                await channel.purge(limit=100)
                logger.info(f"Kanal {CHANNEL_ID} wurde komplett bereinigt (purged).")
            except discord.Forbidden:
                logger.error("Keine Rechte vorhanden, um Nachrichten in diesem Channel zu löschen.")
            except Exception as e:
                logger.error(f"Fehler beim Purgen des Channels: {e}")
                
            # Permanentes Dashboard Setup
            dash_embed = discord.Embed(
                title="📥 Media Downloader Dashboard",
                description=(
                    "Willkommen am Kontrollzentrum!\n\n"
                    "Hier bleibt alles für immer 100% anonym und sauber. Klicke einfach auf einen der "
                    "**drei Buttons unten**, um das gewünschte Format (Video, Audio oder Thumbnail) "
                    "zu wählen und füge dann deine Video-URL ein.\n\n"
                    "*(Deine Downloads laden kollisionsfrei im Hintergrund und werden dir komplett unsichtbar (ephemeral) zurückgesendet!)*"
                ),
                color=discord.Color.blurple()
            )
            dash_embed.set_footer(text="Vollautomatisiert, Clean & Modular")
            
            # Sende das View/Embed zurück in den gesäuberten Channel
            await channel.send(embed=dash_embed, view=DashboardView())
            logger.info("Dashboard erfolgreich in den Kanal gepostet.")
        else:
            logger.error(f"FEHLER: Channel mit der ID {CHANNEL_ID} wurde auf dem Server nicht gefunden!")
            
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="dem Dashboard zu"))

# --- BOT ENTRYPOINT ---
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        logger.error("Kein Token gefunden! Bitte DISCORD_BOT_TOKEN prüfen.")
    else:
        bot = MediaBot()
        bot.run(TOKEN)
