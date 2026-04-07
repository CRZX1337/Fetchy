import os
import asyncio
import logging
import discord

from downloader import download_media

logger = logging.getLogger("MediaBot")

class DownloadModal(discord.ui.Modal):
    def __init__(self, format_type: str):
        super().__init__(title='Enter Media Link')
        self.format_type = format_type

    # Text input for the source URL
    url_input = discord.ui.TextInput(
        label='Video / Audio URL',
        style=discord.TextStyle.short,
        placeholder='https://www...',
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        raw_format = self.format_type
        
        # 1. Ephemeral Response ("Please Wait" Status)
        embed = discord.Embed(
            title=f"⏳ Preparing your {raw_format}...",
            description="Just a moment while I process your request in the background... 🚀",
            color=discord.Color.yellow()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        file_path = None
        try:
            # 2. YTDLP must inevitably run in a thread; downloading the true filename
            url = self.url_input.value
            file_path = await asyncio.to_thread(download_media, url, raw_format)
            
            # 3. Limit Checking for 10MB
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb > 10.0:
                embed.title = "❌ Request failed"
                embed.description = f"The requested file is **{file_size_mb:.2f} MB**, which exceeds my current 10 MB limit for Discord uploads. 😓"
                embed.color = discord.Color.red()
                await interaction.edit_original_response(embed=embed, attachments=[])
            else:
                embed.title = "✅ Your file is ready!"
                embed.description = f"Handled with care. ✨\n\n*Support the project: [Star us on GitHub](https://github.com/CRZX1337/Fetchy)*"
                embed.color = discord.Color.green()
                
                # Post file to the Interaction webhook
                discord_file = discord.File(file_path)
                await interaction.edit_original_response(embed=embed, attachments=[discord_file])
                
        except Exception as e:
            logger.error(f"Error at URL {self.url_input.value}: {str(e)}")
            embed.title = "❌ I ran into a small issue processing your request"
            embed.description = f"Here's what happened on my end:\n```{str(e)[:700]}```"
            embed.color = discord.Color.red()
            await interaction.edit_original_response(embed=embed, attachments=[])
            
        finally:
            # 4. OS CLEANUP OF TMP FILES
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Disk cleanup successful: {file_path}")
                except Exception as cleanup_err:
                    logger.error(f"Error deleting local file cache: {cleanup_err}")

class DashboardView(discord.ui.View):
    # timeout=None is mandatory so button clicks ALWAYS trigger (even after long idle times)
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="🎥 Video (MP4)", style=discord.ButtonStyle.primary, custom_id="persistent_dashboard_btn_video")
    async def btn_video(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DownloadModal(format_type="video"))

    @discord.ui.button(label="🎵 Audio (MP3)", style=discord.ButtonStyle.success, custom_id="persistent_dashboard_btn_audio")
    async def btn_audio(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DownloadModal(format_type="audio"))

    @discord.ui.button(label="🖼️ Picture (PNG)", style=discord.ButtonStyle.secondary, custom_id="persistent_dashboard_btn_picture")
    async def btn_picture(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DownloadModal(format_type="picture"))
