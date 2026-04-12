import discord
import logging
import asyncio
import threading
import os
import time
import urllib.parse
from collections import defaultdict
from config import CONFIG
import downloader
from constants import BOT_NAME
from file_server import generate_file_token


def is_valid_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


# --- LOGGING SETUP ---
logger = logging.getLogger("MediaBot.UI")

# --- RATE LIMITING ---
active_downloads = {}
MAX_CONCURRENT_PER_USER = 2
_user_cooldowns: dict[int, float] = {}
COOLDOWN_SECONDS = 30

# --- PER-USER DOWNLOAD QUEUE ---
_user_queues: dict[int, asyncio.Queue] = defaultdict(lambda: asyncio.Queue())
_queue_workers: dict[int, asyncio.Task] = {}
MAX_QUEUE_PER_USER = 3


def check_cooldown(user_id: int) -> int | None:
    elapsed = time.time() - _user_cooldowns.get(user_id, 0)
    return int(COOLDOWN_SECONDS - elapsed) if elapsed < COOLDOWN_SECONDS else None


def cleanup_stale_state(now: float) -> dict:
    expired_cooldowns = [
        uid for uid, t in _user_cooldowns.items() if now - t > COOLDOWN_SECONDS
    ]
    for uid in expired_cooldowns:
        del _user_cooldowns[uid]

    stale_slots = [uid for uid, count in active_downloads.items() if count <= 0]
    for uid in stale_slots:
        del active_downloads[uid]

    return {
        "cooldowns_cleared": len(expired_cooldowns),
        "stale_downloads_cleared": len(stale_slots),
    }


def _is_instagram_post(url: str) -> bool:
    return any(p in url for p in (
        "instagram.com/p/",
        "instagram.com/reel/",
        "instagram.com/reels/",
        "instagram.com/stories/",
    ))


def _platform_embed_color(url: str) -> int:
    """Returns a hex color int for the platform of the given URL."""
    return downloader.get_platform(url)["color"]


def _platform_footer(url: str) -> str:
    """Returns a footer string with platform emoji + name."""
    p = downloader.get_platform(url)
    return f"{p['emoji']} {p['name']}"


# ─────────────────────────────────────────────
#  QUEUE WORKER
# ─────────────────────────────────────────────

async def _queue_worker(user_id: int):
    queue = _user_queues[user_id]
    while True:
        job = await queue.get()
        try:
            await job()
        except Exception as e:
            logger.error(f"Queue job error for user {user_id}: {e}")
        finally:
            queue.task_done()
        if queue.empty():
            _queue_workers.pop(user_id, None)
            break


async def _enqueue_download(user_id: int, job_coro_fn, position_callback=None):
    queue = _user_queues[user_id]
    if queue.qsize() >= MAX_QUEUE_PER_USER:
        return False

    position = queue.qsize() + 1
    await queue.put(job_coro_fn)

    if position_callback and position > 1:
        await position_callback(position)

    if user_id not in _queue_workers or _queue_workers[user_id].done():
        _queue_workers[user_id] = asyncio.create_task(_queue_worker(user_id))

    return True


# ─────────────────────────────────────────────
#  PREVIEW
# ─────────────────────────────────────────────

