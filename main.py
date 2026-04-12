import discord
import logging
import os
import asyncio
import aiohttp
import time
import sys
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
import ui
import downloader
import file_server
from constants import BOT_NAME

# --- TOKEN-AUTHENTICATED FILE SERVER ---
async def _handle_download(request: web.Request) -> web.Response:
    token = request.rel_url.query.get("token")
    if not token:
        return web.Response(status=403, content_type="application/json", text='{"error": "Missing token"}')
    entry = file_server._file_tokens.get(token)
    if entry is None:
        return web.Response(status=403, content_type="application/json", text='{"error": "Invalid token"}')
    filepath, expiry = entry
    if time.time() > expiry:
        del file_server._file_tokens[token]
        return web.Response(status=403, content_type="application/json", text='{"error": "Token expired"}')
    return web.FileResponse(filepath)


async def start_server():
    app = web.Application()
    app.router.add_get('/downloads', _handle_download)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logger.info("Token-authenticated file server started on port 8080.")


async def auto_update_ytdlp():
    try:
        import yt_dlp
        old_version = yt_dlp.version.__version__
        logger.info(f"yt-dlp current version: {old_version} — checking for updates...")

        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pip", "install", "-U", "yt-dlp",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            import importlib
            importlib.reload(yt_dlp.version)
            new_version = yt_dlp.version.__version__
            if new_version != old_version:
                logger.info(f"yt-dlp updated: {old_version} -> {new_version}")
            else:
                logger.info(f"yt-dlp is already up to date ({new_version})")
        else:
            logger.warning(f"yt-dlp update failed (exit {proc.returncode}): {stderr.decode().strip()}")
    except Exception as e:
        logger.warning(f"yt-dlp auto-update skipped: {e}")


def build_dashboard_embed() -> discord.Embed:
    embed = discord.Embed(
        title=f"📥 {BOT_NAME} — Media Downloader",
        description="Your personal, private media assistant. Drop a link or pick a format below.",
        color=discord.Color.blurple()
    )
    embed.add_field(
        name="⚡ How to use",
        value=(
            "1️⃣ Paste a media link in this channel, **or**\n"
            "2️⃣ Click a format button below and enter the URL manually."
        ),
        inline=False
    )
    embed.add_field(
        name="🎯 Supported formats",
        value="🎥 Video · 🎵 Audio · 🖼️ Picture",
        inline=False
    )
    embed.add_field(
        name="✂️ New: Audio Trim",
        value="Pick Audio → choose format → set start/end time!",
        inline=False
    )
    embed.add_field(
        name="🎬 New: /clip",
        value="Cut any video/audio to a specific timestamp range!",
        inline=False
    )
    embed.add_field(
        name="✨ Features",
        value="Private · Large file support · Zero tracking",
        inline=False
    )
    embed.add_field(
        name="🖥️ Source",
        value="[GitHub Repository](https://github.com/CRZX1337/Fetchy)",
        inline=False
    )
    embed.set_thumbnail(url="https://raw.githubusercontent.com/CRZX1337/Fetchy/main/media/logo.png")
    embed.set_footer(text="Handcrafted for efficiency · System fully operational")
    return embed


class MediaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.status_index = 0
        self.statuses = [
            "Watching for links... 🔍",
            "Ready to download! 🎥",
            "Helping users fetch media! ✨",
            "Type a link to get started! 🔗",
            "Try /clip to cut a video! ✂️",
        ]
        self._dashboard_posted = False

    async def setup_hook(self):
        await auto_update_ytdlp()
        self.add_view(DashboardView())
        self.status_rotation.start()
        self.cleanup_task.start()
        await start_server()

        from cogs.general import General
        from cogs.admin import Admin
        await self.add_cog(General(self))
        await self.add_cog(Admin(self))

        # Register /clip slash command
        @self.tree.command(name="clip", description="✂️ Download a clip from any URL with start/end timestamps")
        @discord.app_commands.describe(
            url="The media URL (YouTube, TikTok, etc.)",
            start="Start time, e.g. 1:30 or 90",
            end="End time, e.g. 2:45 or 165",
            format="Output format: mp4 (video) or mp3/wav/m4a (audio)",
        )
        async def clip_command(
            interaction: discord.Interaction,
            url: str,
            start: str,
            end: str,
            format: str = "mp4",
        ):
            if not ui.is_valid_url(url):
                await interaction.response.send_message("❌ Invalid URL.", ephemeral=True)
                return

            start_sec = downloader._parse_timestamp(start)
            end_sec = downloader._parse_timestamp(end)

            if start_sec is None:
                await interaction.response.send_message(
                    "❌ Invalid start time. Use format `1:30` or `90`.", ephemeral=True
                )
                return
            if end_sec is None:
                await interaction.response.send_message(
                    "❌ Invalid end time. Use format `2:45` or `165`.", ephemeral=True
                )
                return
            if end_sec <= start_sec:
                await interaction.response.send_message(
                    "❌ End time must be after start time.", ephemeral=True
                )
                return

            format = format.lower().strip()
            if format in ("mp4", "webm"):
                format_type = "video"
                extension = "mp3"  # not used for video
            else:
                format_type = "audio"
                extension = format if format in ("mp3", "wav", "flac", "m4a") else "mp3"

            platform = downloader.get_platform(url)
            await interaction.response.send_message(
                f"{platform['emoji']} **Clipping** `{start}` → `{end}` from {platform['name']}...",
                ephemeral=True
            )

            await ui.process_action(
                interaction, url, format_type,
                quality="1080",
                extension=extension,
                start_time=start,
                end_time=end,
            )

        await self.tree.sync()
        logger.info("Slash commands synced.")
        logger.info("Bot setup completed.")

    @tasks.loop(seconds=CONFIG.get("STATUS_ROTATION_SPEED", 10))
    async def status_rotation(self):
        await self.change_presence(activity=discord.Game(name=self.statuses[self.status_index]))
        self.status_index = (self.status_index + 1) % len(self.statuses)

    @tasks.loop(hours=1)
    async def cleanup_task(self):
        logger.info("Running cleanup task...")
        count = 0
        downloads_dir = "downloads"
        if os.path.exists(downloads_dir) and any(os.scandir(downloads_dir)):
            for filename in os.listdir(downloads_dir):
                file_path = os.path.join(downloads_dir, filename)
                try:
                    if os.path.isfile(file_path):
                        if time.time() - os.path.getmtime(file_path) > 3600:
                            os.remove(file_path)
                            count += 1
                except Exception as e:
                    logger.error(f"Failed to delete {file_path}: {e}")
            logger.info(f"Cleanup finished. Deleted {count} files.")
        else:
            logger.info("Cleanup skipped: downloads/ is empty or does not exist.")

        ui_summary = ui.cleanup_stale_state(time.time())
        logger.info(
            f"UI state cleanup: {ui_summary['cooldowns_cleared']} cooldowns, "
            f"{ui_summary['stale_downloads_cleared']} stale download counters cleared."
        )

        now = time.time()
        expired_tokens = [t for t, (_, exp) in file_server._file_tokens.items() if now > exp]
        for t in expired_tokens:
            del file_server._file_tokens[t]
        logger.info(f"Cleared {len(expired_tokens)} expired file tokens.")

    @status_rotation.before_loop
    async def before_status_rotation(self):
        await self.wait_until_ready()

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Targeting Channel ID: {CONFIG['CHANNEL_ID']}")

        if self._dashboard_posted:
            logger.info("on_ready fired again (reconnect) — skipping dashboard repost.")
            return

        channel = self.get_channel(CONFIG["CHANNEL_ID"])
        if channel:
            if channel.permissions_for(channel.guild.me).manage_messages:
                try:
                    await channel.purge(limit=100)
                except Exception as exc:
                    logger.warning(f"channel.purge() failed even with permission: {exc}")
            else:
                logger.warning(
                    "Skipping startup purge: bot lacks 'Manage Messages' in "
                    f"channel {channel.id}."
                )
            await channel.send(embed=build_dashboard_embed(), view=DashboardView())
            self._dashboard_posted = True
            logger.info("Dashboard posted successfully.")

    async def on_message(self, message):
        if message.author == self.user:
            return

        if message.channel.id == CONFIG['CHANNEL_ID']:
            if re.search(CONFIG['LINK_REGEX'], message.content):
                view = DashboardView(url=message.content, trigger_message_id=message.id)
                await message.reply(
                    f"Hey {message.author.display_name}! I spotted a media link — pick a format to download it! 🚀",
                    view=view
                )

        await self.process_commands(message)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        raise error


# --- BOT ENTRYPOINT ---
if __name__ == "__main__":
    load_dotenv()
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        legacy_token = os.getenv("DISCORD_TOKEN")
        if legacy_token:
            logger.warning(
                "DISCORD_TOKEN is deprecated. Please rename it to DISCORD_BOT_TOKEN "
                "in your .env file. Falling back for this session."
            )
            token = legacy_token
    if not token:
        logger.critical("No DISCORD_BOT_TOKEN found in your .env file!")
    else:
        bot = MediaBot()
        bot.run(token)
