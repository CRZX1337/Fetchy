import discord
import logging
import asyncio
import os
import urllib.parse
from config import CONFIG
import downloader

def is_valid_url(url: str) -> bool:
    """Validates if a string is a proper http/https URL."""
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False

# --- LOGGING SETUP ---
logger = logging.getLogger("MediaBot.UI")

# --- RATE LIMITING ---
active_downloads = {}  # user_id -> count
MAX_CONCURRENT_PER_USER = 2

class SupportInformationEmbed(discord.Embed):
    """Custom embed for supported sites."""
    def __init__(self):
        super().__init__(
            title="❓ Supported Platforms",
            description="Fetchy supports a wide range of platforms! Here are the main ones:",
            color=discord.Color.blue()
        )
        self.add_field(name="🎥 Video", value="YouTube, TikTok, Twitter/X, Instagram, Facebook", inline=False)
        self.add_field(name="🎵 Audio", value="SoundCloud, Bandcamp, YouTube Music", inline=False)
        self.add_field(name="🖼️ Pictures", value="Instagram, Twitter, Pinterest (mostly via Link)", inline=False)
        self.add_field(name="...and many more!", value="Supported via yt-dlp powerful engine.", inline=False)

async def start_analysis(interaction: discord.Interaction, url: str, format_requested: str, trigger_message_id: int = None, prompt_message_id: int = None):
    """Core logic to analyze a link and present the next selection view."""
    if not interaction.response.is_done():
        await interaction.response.send_message("🔍 **Analyzing content...** Please wait.", ephemeral=True)
    
    if not is_valid_url(url):
        await interaction.edit_original_response(content="❌ Invalid URL! Please provide a valid http or https link.")
        return

    # Early return for Instagram Carousels (must be before get_media_info)
    if "instagram.com/p/" in url:
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

    # 1. ANALYZE LINK
    info = downloader.get_media_info(url)
    if not info:
        await interaction.edit_original_response(content="❌ **Oops!** I couldn't analyze that link. Is it the right format?")
        return

    title_short = info['title'][:50] + "..." if len(info['title']) > 50 else info['title']
    
    if format_requested == "video":
        # Pass resolution heights for dynamic filtering
        view = QualitySelectView(url, info['heights'], trigger_message_id, prompt_message_id)
        await interaction.edit_original_response(content=f"🎬 **Found:** *{title_short}*\nSelect Your Video Quality:", view=view)
    elif format_requested == "audio":
        view = AudioFormatView(url, trigger_message_id, prompt_message_id)
        await interaction.edit_original_response(content=f"🎵 **Found:** *{title_short}*\nSelect Audio Format:", view=view)
    elif format_requested == "picture":
        view = PictureFormatView(url, trigger_message_id, prompt_message_id)
        await interaction.edit_original_response(content=f"🖼️ **Found:** *{title_short}*\nSelect Image Format:", view=view)

class InstagramCarouselView(discord.ui.View):
    """View for selecting photos from an Instagram carousel."""
    def __init__(self, url: str, entries: list, trigger_message_id=None, prompt_message_id=None):
        super().__init__(timeout=300)
        self.url = url
        self.entries = entries
        self.trigger_message_id = trigger_message_id
        self.prompt_message_id = prompt_message_id

        # Limit to 20 entries to ensure we have room for the "Download All" button (Max 25 items)
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
        if not interaction.response.is_done():
            await interaction.response.send_message(f"⌛ Downloading all {len(self.entries)} photos...", ephemeral=True)
        
        files = await downloader.download_instagram_photo(self.url)
        if files:
            discord_files = [discord.File(f) for f in files]
            # Send in batches of 10 (Discord limit)
            for i in range(0, len(discord_files), 10):
                batch = discord_files[i:i+10]
                await interaction.followup.send(content=f"✨ **Batch {i//10 + 1}** of photos ready!", files=batch, ephemeral=True)
            
            for f in files:
                if os.path.exists(f):
                    os.remove(f)
        else:
            await interaction.followup.send("❌ Failed to download photos.", ephemeral=True)

class QualitySelectView(discord.ui.View):
    """Refined dynamic quality selection based on available resolutions."""
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
        await process_action(interaction, self.url, "video", quality=quality, trigger_message_id=self.trigger_message_id, prompt_message_id=self.prompt_message_id)

class AudioFormatView(discord.ui.View):
    """Format selection for Audio."""
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
        await process_action(interaction, self.url, "audio", extension=select.values[0], trigger_message_id=self.trigger_message_id, prompt_message_id=self.prompt_message_id)

class PictureFormatView(discord.ui.View):
    """Format selection for Pictures."""
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
        await process_action(interaction, self.url, "picture", extension=select.values[0], trigger_message_id=self.trigger_message_id, prompt_message_id=self.prompt_message_id)