class PreviewView(discord.ui.View):
    def __init__(self, url: str, format_type: str, quality: str = "1080",
                 extension: str = None, trigger_message_id: int = None,
                 prompt_message_id: int = None,
                 start_time: str = None, end_time: str = None):
        super().__init__(timeout=60)
        self.url = url
        self.format_type = format_type
        self.quality = quality
        self.extension = extension
        self.trigger_message_id = trigger_message_id
        self.prompt_message_id = prompt_message_id
        self.start_time = start_time
        self.end_time = end_time
        self._confirmed = False

    @discord.ui.button(label="⬇️ Download", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._confirmed = True
        self.stop()
        await interaction.response.edit_message(
            content="⏳ Starting download...", embed=None, view=None
        )
        await process_action(
            interaction, self.url, self.format_type,
            quality=self.quality, extension=self.extension,
            trigger_message_id=self.trigger_message_id,
            prompt_message_id=self.prompt_message_id,
            start_time=self.start_time,
            end_time=self.end_time,
        )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(
            content="❌ Download cancelled.", embed=None, view=None
        )

    async def on_timeout(self):
        if not self._confirmed:
            self.stop()


async def show_preview(interaction: discord.Interaction, url: str, format_type: str,
                       quality: str = "1080", extension: str = None,
                       trigger_message_id: int = None, prompt_message_id: int = None,
                       start_time: str = None, end_time: str = None):
    if not interaction.response.is_done():
        await interaction.response.send_message("🔍 **Fetching preview...** Please wait.", ephemeral=True)

    info = await asyncio.to_thread(downloader.get_preview_info, url)
    if not info:
        await interaction.edit_original_response(content="❌ Couldn't fetch preview. Try downloading directly.")
        return

    if info['is_playlist']:
        await interaction.edit_original_response(
            content=(
                f"💼 **Playlist detected:** *{info['title']}*\n"
                f"📀 **{info['playlist_count']} tracks** — Downloading all now..."
            ),
            view=None
        )
        await handle_playlist_download(
            interaction, url, format_type, quality, extension or "mp3"
        )
        return

    platform = downloader.get_platform(url)
    title_short = info['title'][:60] + "..." if len(info['title']) > 60 else info['title']

    embed = discord.Embed(
        title=f"{platform['emoji']} {title_short}",
        color=platform['color']
    )
    if info['thumbnail']:
        embed.set_thumbnail(url=info['thumbnail'])
    if info['uploader']:
        embed.add_field(name="🎤 Uploader", value=info['uploader'], inline=True)
    if info['duration']:
        embed.add_field(name="⏱️ Duration", value=info['duration'], inline=True)
    embed.add_field(name="📦 Format", value=f"`{format_type}`", inline=True)

    # Show trim info in preview if set
    if start_time or end_time:
        trim_str = f"`{start_time or '0:00'}` → `{end_time or 'end'}`"
        embed.add_field(name="✂️ Trim", value=trim_str, inline=False)

    embed.set_footer(text=f"{platform['emoji']} {platform['name']} · Preview expires in 60s")

    view = PreviewView(
        url=url, format_type=format_type, quality=quality,
        extension=extension, trigger_message_id=trigger_message_id,
        prompt_message_id=prompt_message_id,
        start_time=start_time, end_time=end_time,
    )
    await interaction.edit_original_response(content=None, embed=embed, view=view)


# ─────────────────────────────────────────────
#  PLAYLIST
# ─────────────────────────────────────────────

class PlaylistCancelView(discord.ui.View):
    def __init__(self, cancel_event: threading.Event):
        super().__init__(timeout=None)
        self.cancel_event = cancel_event

    @discord.ui.button(label="⏹ Cancel Playlist", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cancel_event.set()
        button.disabled = True
        button.label = "Cancelling..."
        await interaction.response.edit_message(view=self)


async def handle_playlist_download(
    interaction: discord.Interaction,
    url: str,
    format_type: str,
    quality: str = "1080",
    extension: str = "mp3",
):
    cancel_event = threading.Event()
    cancel_view = PlaylistCancelView(cancel_event)

    platform = downloader.get_platform(url)
    embed = discord.Embed(
        title=f"💼 {BOT_NAME} | Playlist Download",
        description="⏳ Starting playlist download...",
        color=platform['color']
    )
    embed.set_footer(text=f"{platform['emoji']} {platform['name']}")
    await interaction.edit_original_response(embed=embed, view=cancel_view)

    delivered = 0
    failed = 0

    async def on_track_done(current, total, title, filepath):
        nonlocal delivered, failed
        bar_filled = int((current / total) * 10)
        bar = "█" * bar_filled + "░" * (10 - bar_filled)

        if filepath and os.path.exists(filepath):
            delivered += 1
            file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
            embed.description = (
                f"⏬ `[{bar}]` **{current}/{total}**\n"
                f"🎵 *{title[:60]}*"
            )
            await interaction.edit_original_response(embed=embed, view=cancel_view)

            if file_size_mb > 10.0:
                dl_url = generate_file_token(filepath)
                await interaction.followup.send(
                    content=f"📥 **Track {current}/{total}:** [{title[:50]}]({dl_url}) *(large file — 1h link)*",
                    ephemeral=True
                )
                asyncio.create_task(_delete_after(filepath, 3600))
            else:
                await interaction.followup.send(
                    content=f"✨ **Track {current}/{total}:** *{title[:50]}*",
                    file=discord.File(filepath),
                    ephemeral=True
                )
                if os.path.exists(filepath):
                    os.remove(filepath)
        else:
            failed += 1
            embed.description = (
                f"⏬ `[{bar}]` **{current}/{total}**\n"
                f"❌ *{title[:60]}*"
            )
            await interaction.edit_original_response(embed=embed, view=cancel_view)

    try:
        await downloader.download_playlist(
            url, format_type, quality, extension,
            progress_callback=on_track_done,
            cancel_event=cancel_event
        )
    except Exception as e:
        logger.error(f"Playlist download error: {e}")
        embed.title = "❌ Playlist Error"
        embed.description = f"Something went wrong: `{str(e)[:200]}`"
        embed.color = discord.Color.red()
        await interaction.edit_original_response(embed=embed, view=None)
        return

    cancelled = cancel_event.is_set()
    embed.title = "⏹ Playlist Cancelled" if cancelled else "✅ Playlist Complete!"
    embed.description = (
        f"📥 **{delivered}** tracks delivered"
        + (f" · ❌ **{failed}** failed" if failed else "")
        + (" · Cancelled early" if cancelled else "")
    )
    embed.color = discord.Color.greyple() if cancelled else discord.Color.green()
    await interaction.edit_original_response(embed=embed, view=None)


async def _delete_after(path: str, delay: float):
    await asyncio.sleep(delay)
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"Deleted file after TTL: {path}")
    except Exception as ex:
        logger.warning(f"Could not delete file {path}: {ex}")


# ─────────────────────────────────────────────
#  EMBEDS
# ─────────────────────────────────────────────

class SupportInformationEmbed(discord.Embed):
    def __init__(self):
        super().__init__(
            title="❓ Supported Platforms",
            description=f"{BOT_NAME} supports a wide range of platforms! Here are the main ones:",
            color=discord.Color.blue()
        )
        self.add_field(name="🎥 Video", value="YouTube, TikTok, Twitter/X, Instagram, Facebook", inline=False)
        self.add_field(name="🎵 Audio", value="SoundCloud, Bandcamp, YouTube Music", inline=False)
        self.add_field(name="🖼️ Pictures", value="Instagram, Twitter, Pinterest (mostly via Link)", inline=False)
        self.add_field(name="...and many more!", value="Supported via yt-dlp powerful engine.", inline=False)


# ─────────────────────────────────────────────
#  AUDIO TRIM MODAL
# ─────────────────────────────────────────────

class AudioTrimModal(discord.ui.Modal, title="✂️ Trim Audio"):
    """
    Modal that collects start/end timestamps for audio trimming.
    Shown after the user picks an audio format.
    """
    start_input = discord.ui.TextInput(
        label="Start Time (optional)",
        placeholder="e.g. 0:30 or 1:15:00 — leave blank for beginning",
        required=False,
        max_length=12,
    )
    end_input = discord.ui.TextInput(
        label="End Time (optional)",
        placeholder="e.g. 2:45 or 3:00:00 — leave blank for full end",
        required=False,
        max_length=12,
    )

    def __init__(self, url: str, extension: str,
                 trigger_message_id: int = None, prompt_message_id: int = None):
        super().__init__()
        self.url = url
        self.extension = extension
        self.trigger_message_id = trigger_message_id
        self.prompt_message_id = prompt_message_id

    async def on_submit(self, interaction: discord.Interaction):
        start = self.start_input.value.strip() or None
        end = self.end_input.value.strip() or None

        # Validate timestamps if provided
        if start and downloader._parse_timestamp(start) is None:
            await interaction.response.send_message(
                "❌ Invalid start time. Use format `1:30` or `90`.", ephemeral=True
            )
            return
        if end and downloader._parse_timestamp(end) is None:
            await interaction.response.send_message(
                "❌ Invalid end time. Use format `2:45` or `165`.", ephemeral=True
            )
            return

        await show_preview(
            interaction, self.url, "audio",
            extension=self.extension,
            trigger_message_id=self.trigger_message_id,
            prompt_message_id=self.prompt_message_id,
            start_time=start,
            end_time=end,
        )


# ─────────────────────────────────────────────
#  START ANALYSIS
# ─────────────────────────────────────────────

async def start_analysis(interaction: discord.Interaction, url: str, format_requested: str,
                         trigger_message_id: int = None, prompt_message_id: int = None):
    if not interaction.response.is_done():
        await interaction.response.send_message("🔍 **Analyzing content...** Please wait.", ephemeral=True)

    if not is_valid_url(url):
        await interaction.edit_original_response(content="❌ Invalid URL! Please provide a valid http or https link.")
        return

    if _is_instagram_post(url):
        entries = await asyncio.to_thread(downloader.get_instagram_carousel, url)
        if entries:
            view = InstagramCarouselView(url, entries, trigger_message_id, prompt_message_id)
            await interaction.edit_original_response(
                content=f"📸 **Found Instagram Carousel:** {len(entries)} Photos\nSelect a photo or download them all:",
                view=view
            )
        else:
            await interaction.edit_original_response(content="❌ **Error:** I couldn't find any photos in that Instagram post.")
        return

    info = downloader.get_media_info(url)
    if not info:
        await interaction.edit_original_response(content="❌ **Oops!** I couldn't analyze that link. Is it the right format?")
        return

    platform = downloader.get_platform(url)
    title_short = info['title'][:50] + "..." if len(info['title']) > 50 else info['title']

    if format_requested == "video":
        view = QualitySelectView(url, info['heights'], trigger_message_id, prompt_message_id)
        await interaction.edit_original_response(
            content=f"{platform['emoji']} **Found:** *{title_short}*\nSelect Your Video Quality:",
            view=view
        )
    elif format_requested == "audio":
        view = AudioFormatView(url, trigger_message_id, prompt_message_id)
        await interaction.edit_original_response(
            content=f"{platform['emoji']} **Found:** *{title_short}*\nSelect Audio Format:",
            view=view
        )
    elif format_requested == "picture":
        view = PictureFormatView(url, trigger_message_id, prompt_message_id)
        await interaction.edit_original_response(
            content=f"{platform['emoji']} **Found:** *{title_short}*\nSelect Image Format:",
            view=view
        )


# ─────────────────────────────────────────────
#  FORMAT SELECTION VIEWS
# ─────────────────────────────────────────────

class InstagramCarouselView(discord.ui.View):
    def __init__(self, url: str, entries: list, trigger_message_id=None, prompt_message_id=None):
        super().__init__(timeout=300)
        self.url = url
        self.entries = entries
        self.trigger_message_id = trigger_message_id
        self.prompt_message_id = prompt_message_id

        display_entries = self.entries[:20]
        for entry in display_entries:
            i = entry['index']
            btn = discord.ui.Button(
                label=f"📷 Photo {i}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"ig_photo_{i}",
                row=(i-1) // 5
            )
            btn.callback = self.create_callback(i)
            self.add_item(btn)

        all_btn = discord.ui.Button(
            label="⬇️ Download All",
            style=discord.ButtonStyle.success,
            custom_id="ig_download_all",
            row=(min(len(display_entries), 20)) // 5
        )
        all_btn.callback = self.download_all_callback
        self.add_item(all_btn)

    def create_callback(self, index):
        async def callback(interaction: discord.Interaction):
            wait = check_cooldown(interaction.user.id)
            if wait:
                return await interaction.response.send_message(
                    f"⏳ Please wait **{wait}s** before starting a new download.",
                    ephemeral=True
                )
            _user_cooldowns[interaction.user.id] = time.time()
            if not interaction.response.is_done():
                await interaction.response.send_message(f"⌛ Downloading Photo {index}...", ephemeral=True)
            files = await downloader.download_instagram_photo(self.url, index=index)
            if files:
                await interaction.followup.send(content=f"✨ **Photo {index}** ready!", file=discord.File(files[0]), ephemeral=True)
                if os.path.exists(files[0]):
                    os.remove(files[0])
            else:
                await interaction.followup.send("❌ Failed to download photo. The link may have expired.", ephemeral=True)
        return callback

    async def download_all_callback(self, interaction: discord.Interaction):
        wait = check_cooldown(interaction.user.id)
        if wait:
            return await interaction.response.send_message(
                f"⏳ Please wait **{wait}s** before starting a new download.",
                ephemeral=True
            )
        _user_cooldowns[interaction.user.id] = time.time()
        if not interaction.response.is_done():
            await interaction.response.send_message(f"⌛ Downloading all {len(self.entries)} photos...", ephemeral=True)
        files = await downloader.download_instagram_photo(self.url)
        if files:
            discord_files = [discord.File(f) for f in files]
            for i in range(0, len(discord_files), 10):
                batch = discord_files[i:i+10]
                await interaction.followup.send(content=f"✨ **Batch {i//10 + 1}** of photos ready!", files=batch, ephemeral=True)
            for f in files:
                if os.path.exists(f):
                    os.remove(f)
        else:
            await interaction.followup.send("❌ Failed to download photos.", ephemeral=True)


class QualitySelectView(discord.ui.View):
    def __init__(self, url: str, heights: list, trigger_message_id: int = None, prompt_message_id: int = None):
        super().__init__(timeout=180)
        self.url = url
        self.trigger_message_id = trigger_message_id
        self.prompt_message_id = prompt_message_id

        options = []
        if not heights:
            options.append(discord.SelectOption(label="Best Available", value="best", description="High-Def or Original"))
        else:
            standard_breakpoints = {360: "SD", 480: "HQ", 720: "HD", 1080: "Full HD", 1440: "2K", 2160: "4K"}
            sorted_heights = sorted(list(set(heights)), reverse=True)
            for h in sorted_heights:
                label = f"{h}p"
                desc = standard_breakpoints.get(h, "Auto")
                options.append(discord.SelectOption(label=label, value=str(h), description=desc))

        self.add_item(self.Dropdown(options))

    class Dropdown(discord.ui.Select):
        def __init__(self, options):
            super().__init__(placeholder="Choose video quality...", options=options)

        async def callback(self, interaction: discord.Interaction):
            await self.view.on_select(interaction)

    async def on_select(self, interaction: discord.Interaction):
        quality = interaction.data['values'][0]
        await show_preview(
            interaction, self.url, "video", quality=quality,
            trigger_message_id=self.trigger_message_id,
            prompt_message_id=self.prompt_message_id
        )


class AudioFormatView(discord.ui.View):
    """Format selection for Audio — after selection opens the Trim modal."""
    def __init__(self, url: str, trigger_message_id: int = None, prompt_message_id: int = None):
        super().__init__(timeout=180)
        self.url = url
        self.trigger_message_id = trigger_message_id
        self.prompt_message_id = prompt_message_id

    @discord.ui.select(
        placeholder="Choose audio format...",
        options=[
            discord.SelectOption(label="MP3 (Standard)", value="mp3"),
            discord.SelectOption(label="WAV (Lossless)", value="wav"),
            discord.SelectOption(label="FLAC (High Fidelity)", value="flac"),
            discord.SelectOption(label="M4A (Apple)", value="m4a")
        ]
    )
    async def select_format(self, interaction: discord.Interaction, select: discord.ui.Select):
        ext = select.values[0]
        # Open trim modal — user can leave both fields blank to skip trimming
        modal = AudioTrimModal(
            url=self.url,
            extension=ext,
            trigger_message_id=self.trigger_message_id,
            prompt_message_id=self.prompt_message_id,
        )
        await interaction.response.send_modal(modal)


class PictureFormatView(discord.ui.View):
    def __init__(self, url: str, trigger_message_id: int = None, prompt_message_id: int = None):
        super().__init__(timeout=180)
        self.url = url
        self.trigger_message_id = trigger_message_id
        self.prompt_message_id = prompt_message_id

    @discord.ui.select(
        placeholder="Choose image format...",
        options=[
            discord.SelectOption(label="PNG (Lossless)", value="png"),
            discord.SelectOption(label="JPG (Fast)", value="jpg"),
            discord.SelectOption(label="WEBP (Modern)", value="webp")
        ]
    )
    async def select_format(self, interaction: discord.Interaction, select: discord.ui.Select):
        await show_preview(
            interaction, self.url, "picture", extension=select.values[0],
            trigger_message_id=self.trigger_message_id,
            prompt_message_id=self.prompt_message_id
        )


class CancelView(discord.ui.View):
    def __init__(self, cancel_event: threading.Event):
        super().__init__(timeout=None)
        self.cancel_event = cancel_event

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cancel_event.set()
        button.disabled = True
        button.label = "Cancelling..."
        await interaction.response.edit_message(view=self)


# ─────────────────────────────────────────────
#  CORE DOWNLOAD PROCESSOR
# ─────────────────────────────────────────────

async def process_action(
    interaction: discord.Interaction, url: str, format_type: str,
    quality: str = "1080", extension: str = None,
    trigger_message_id: int = None, prompt_message_id: int = None,
    start_time: str = None, end_time: str = None,
):
    user_id = interaction.user.id

    wait = check_cooldown(user_id)
    if wait:
        return await interaction.response.send_message(
            f"⏳ Please wait **{wait}s** before starting a new download.",
            ephemeral=True
        ) if not interaction.response.is_done() else await interaction.edit_original_response(
            content=f"⏳ Please wait **{wait}s** before starting a new download."
        )

    async def _notify_position(position: int):
        msg = f"🟡 You're **#{position} in queue** — your download will start soon!"
        if interaction.response.is_done():
            await interaction.edit_original_response(content=msg)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    async def _run_download():
        await _execute_download(
            interaction, url, format_type, quality, extension or "mp3",
            trigger_message_id, prompt_message_id,
            start_time=start_time, end_time=end_time,
        )

    accepted = await _enqueue_download(user_id, _run_download, _notify_position)
    if not accepted:
        msg = f"🚫 **Queue full!** You already have {MAX_QUEUE_PER_USER} downloads queued. Please wait."
        if interaction.response.is_done():
            await interaction.edit_original_response(content=msg)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return


async def _execute_download(
    interaction: discord.Interaction, url: str, format_type: str,
    quality: str, extension: str,
    trigger_message_id: int = None, prompt_message_id: int = None,
    start_time: str = None, end_time: str = None,
):
    user_id = interaction.user.id
    active_downloads[user_id] = active_downloads.get(user_id, 0) + 1
    _user_cooldowns[user_id] = time.time()

    platform = downloader.get_platform(url)

    try:
        embed = discord.Embed(
            title=f"{platform['emoji']} {BOT_NAME} | Working...",
            description="🔍 Locating media...",
            color=platform['color']
        )
        embed.set_footer(text=f"{platform['emoji']} {platform['name']}")
        cancel_event = threading.Event()
        cancel_view = CancelView(cancel_event)
        loop = asyncio.get_running_loop()

        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, view=cancel_view, ephemeral=True)
        else:
            await interaction.edit_original_response(content=None, embed=embed, view=cancel_view)

        async def update_status_ui(payload):
            if isinstance(payload, dict):
                phase = payload.get("phase", "")
                if phase == "DOWNLOADING":
                    pct = payload.get("percent", 0)
                    dl = payload.get("downloaded_mb", 0)
                    total = payload.get("total_mb", 0)
                    spd = payload.get("speed_mb", 0)
                    bar_filled = int(pct / 10)
                    bar = "█" * bar_filled + "░" * (10 - bar_filled)
                    size_str = f"{dl} / {total} MB" if total > 0 else f"{dl} MB"
                    speed_str = f" · {spd} MB/s" if spd > 0 else ""
                    embed.description = f"⬇️ `[{bar}]` **{pct}%**\n{size_str}{speed_str}"
                elif phase == "PROCESSING":
                    embed.description = "⚙️ Processing file..."
                elif phase == "SEARCHING":
                    embed.description = "🔍 Locating media..."
            try:
                await interaction.edit_original_response(embed=embed)
            except Exception:
                pass

        def status_callback(status):
            asyncio.run_coroutine_threadsafe(update_status_ui(status), loop)

        file_path, file_size_mb = await asyncio.to_thread(
            downloader.download_media, url, format_type, quality, extension,
            status_callback, cancel_event, start_time, end_time
        )

        if not file_path:
            raise Exception("No file was returned from the downloader.")

        if file_size_mb > 10.0:
            download_url = generate_file_token(file_path)
            embed.title = f"{platform['emoji']} File Ready (Large)"
            embed.description = (
                f"This file was too large for Discord (>10MB).\n"
                f"[**Click here to Download**]({download_url})\n\n"
                f"*(File expires in 1 hour)*"
            )
            embed.color = discord.Color.green()
            await interaction.edit_original_response(embed=embed, view=None)
            asyncio.create_task(_delete_after(file_path, 3600))
        else:
            file = discord.File(file_path)
            await interaction.followup.send(
                content=f"✨ **Here is your {format_type}!** Enjoy!", file=file, ephemeral=True
            )
            embed.title = f"{platform['emoji']} Complete!"
            embed.description = "Your file has been delivered privately to you. 🔐"
            embed.color = discord.Color.green()
            await interaction.edit_original_response(embed=embed, view=None)
            if os.path.exists(file_path):
                os.remove(file_path)

        if trigger_message_id:
            try:
                msg = await interaction.channel.fetch_message(trigger_message_id)
                await msg.delete()
            except Exception:
                pass

        if prompt_message_id:
            try:
                p_msg = await interaction.channel.fetch_message(prompt_message_id)
                await p_msg.delete()
            except Exception:
                pass

    except Exception as e:
        logger.error(f"UI Download Error: {e}")
        e_str = str(e)
        if "cancelled by user" in e_str.lower():
            embed.title = "🚫 Cancelled"
            embed.description = "Download was cancelled."
            embed.color = discord.Color.greyple()
        else:
            error_msg = "Something went wrong while I was fetching your file. I'll try to do better next time! 😓"
            if "Private video" in e_str:
                error_msg = "I'm sorry, that video seems to be private! 🔒 I can't access restricted content."
            elif "Unsupported URL" in e_str:
                error_msg = "Oops! I don't recognize this platform yet. Maybe check my supported sites? 🤔"
            embed.title = "❌ Error"
            embed.description = error_msg
            embed.color = discord.Color.red()
        await interaction.edit_original_response(embed=embed, view=None)
    finally:
        active_downloads[user_id] = max(0, active_downloads.get(user_id, 1) - 1)


