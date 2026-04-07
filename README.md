<div align="center">

![Fetchy Banner](./media/banner.png)

[![Version](https://img.shields.io/badge/version-v1.4.0-blue.svg)](https://github.com/CRZX1337/Fetchy)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/CRZX1337/Fetchy/blob/master/LICENSE)
[![Powered by yt-dlp](https://img.shields.io/badge/powered%20by-yt--dlp-red.svg)](https://github.com/yt-dlp/yt-dlp)
[![Built with Python 3.11](https://img.shields.io/badge/built%20with-Python%203.11-yellow.svg)](https://www.python.org/)

</div>

# 🚀 Fetchy — Your Elite Personal Media Assistant

Fetchy is a high-performance, privacy-focused Discord bot designed to extract and deliver media from across the web with unparalleled ease. Built on a modern asynchronous architecture, Fetchy provides a clean, automated environment for all your media needs.

---

## 📖 About Fetchy

<div align="center">
  <img src="./media/logo.png" alt="Fetchy Logo" width="200"/>
</div>

Fetchy was engineered to simplify the complex world of media extraction. Operating as a professional personal assistant, Fetchy handles everything from high-resolution 4K encoding to smart link detection, ensuring that your favorite content is always just a click away—all while maintaining absolute user anonymity.

---

## ✨ Key Features

- 🎥 **Elite Quality Selection:** Choose your preferred resolution, from **720p** up to **Ultra HD 4K**.
- 🔄 **Live Progress Tracking:** Stay informed with real-time status updates including download percentage, size, and speed.
- ❌ **Cancel Support:** Abort any active download instantly with a single button click.
- 🧠 **Smart Link Detection:** Fetchy proactively notices media links in your channel and offers to assist immediately.
- 🎬 **Full Format Support:** High-quality MP4 video, high-fidelity MP3 audio, and high-res PNG pictures.
- 🧹 **Daily Auto-Cleanup:** Automated maintenance task that purges abandoned files to save disk space.
- 🛡️ **URL Validation:** Protects against invalid or malicious inputs before any download begins.
- 💬 **Detailed Error Feedback:** Human-friendly responses for private videos or unsupported platforms.
- ⚡ **Asynchronous Engine:** Non-blocking operations ensure the bot remains lightning-fast under load.
- 🛡️ **Privacy First:** Every interaction is ephemeral and anonymous. No tracking, no logs, just media.
- 🐳 **Docker Powered:** Fully containerized for easy deployment and zero-maintenance operation.

---

## ⚙️ Configuration

Fetchy is configured entirely via the `.env` file in the root directory:

| Key | Description | Default |
| :--- | :--- | :--- |
| `DISCORD_BOT_TOKEN` | Your Discord bot token. | *(required)* |
| `CHANNEL_ID` | The ID of the Discord channel for the dashboard. | *(required)* |
| `STATUS_ROTATION_SPEED` | Seconds between status changes. | `10` |
| `BASE_URL` | Public URL for large-file downloads. | `http://YOUR_IP:8080` |
| `INSTAGRAM_USERNAME` | Instagram username for session auth. | *(optional)* |
| `LINK_REGEX` | Pattern for automatic link detection. | *(Common platforms)* |

---

## 🚀 Getting Started

### 📦 Docker Deployment (Recommended)
The most efficient way to deploy Fetchy is via Docker.

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/CRZX1337/Fetchy
   cd Fetchy
   ```

2. **Configure Environment:**
   ```bash
   cp .env.example .env
   # Edit .env and supply your DISCORD_BOT_TOKEN
   ```

3. **Launch:**
   ```bash
   sudo docker compose up -d --build
   ```

---

### 💻 Local Installation
For direct host execution:

1. **Requirements:**
   - Python 3.11+
   - **FFmpeg** (Must be in your system PATH)

2. **Install:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run:**
   ```bash
   python main.py
   ```

---

## 🛠️ How to Use
1. **Interactive Dashboard**: Click a format button and follow the quality selection prompts.
2. **Auto-Detection**: Simply drop a supported link (YouTube, TikTok, X, Instagram) into the channel, and Fetchy will prompt you for the next steps.
3. **Download**: Your file is delivered via a private ephemeral message.

---

## 📜 Credits & Technology
Fetchy is built on the shoulders of these incredible open-source projects:
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — The engine for media extraction!
- [discord.py](https://github.com/Rapptz/discord.py) — The interface for Discord interactions!
- [FFmpeg](https://ffmpeg.org/) — The power behind media conversion and merging!

---
*Developed with ❤️ by [CRZX1337](https://github.com/CRZX1337/Fetchy)*
