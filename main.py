import os
import logging
import itertools
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# Import our clean UI architecture
from ui import DashboardView

import re
import json
import time

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
        "LINK_REGEX": r'(https?://)?(www\.)?(youtube\.com|youtu\.be|tiktok\.com|twitter\.com|x\.com|instagram\.com)/[^\s]+'
    }

CHANNEL_ID = CONFIG.get("CHANNEL_ID")
LINK_REGEX = CONFIG.get("LINK_REGEX")

class MediaBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all()) # Enabled all intents for on_message
        
        # Rotating status activities
        self.activities = itertools.cycle([
            discord.Activity(type=discord.ActivityType.watching, name="over the Dashboard ✨"),
            discord.Activity(type=discord.ActivityType.listening, name="to 🎵 Audio extractions"),
            discord.Activity(type=discord.ActivityType.playing, name="🎬 with Media files"),
            discord.Activity(type=discord.ActivityType.watching, name="out for new Links 🚀")
        ])

    async def on_message(self, message):
        # 1. Ignore own messages
        if message.author == self.user:
            return

        # 2. Only watch the designated Dashboard Channel
        if message.channel.id == CHANNEL_ID:
            # 3. Detect media links using regex
            if re.search(LINK_REGEX, message.content, re.IGNORECASE):
                logger.info(f"Media link detected from {message.author}: {message.content}")
                
                # Send a friendly prompt with the dashboard interaction buttons
                prompt_text = (
                    f"👋 Hello, {message.author.display_name}! I noticed you shared a media link.\n"
                    "Would you like me to process that for you? Just pick a format below! 🚀"
                )
                await message.reply(prompt_text, view=DashboardView(), delete_after=300) # Auto-delete prompt after 5 mins

        # 4. Mandatory for commands to continue working (if any)
        await self.process_commands(message)

    async def setup_hook(self):
        # 1. Essential for keeping button functionality after bot restarts:
        self.add_view(DashboardView())
        
        # Synchronize (or clear) old slash commands
        await self.tree.sync()
        logger.info("Bot setup complete. Dashboard View registered successfully.")

    @tasks.loop(seconds=10)
    async def status_task(self):
        """Task to rotate bot status."""
        await self.change_presence(activity=next(self.activities))

    @tasks.loop(hours=24)
    async def cleanup_task(self):
        """Background task to clean up old files in the downloads directory."""
        temp_dir = os.path.join(os.getcwd(), "downloads")
        if not os.path.exists(temp_dir):
            return
            
        logger.info("Starting automated background cleanup...")
        count = 0
        now = time.time()
        
        try:
            for filename in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, filename)
                if os.path.isfile(file_path):
                    # If file is older than 1 hour (3600 seconds)
                    if now - os.path.getmtime(file_path) > 3600:
                        os.remove(file_path)
                        count += 1
            if count > 0:
                logger.info(f"Cleanup complete. Deleted {count} abandoned files.")
        except Exception as e:
            logger.error(f"Cleanup task failed: {e}")

    async def on_ready(self):
        logger.info(f"Bot is online as {self.user} (ID: {self.user.id})")
        
        # Adjust rotation speed from config
        rotation_speed = CONFIG.get("STATUS_ROTATION_SPEED", 10)
        self.status_task.change_interval(seconds=rotation_speed)

        # Start the background tasks
        if not self.status_task.is_running():
            self.status_task.start()
        
        if not self.cleanup_task.is_running():
            self.cleanup_task.start()
            logger.info("Maintenance cleanup task scheduled every 24 hours.")
        
        # 2. Setup the dedicated Dashboard Channel
        channel = self.get_channel(CHANNEL_ID)
        if channel:
            # Purge clears old messages entirely from the channel
            try:
                await channel.purge(limit=100)
                logger.info(f"Channel {CHANNEL_ID} was successfully purged.")
            except discord.Forbidden:
                logger.error("Missing permissions to delete messages in this channel.")
            except Exception as e:
                logger.error(f"Error purging the channel: {e}")
                
            # Permanent Dashboard Setup
            dash_embed = discord.Embed(
                title="📥 Fetchy | Your Personal Media Assistant",
                description=(
                    "I am here to assist you with high-performance media extraction and management. "
                    "Enjoy a fully private and anonymous experience across all your interactions. ✨\n\n"
                    "**How to get started:**\n"
                    "1. Select a **format** below (Video, Audio, or Picture).\n"
                    "2. Provide the **source link** in the secure input field.\n"
                    "3. Relax while I process and deliver your requested file! 🚀\n\n\n"
                    "✨ **Key Benefits:** High Performance • Secure Processing • Zero Tracking\n\n"
                    "🖥️ **Source Code:** [GitHub Repository](https://github.com/CRZX1337/Fetchy)"
                ),
                color=discord.Color.blurple()
            )
            dash_embed.set_thumbnail(url="https://raw.githubusercontent.com/CRZX1337/Fetchy/main/media/logo.png")
            dash_embed.set_footer(text="Handcrafted for efficiency • System fully operational")
            
            # Send the View/Embed back into the cleaned channel
            await channel.send(embed=dash_embed, view=DashboardView())
            logger.info("Dashboard successfully posted to the channel.")
        else:
            logger.error(f"ERROR: Channel with ID {CHANNEL_ID} was not found on this server!")

# --- BOT ENTRYPOINT ---
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        logger.error("No token found! Please check your DISCORD_BOT_TOKEN.")
    else:
        bot = MediaBot()
        bot.run(TOKEN)
