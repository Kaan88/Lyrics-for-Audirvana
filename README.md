
# Audirvana Lyrics Viewer

**This app was vibe coded and I'm not a dev.**

A minimalist, high-fidelity lyrics companion for **Audirvana Studio (Windows)**. Reads playback position directly from the Audirvana UI for frame-accurate sync — no timing guesses, no offsets needed.

[![App Screenshot](screenshot.png)](screenshot.png)

---

## ✨ Features

- **Exact sync** — reads the playback clock directly from Audirvana's UI via Windows Accessibility (UIA), so lyrics are always in the right place regardless of Last.fm latency.
- **Dual providers** — prioritizes **LRCLIB** for perfectly timed `.lrc` data, falls back to **Genius**
- **Click-to-sync** — click any lyric line to instantly snap the sync to that position.
- **Nudge buttons** — ±0.25s fine-tuning if you need it.
- **Artist and Album art** Hover to view fullsize.
- **Static mode** — toggle sync off to easily read lyrics as a whole.
- **Fuzzy matching** — if LRCLIB can't find an exact match, it suggests the closest result with a confirmation popup.
- **LRC cache** — recently fetched lyrics are cached in memory so provider switching is instant.
- **Smart title cleaner** — strips remaster tags, vinyl side markers, feat. credits for better search accuracy.
- **Fully configurable** — fonts, colours, sizes, polling intervals, fuzzy threshold all adjustable in Settings.

---

## 🚀 Getting Started

### Requirements

- **Windows** (UIA screen reading is Windows-only)
- A **Last.fm** account with scrobbling enabled in Audirvana
- Last.fm API key + secret — [get them here](https://www.last.fm/api/account/create)
- Genius Access Token (optional, for unsynced lyrics fallback) — [get it here](https://genius.com/api-clients)

### Installation

```
pip install -r requirements.txt
python lyrics.pyw
```

### Setup

1. Click **⚙** to open Settings.
2. Enter your Last.fm Username, API Key, and Secret.
3. Optionally add your Genius Access Token.
4. Click **Save & Apply**.

The app will detect what's playing in Audirvana automatically. The default sync offset is `0.0` — you shouldn't need to change it.

---

## 🎛 Usage

| Control | What it does |
|---|---|
| **Auto-Sync Player** switch | Enables/disables automatic Last.fm track detection |
| **Search / Restart** button | Manually search by artist + title (doesn't disable auto-sync) |
| **Click a lyric line** | Snaps sync to that line |
| **−0.25s / +0.25s** | Fine-tune timing on the fly |
| **Reset** | Clears manual nudge |
| **LRCLIB / Genius** buttons | Switch lyrics provider |
| **Disable/Enable Sync** | Toggles between karaoke and static reading mode |

---

## 🛠 Building from Source

```
pip install pyinstaller
pyinstaller lyrics.spec
```

The included `lyrics.spec` handles all the necessary options (CustomTkinter data files, UPX compression, excludes).

---

## How Sync Works

Audirvana Studio exposes its playback clock as accessible text elements in the Windows UI tree. This app reads those elements every 0.5 seconds (configurable) and interpolates between whole-second ticks for sub-second accuracy. Last.fm is only used for song-change detection — it plays no role in timing.

---

## License

MIT
