# Audirvana Lyrics Viewer 🎵

**This app was vibe coded and I'm not a dev.**

A lightweight, standalone desktop app that automatically fetches and displays lyrics for whatever you are currently playing in Audirvana. Since Audirvana on Windows doesn't hook into the standard System Media Transport Controls (SMTC), this app uses a clever workaround by monitoring your Last.fm "Now Playing" status.

### Features
* **Auto-Sync:** Silently polls Last.fm in the background and updates lyrics instantly when a new track plays.
* **Dual Providers:** Fetches lyrics from **Genius** or **LRCLIB** (free, open-source). Swap between them with a click.
* **Manual Search:** Editable fields to manually search for any artist or track.
* **Smart Caching:** Saves fetched lyrics locally during your session to prevent duplicate API calls and rate-limiting.
* **Dark Mode UI:** Built with CustomTkinter for a clean, non-distracting aesthetic.

### How to Install & Run (No Code Required)

1. Go to the [Releases](../../releases) page and download the latest `app.exe`.
2. Run the `.exe` (no installation required).
3. Click **⚙ Settings** in the top right.
4. Paste your API keys (see below) and click Save & Reload.
5. Play a song in Audirvana!

### Getting Your Free API Keys
To use this app, you need free API keys from Last.fm and Genius. 
* **Last.fm:** [Create an API account here](https://www.last.fm/api/account/create) to get your API Key and Shared Secret. (Make sure you link your Last.fm account to Audirvana in the player's settings!)
* **Genius:** [Create an API client here](https://genius.com/api-clients) to generate your Access Token.

### For Developers
If you want to run from source or modify the code:
1. Clone the repo.
2. `pip install -r requirements.txt`
3. Run `python app.pyw`

To build the executable yourself:
`pyinstaller --noconsole --onefile app.pyw`