# ─────────────────────────────────────────────
#  MODAL + DASHBOARD
# ─────────────────────────────────────────────

class DownloadModal(discord.ui.Modal):
    def __init__(self, format_type):
        super().__init__(title=f"Manually Download {format_type.capitalize()}")
        self.format_type = format_type
        self.url_input = discord.ui.TextInput(
            label="Provide the media URL",
            placeholder="https://www.youtube.com/watch?v=...",
            required=True
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        url = self.url_input.value
        if not is_valid_url(url):
            await interaction.response.send_message("❌ Invalid URL! Please provide a valid http or https link.", ephemeral=True)
            return
        wait = check_cooldown(interaction.user.id)
        if wait:
            return await interaction.response.send_message(
                f"⏳ Please wait **{wait}s** before starting a new download.",
                ephemeral=True
            )
        await start_analysis(interaction, url, self.format_type)


class DashboardView(discord.ui.View):
    def __init__(self, url=None, trigger_message_id=None):
        super().__init__(timeout=None)
        self.url = url
        self.trigger_message_id = trigger_message_id

    @discord.ui.button(label="🎥 Video", style=discord.ButtonStyle.primary, custom_id="fetchy_video")
    async def video(self, interaction: discord.Interaction, button: discord.ui.Button):
        wait = check_cooldown(interaction.user.id)
        if wait:
            return await interaction.response.send_message(
                f"⏳ Please wait **{wait}s** before starting a new download.",
                ephemeral=True
            )
        if self.url:
            await start_analysis(interaction, self.url, "video", self.trigger_message_id, interaction.message.id)
        else:
            await interaction.response.send_modal(DownloadModal("video"))

    @discord.ui.button(label="🎵 Audio", style=discord.ButtonStyle.primary, custom_id="fetchy_audio")
    async def audio(self, interaction: discord.Interaction, button: discord.ui.Button):
        wait = check_cooldown(interaction.user.id)
        if wait:
            return await interaction.response.send_message(
                f"⏳ Please wait **{wait}s** before starting a new download.",
                ephemeral=True
            )
        if self.url:
            await start_analysis(interaction, self.url, "audio", self.trigger_message_id, interaction.message.id)
        else:
            await interaction.response.send_modal(DownloadModal("audio"))

    @discord.ui.button(label="🖼️ Picture", style=discord.ButtonStyle.primary, custom_id="fetchy_picture")
    async def picture(self, interaction: discord.Interaction, button: discord.ui.Button):
        wait = check_cooldown(interaction.user.id)
        if wait:
            return await interaction.response.send_message(
                f"⏳ Please wait **{wait}s** before starting a new download.",
                ephemeral=True
            )
        if self.url:
            await start_analysis(interaction, self.url, "picture", self.trigger_message_id, interaction.message.id)
        else:
            await interaction.response.send_modal(DownloadModal("picture"))

    @discord.ui.button(label="❓ Support Info", style=discord.ButtonStyle.secondary, custom_id="fetchy_support")
    async def support_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=SupportInformationEmbed(), ephemeral=True)
