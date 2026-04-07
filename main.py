import os
import logging
import itertools
import discord
import json
import time
import asyncio
import re
from discord.ext import commands, tasks
from dotenv import load_dotenv
from aiohttp import web

# Import our UI architecture
from ui import DashboardView

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MediaBot")

# --- CONFIGURATION LOADING ---
try:
    with open("config.json", "r") as f:
        CONFIG = json.load(f)
except Exception as e:
    logger.warning(f"Could not load config.json: {e}. Using hardcoded defaults.")
    CONFIG = {
        "CHANNEL_ID": 1491040447370362980,
        "STATUS_ROTATION_SPEED": 10,
        "LINK_REGEX": r'(https?://)?(www\.)?(youtube\.com|youtu\.be|tiktok\.com|twitter\.com|x\.com|instagram\.com)/[^\s]+',
        "BASE_URL": "http://localhost:8080"
    }

CHANNEL_ID = CONFIG.get("CHANNEL_ID")
LINK_REGEX = CONFIG.get("LINK_REGEX")

class MediaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        
        self.activities = itertools.cycle([
            discord.Activity(type=discord.ActivityType.watching, name="over the Dashboard ✨"),
            discord.Activity(type=discord.ActivityType.listening, name="to 🎵 Audio extractions"),
            discord.Activity(type=discord.ActivityType.playing, name="🎬 with Media files"),
            discord.Activity(type=discord.ActivityType.watching, name="out for new Links 🚀")
        ])

    async def on_message(self, message):
        if message.author == self.user:
            return

        if message.channel.id == CHANNEL_ID:
            if re.search(LINK_REGEX, message.content, re.IGNORECASE):
                logger.info(f"Media link detected from {message.author}: {message.content}")
                prompt_text = (
                    f"👋 Hello, {message.author.display_name}! I noticed you shared a media link.\n"
                    "Would you like me to process that for you? Just pick a format below! 🚀"
                )
                await message.reply(prompt_text, view=DashboardView(), delete_after=300)

        await self.process_commands(message)

    async def setup_hook(self):
        self.add_view(DashboardView())
        
        # Start the Static File Server
        await self.start_web_server()
        
        await self.tree.sync()
        logger.info("Bot setup complete. All services registered.")

    async def start_web_server(self):
        """Starts a clean static file server for self-hosting large files."""
        app = web.Application()
        # Serve the /downloads folder at the /dl/ path
        app.router.add_static('/dl/', os.path.join(os.getcwd(), 'downloads'), show_index=False)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        await site.start()
        logger.info("Static file server listening on port 8080.")

    @tasks.loop(seconds=10)
    async def status_task(self):
        await self.change_presence(activity=next(self.activities))

    @tasks.loop(hours=24)
    async def cleanup_task(self):
        """Background maintenance with 24-hour retention."""
        temp_dir = os.path.join(os.getcwd(), "downloads")
        if not os.path.exists(temp_dir):
            return
            
        logger.info("Starting maintenance cleanup...")
        count = 0
        now = time.time()
        
        try:
            for filename in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, filename)
                if os.path.isfile(file_path):
                    # Delete files older than 24 hours (86400 seconds)
                    if now - os.path.getmtime(file_path) > 86400:
                        os.remove(file_path)
                        count += 1
            if count > 0:
                logger.info(f"Cleanup complete. Deleted {count} legacy files.")
        except Exception as e:
            logger.error(f"Cleanup task failed: {e}")

    async def on_ready(self):
        logger.info(f"Bot is online as {self.user}")
        
        rotation_speed = CONFIG.get("STATUS_ROTATION_SPEED", 10)
        self.status_task.change_interval(seconds=rotation_speed)

        if not self.status_task.is_running():
            self.status_task.start()
        
        if not self.cleanup_task.is_running():
            self.cleanup_task.start()

        # Dashboard posting logic remains exactly as is...
        channel = self.get_channel(CHANNEL_ID)
        if channel:
            try:
                await channel.purge(limit=100)
            except Exception:
                pass
                
            dash_embed = discord.Embed(
                title="📥 Fetchy | Your Personal Media Assistant",
                description=(
                    "I am here to assist you with high-performance media extraction and management. "
                    "Enjoy a fully private and anonymous experience across all your interactions.\n\n"
                    "**How to get started:**\n"
                    "1. Select a **format** below (Video, Audio, or Picture).\n"
                    "2. Provide the **source link** in the secure input field.\n"
                    "3. Choose your **quality/format** and I'll handle the rest! 🚀\n\n\n"
                    "✨ **Key Benefits:** High Performance • Large File Support • Zero Tracking\n\n"
                    "🖥️ **Source Code:** [GitHub Repository](https://github.com/CRZX1337/Fetchy)"
                ),
                color=discord.Color.blurple()
            )
            dash_embed.set_thumbnail(url="https://raw.githubusercontent.com/CRZX1337/Fetchy/main/media/logo.png")
            dash_embed.set_footer(text="Handcrafted for efficiency • System fully operational")
            await channel.send(embed=dash_embed, view=DashboardView())
            logger.info("Dashboard posted.")

if __name__ == "__main__":
    load_dotenv()
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        logger.error("No token found!")
    else:
        bot = MediaBot()
        bot.run(TOKEN)
