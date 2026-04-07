import os
import logging
import itertools
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# Import our clean UI architecture
from ui import DashboardView

load_dotenv()

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MediaBot")

CHANNEL_ID = 1491040447370362980

class MediaBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        
        # Rotating status activities
        self.activities = itertools.cycle([
            discord.Activity(type=discord.ActivityType.watching, name="over the Dashboard ✨"),
            discord.Activity(type=discord.ActivityType.listening, name="to 🎵 Audio extractions"),
            discord.Activity(type=discord.ActivityType.playing, name="🎬 with Media files"),
            discord.Activity(type=discord.ActivityType.watching, name="out for new Links 🚀")
        ])

    async def setup_hook(self):
        # 1. Essential for keeping button functionality after bot restarts:
        self.add_view(DashboardView())
        
        # Synchronize (or clear) old slash commands
        await self.tree.sync()
        logger.info("Bot setup complete. Dashboard View registered successfully.")

    @tasks.loop(seconds=10)
    async def status_task(self):
        """Task to rotate bot status every 10 seconds."""
        await self.change_presence(activity=next(self.activities))

    async def on_ready(self):
        logger.info(f"Bot is online as {self.user} (ID: {self.user.id})")
        
        # Start the background status task if it's not already running
        if not self.status_task.is_running():
            self.status_task.start()
            logger.info("Dynamic status rotation started.")
        
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
