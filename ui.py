import os
import asyncio
import logging
import discord

from downloader import download_media

logger = logging.getLogger("MediaBot")

class DownloadModal(discord.ui.Modal):
    def __init__(self, format_type: str, quality: str):
        super().__init__(title='Enter Media Link')
        self.format_type = format_type
        self.quality = quality

    # Text input for the source URL
    url_input = discord.ui.TextInput(
        label='Video / Audio URL',
        style=discord.TextStyle.short,
        placeholder='https://www...',
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        raw_format = self.format_type
        loop = interaction.client.loop
        
        # 1. Ephemeral Response ("Please Wait" Status)
        embed = discord.Embed(
            title=f"🎬 Fetchy | Preparing your {raw_format}",
            description="🔄 Initializing request...",
            color=discord.Color.yellow()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Thread-safe callback for live status updates from downloader
        async def update_status_ui(phase):
            phase_map = {
                "SEARCHING": "🔍 Searching for your content...",
                "DOWNLOADING": "📥 Downloading media files...",
                "PROCESSING": "⚙️ Finalizing and merging quality layers..."
            }
            embed.description = phase_map.get(phase, phase)
            await interaction.edit_original_response(embed=embed)

        def status_callback(status):
            asyncio.run_coroutine_threadsafe(update_status_ui(status), loop)
        
        file_path = None
        try:
            # 2. Extract and download with live hooks
            url = self.url_input.value
            file_path = await asyncio.to_thread(download_media, url, raw_format, self.quality, status_callback)
            
            # 3. Limit Checking for 10MB
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb > 10.0:
                embed.title = "❌ Request failed"
                embed.description = f"The requested file is **{file_size_mb:.2f} MB**, which exceeds my current 10 MB limit for Discord uploads. 😓"
                embed.color = discord.Color.red()
                await interaction.edit_original_response(embed=embed, attachments=[])
            else:
                embed.title = "✅ Your file is ready!"
                embed.description = f"Handled with care at **{self.quality}p**. ✨\n\n*Support the project: [Star us on GitHub](https://github.com/CRZX1337/Fetchy)*"
                embed.color = discord.Color.green()
                
                # Post file to the Interaction webhook
                discord_file = discord.File(file_path)
                await interaction.edit_original_response(embed=embed, attachments=[discord_file])
                
        except Exception as e:
            error_str = str(e)
            logger.error(f"Error at URL {self.url_input.value}: {error_str}")
            
            # Specific Mapper for yt-dlp exceptions
            if "Private video" in error_str:
                friendly_error = "I'm sorry, that video seems to be private! 🔒 I can't access restricted content."
            elif "Unsupported URL" in error_str:
                friendly_error = "Oops! I don't recognize this platform yet. Maybe check my supported sites? 🤔"
            else:
                friendly_error = "Something went wrong while I was fetching your file. I'll try to do better next time! 😓"
                
            embed.title = "❌ Request issue"
            embed.description = friendly_error
            embed.color = discord.Color.red()
            await interaction.edit_original_response(embed=embed, attachments=[])
            
        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Disk cleanup successful: {file_path}")
                except Exception as cleanup_err:
                    logger.error(f"Error deleting local file cache: {cleanup_err}")

class QualitySelectView(discord.ui.View):
    def __init__(self, format_type: str):
        super().__init__(timeout=180)
        self.format_type = format_type

    @discord.ui.select(
        placeholder="Choose your preferred quality...",
        options=[
            discord.SelectOption(label="720p", value="720", description="Standard HD - Balanced performance"),
            discord.SelectOption(label="1080p", value="1080", description="Full HD - Recommended baseline", default=True),
            discord.SelectOption(label="1440p (2K)", value="1440", description="Quad HD - For high-res displays"),
            discord.SelectOption(label="2160p (4K)", value="2160", description="Ultra HD - Maximum fidelity")
        ]
    )
    async def select_quality(self, interaction: discord.Interaction, select: discord.ui.Select):
        quality = select.values[0]
        # Transition to the URL input modal
        await interaction.response.send_modal(DownloadModal(format_type=self.format_type, quality=quality))

class DashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="🎥 Video (MP4)", style=discord.ButtonStyle.primary, custom_id="persistent_dashboard_btn_video")
    async def btn_video(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Please select the desired video quality:", view=QualitySelectView("video"), ephemeral=True)

    @discord.ui.button(label="🎵 Audio (MP3)", style=discord.ButtonStyle.success, custom_id="persistent_dashboard_btn_audio")
    async def btn_audio(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Audio currently defaults to best, but we'll follow the flow
        await interaction.response.send_message("High-quality audio extraction selected. Proceed to link:", view=QualitySelectView("audio"), ephemeral=True)

    @discord.ui.button(label="🖼️ Picture (PNG)", style=discord.ButtonStyle.secondary, custom_id="persistent_dashboard_btn_picture")
    async def btn_picture(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Original quality picture extraction selected. Proceed to link:", view=QualitySelectView("picture"), ephemeral=True)