async def process_action(interaction: discord.Interaction, url: str, format_type: str, quality: str = "1080", extension: str = None, trigger_message_id: int = None, prompt_message_id: int = None):
    """Global processor for the final download stage with rate limiting and status updates."""
    user_id = interaction.user.id
    
    if active_downloads.get(user_id, 0) >= MAX_CONCURRENT_PER_USER:
        return await interaction.response.send_message(
            "⏳ **Whoa there!** You already have 2 active downloads. Please wait for one to finish! 🚦",
            ephemeral=True
        )

    # Increment counter
    active_downloads[user_id] = active_downloads.get(user_id, 0) + 1
    
    try:
        embed = discord.Embed(
            title="📥 Fetchy | Working...",
            description="I'm processing your media Request. It will be ready in a moment!",
            color=discord.Color.yellow()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.edit_original_response(content=None, embed=embed, view=None)

        # 2. RUN DOWNLOAD with status hook
        loop = asyncio.get_running_loop()
        
        async def update_status_ui(phase):
            mapping = {
                "SEARCHING": "🔍 Locating media...",
                "DOWNLOADING": "📥 Downloading data...",
                "PROCESSING": "⚙️ Processing file..."
            }
            embed.description = mapping.get(phase, "Working...")
            await interaction.edit_original_response(embed=embed)
            
        def status_callback(status):
            asyncio.run_coroutine_threadsafe(update_status_ui(status), loop)

        file_path, file_size_mb = await asyncio.to_thread(
            downloader.download_media, url, format_type, quality, extension or "mp3", status_callback
        )

        if not file_path:
            raise Exception("No file was returned from the downloader.")

        # 3. HANDLE DELIVERY
        if file_size_mb > 10.0:
            filename = os.path.basename(file_path)
            encoded_filename = urllib.parse.quote(filename)
            base_url = CONFIG.get("BASE_URL", "http://localhost:8080").rstrip('/')
            download_url = f"{base_url}/downloads/{encoded_filename}"
            embed.title = "💾 File Ready (Large)"
            embed.description = f"This file was too large for Discord (>10MB).\n[**Click here to Download**]({download_url})\n\n*(File expires in 24 hours)*"
            embed.color = discord.Color.green()
            await interaction.edit_original_response(embed=embed)
        else:
            file = discord.File(file_path)
            # Deliver the file ephemerally
            await interaction.followup.send(content=f"✨ **Here is your {format_type}!** Enjoy!", file=file, ephemeral=True)
            
            embed.title = "✅ Complete!"
            embed.description = "Your file has been delivered privately to you. 🔐"
            embed.color = discord.Color.green()
            await interaction.edit_original_response(embed=embed)
            if os.path.exists(file_path):
                os.remove(file_path)

        # 4. UX CLEANUP
        if trigger_message_id:
            try:
                msg = await interaction.channel.fetch_message(trigger_message_id)
                await msg.delete()
                logger.info(f"Trigger message {trigger_message_id} deleted.")
            except Exception: pass

        if prompt_message_id:
            try:
                p_msg = await interaction.channel.fetch_message(prompt_message_id)
                await p_msg.delete()
                logger.info(f"Prompt message {prompt_message_id} deleted.")
            except Exception: pass

    except Exception as e:
        logger.error(f"UI Download Error: {e}")
        error_msg = "Something went wrong while I was fetching your file. I'll try to do better next time! 😓"
        e_str = str(e)
        if "Private video" in e_str:
            error_msg = "I'm sorry, that video seems to be private! 🔒 I can't access restricted content."
        elif "Unsupported URL" in e_str:
            error_msg = "Oops! I don't recognize this platform yet. Maybe check my supported sites? 🤔"
        
        embed.title = "❌ Error"
        embed.description = error_msg
        embed.color = discord.Color.red()
        await interaction.edit_original_response(embed=embed)
    finally:
        active_downloads[user_id] = max(0, active_downloads.get(user_id, 1) - 1)

class DownloadModal(discord.ui.Modal):
    """Prompt for a URL when no link was auto-detected."""
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
        await start_analysis(interaction, url, self.format_type)

class DashboardView(discord.ui.View):
    """The central interactive hub for Fetchy."""
    def __init__(self, url=None, trigger_message_id=None):
        super().__init__(timeout=None)  # Persistent View
        self.url = url
        self.trigger_message_id = trigger_message_id

    @discord.ui.button(label="🎥 Video", style=discord.ButtonStyle.primary, custom_id="fetchy_video")
    async def video(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.url:
            await start_analysis(interaction, self.url, "video", self.trigger_message_id, interaction.message.id)
        else:
            await interaction.response.send_modal(DownloadModal("video"))

    @discord.ui.button(label="🎵 Audio", style=discord.ButtonStyle.primary, custom_id="fetchy_audio")
    async def audio(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.url:
            await start_analysis(interaction, self.url, "audio", self.trigger_message_id, interaction.message.id)
        else:
            await interaction.response.send_modal(DownloadModal("audio"))

    @discord.ui.button(label="🖼️ Picture", style=discord.ButtonStyle.primary, custom_id="fetchy_picture")
    async def picture(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.url:
            await start_analysis(interaction, self.url, "picture", self.trigger_message_id, interaction.message.id)
        else:
            await interaction.response.send_modal(DownloadModal("picture"))

    @discord.ui.button(label="❓ Support Info", style=discord.ButtonStyle.secondary, custom_id="fetchy_support")
    async def support_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=SupportInformationEmbed(), ephemeral=True)
