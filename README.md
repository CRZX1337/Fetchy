![Fetchy Banner](./media/banner.png)

# 🚀 Fetchy — Your Personal Media Assistant

Fetchy is a high-performance, privacy-focused Discord bot designed to download and manage media from various platforms seamlessly. Built with a modern modular architecture, Fetchy provides a clean, persistent dashboard for all your extraction needs.

---

## 📖 About Fetchy

![Fetchy Logo](./media/logo.png)

Fetchy was created to bridge the gap between complex media extraction tools and the ease of use of a Discord interface. Operating as a professional personal assistant, Fetchy handles the heavy lifting of processing and delivering media directly to your hands while ensuring your interactions remain completely private and anonymous.

---

## ✨ Key Features

- 🎬 **Video Extraction:** High-quality MP4 downloads with automatic format merging.
- 🎵 **Audio Extraction:** High-fidelity MP3 conversion for your favorite tracks.
- 🖼️ **Picture Extraction:** High-resolution preview image extraction (PNG).
- ⚡ **Asynchronous Processing:** Non-blocking operations ensure the system remains responsive.
- 🛡️ **Privacy Centric:** Completely anonymous interactions with secure ephemeral responses.
- 🧹 **Automated Infrastructure:** Integrated disk cleanup and Docker support for a maintenance-free experience.

---

## 🚀 Getting Started

### 📦 Docker Deployment (Recommended)
The most efficient way to deploy Fetchy is via Docker. This ensures a consistent environment with all required system dependencies pre-configured.

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

3. **Deploy:**
   ```bash
   sudo docker compose up -d --build
   ```

---

### 💻 Local Installation
If you prefer to run the system directly on your host machine:

1. **System Requirements:**
   - Python 3.10+
   - **FFmpeg** (Must be accessible in your system PATH)

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the Application:**
   ```bash
   python main.py
   ```

---

## 🛠️ How to Use
Fetchy utilizes a centralized **Dashboard** for a streamlined experience:

1. **Navigate** to your designated dashboard channel.
2. **Select your format** using the interactive buttons (Video, Audio, or Picture).
3. **Submit your link** in the secure modal popup.
4. **Retrieve** your file directly from the private ephemeral response.

## 📜 Credits & Technology
Fetchy is built on the shoulders of these incredible open-source projects:
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — High-performance media extraction.
- [discord.py](https://github.com/Rapptz/discord.py) — Modern Discord API wrapper.
- [Docker](https://www.docker.com/) — Containerization and infrastructure management.

---
*Developed with care by [CRZX1337](https://github.com/CRZX1337/Fetchy)*
