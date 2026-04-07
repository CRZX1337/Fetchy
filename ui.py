import os
import asyncio
import logging
import discord

from downloader import download_media

logger = logging.getLogger("MediaBot")

class DownloadModal(discord.ui.Modal):
    def __init__(self, format_type: str):
        super().__init__(title='Medien Link eingeben')
        self.format_type = format_type

    # Text-Input für die Quelle
    url_input = discord.ui.TextInput(
        label='Video- / Audio-URL',
        style=discord.TextStyle.short,
        placeholder='https://www...',
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        raw_format = self.format_type
        
        # 2. Ephemeral Response ("Bitte Warten" Status)
        embed = discord.Embed(
            title=f"⏳ Lade {raw_format.capitalize()} herunter...",
            description="Bitte warten, dein Download läuft im Hintergrund ohne Blockaden.",
            color=discord.Color.yellow()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        file_path = None
        try:
            # 3. YTDLP muss zwingend in einen Thread, wir laden den echten Dateinamen nun herunter
            url = self.url_input.value
            file_path = await asyncio.to_thread(download_media, url, raw_format)
            
            # 4. Limit Checking für 10MB
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb > 10.0:
                embed.title = "❌ Download fehlgeschlagen"
                embed.description = f"Die Datei ist **{file_size_mb:.2f} MB** groß.\nDas Discord Upload-Limit liegt bei 10 MB."
                embed.color = discord.Color.red()
                await interaction.edit_original_response(embed=embed, attachments=[])
            else:
                embed.title = "✅ Download erfolgreich!"
                embed.description = f"Deine Datei ist fertig."
                embed.color = discord.Color.green()
                
                # Datei an den Interaction-Webhook posten
                discord_file = discord.File(file_path)
                await interaction.edit_original_response(embed=embed, attachments=[discord_file])
                
        except Exception as e:
            logger.error(f"Error bei URL {self.url_input.value}: {str(e)}")
            embed.title = "❌ Es ist ein Fehler aufgetreten"
            embed.description = f"Beim Verarbeiten der Anfrage ist etwas gecrasht:\n```{str(e)[:700]}```"
            embed.color = discord.Color.red()
            await interaction.edit_original_response(embed=embed, attachments=[])
            
        finally:
            # 5. OS CLEAUP DER TMP FILES
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Cleanup der Festplatte erfolgreich: {file_path}")
                except Exception as cleanup_err:
                    logger.error(f"Fehler beim Löschen des Dateicaches: {cleanup_err}")

class DashboardView(discord.ui.View):
    # timeout=None ist zwingend, damit Button klicks IMMER (auch nach langer Wartezeit) triggern können
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="🎥 Video (MP4)", style=discord.ButtonStyle.primary, custom_id="persistent_dashboard_btn_video")
    async def btn_video(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DownloadModal(format_type="video"))

    @discord.ui.button(label="🎵 Audio (MP3)", style=discord.ButtonStyle.success, custom_id="persistent_dashboard_btn_audio")
    async def btn_audio(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DownloadModal(format_type="audio"))

    @discord.ui.button(label="🖼️ Thumbnail (PNG)", style=discord.ButtonStyle.secondary, custom_id="persistent_dashboard_btn_thumbnail")
    async def btn_thumbnail(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DownloadModal(format_type="thumbnail"))
