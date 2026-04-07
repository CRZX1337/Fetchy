import discord
import logging
import os
import asyncio
import aiohttp
import time
from aiohttp import web
from discord.ext import commands, tasks
import re
from dotenv import load_dotenv

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MediaBot.Main")

# --- CUSTOM MODULES ---
from config import CONFIG
from ui import DashboardView, SupportInformationEmbed
import downloader
from constants import BOT_NAME

# --- STATIC SERVER SETTING ---
async def start_server():
    """Starts a simple aiohttp server to host files locally."""
    app = web.Application()
    app.router.add_static('/downloads/', 'downloads/')
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logger.info("Static file server started on port 8080.")

class MediaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.status_index = 0
        self.statuses = [
            "Watching for links... 🔍",
            "Ready to download! 📽️",
            "Helping users fetch media! ✨",
            "Type a link to get started! 🔗"
        ]

    async def setup_hook(self):
        self.add_view(DashboardView())
        self.status_rotation.start()
        self.cleanup_task.start()
        await start_server()
        
        from cogs.general import General
        from cogs.admin import Admin
        await self.add_cog(General(self))
        await self.add_cog(Admin(self))
        
        logger.info("Bot setup completed.")

    @tasks.loop(seconds=CONFIG.get("STATUS_ROTATION_SPEED", 10))
    async def status_rotation(self):
        await self.change_presence(activity=discord.Game(name=self.statuses[self.status_index]))
        self.status_index = (self.status_index + 1) % len(self.statuses)

    @tasks.loop(hours=24)
    async def cleanup_task(self):
        logger.info("Running 24-hour cleanup task...")
        count = 0
        if os.path.exists("downloads"):
            for filename in os.listdir("downloads"):
                file_path = os.path.join("downloads", filename)
                try:
                    if os.path.isfile(file_path):
                        if time.time() - os.path.getmtime(file_path) > 86400:
                            os.remove(file_path)
                            count += 1
                except Exception as e:
                    logger.error(f"Failed to delete {file_path}: {e}")
        logger.info(f"Cleanup finished. Deleted {count} files.")

    @status_rotation.before_loop
    async def before_status_rotation(self):
        await self.wait_until_ready()

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Targeting Channel ID: {CONFIG['CHANNEL_ID']}")
        channel = self.get_channel(CONFIG["CHANNEL_ID"])
        if channel:
            try:
                await channel.purge(limit=100)
            except Exception:
                pass
            embed = discord.Embed(
                title=f"📥 {BOT_NAME} | Your Personal Media Assistant",
                description="I am here to assist you with high-performance media extraction and management. Enjoy a fully private and anonymous experience across all your interactions.\n\nHow to get started:\n1. Select a format below (Video, Audio, or Picture).\n2. Provide the source link in the secure input field.\n3. Choose your quality/format and I'll handle the rest! 🚀\n\n\n✨ Key Benefits: High Performance - Large File Support - Zero Tracking\n\n🖥️ Source Code: [GitHub Repository](https://github.com/CRZX1337/Fetchy)",
                color=discord.Color.blurple()
            )
            embed.set_thumbnail(url="https://raw.githubusercontent.com/CRZX1337/Fetchy/main/media/logo.png")
            embed.set_footer(text="Handcrafted for efficiency - System fully operational")
            await channel.send(embed=embed, view=DashboardView())
            logger.info("Dashboard posted successfully.")

    async def on_message(self, message):
        if message.author == self.user:
            return

        # Auto-detect media links in the designated channel
        if message.channel.id == CONFIG['CHANNEL_ID']:
            if re.search(CONFIG['LINK_REGEX'], message.content):
                view = DashboardView(url=message.content, trigger_message_id=message.id)
                await message.reply(
                    f"Hello, {message.author.display_name}! I noticed you shared a media link.\n"
                    "Would you like me to process that for you? Just pick a format below! 🚀",
                    view=view
                )

        await self.process_commands(message)

    async def on_command_error(self, ctx, error):
        """Silently ignore unknown !commands."""
        if isinstance(error, commands.CommandNotFound):
            return
        raise error

# --- BOT ENTRYPOINT ---
if __name__ == "__main__":
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.critical("No DISCORD_TOKEN or DISCORD_BOT_TOKEN found in your .env file!")
    else:
        bot = MediaBot()
        bot.run(token)