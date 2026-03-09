import customtkinter as ctk
import pylast
import lyricsgenius
import requests
import threading
import time
import json
import os

CONFIG_FILE = "config.json"

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("API Settings")
        self.geometry("400x350")
        self.parent = parent
        
        # Bring to front
        self.transient(parent)
        self.grab_set()

        try:
            self.iconbitmap("icon.ico")
        except Exception:
            pass

        self.create_widgets()
        self.load_current_settings()

    def create_widgets(self):
        ctk.CTkLabel(self, text="Last.fm Username:").pack(pady=(10, 0))
        self.lf_user = ctk.CTkEntry(self, width=300, fg_color="#1e1e1e", border_color="#444444")
        self.lf_user.pack()

        ctk.CTkLabel(self, text="Last.fm API Key:").pack(pady=(10, 0))
        self.lf_key = ctk.CTkEntry(self, width=300, fg_color="#1e1e1e", border_color="#444444")
        self.lf_key.pack()

        ctk.CTkLabel(self, text="Last.fm API Secret:").pack(pady=(10, 0))
        self.lf_secret = ctk.CTkEntry(self, width=300, fg_color="#1e1e1e", border_color="#444444", show="*")
        self.lf_secret.pack()

        ctk.CTkLabel(self, text="Genius Access Token:").pack(pady=(10, 0))
        self.genius_token = ctk.CTkEntry(self, width=300, fg_color="#1e1e1e", border_color="#444444", show="*")
        self.genius_token.pack()

        ctk.CTkButton(self, text="Save & Reload", fg_color="#555555", hover_color="#333333", command=self.save_settings).pack(pady=20)

    def load_current_settings(self):
        self.lf_user.insert(0, self.parent.config.get("LASTFM_USERNAME", ""))
        self.lf_key.insert(0, self.parent.config.get("LASTFM_API_KEY", ""))
        self.lf_secret.insert(0, self.parent.config.get("LASTFM_API_SECRET", ""))
        self.genius_token.insert(0, self.parent.config.get("GENIUS_ACCESS_TOKEN", ""))

    def save_settings(self):
        self.parent.config = {
            "LASTFM_USERNAME": self.lf_user.get().strip(),
            "LASTFM_API_KEY": self.lf_key.get().strip(),
            "LASTFM_API_SECRET": self.lf_secret.get().strip(),
            "GENIUS_ACCESS_TOKEN": self.genius_token.get().strip()
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.parent.config, f, indent=4)
        
        self.parent.setup_apis()
        self.destroy()

class LyricsApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # UI Theme (Clean, monochrome grey tones)
        ctk.set_appearance_mode("dark")
        self.configure(fg_color="#1e1e1e")

        self.title("Audirvana Lyrics")
        self.geometry("500x700")
        self.minsize(350, 550)
        
        # Load the custom window icon safely
        try:
            self.iconbitmap("icon.ico")
        except Exception:
            pass # Fails silently if icon.ico is missing
        
        self.current_provider = "Genius"
        self.lyrics_cache = {}
        self.config = self.load_config()
        self.auto_sync = ctk.BooleanVar(value=True)

        self.setup_apis()
        self.build_ui()

        # Start background poller
        self.poll_thread = threading.Thread(target=self.poll_lastfm, daemon=True)
        self.poll_thread.start()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        return {}

    def setup_apis(self):
        self.user = None
        self.genius = None
        try:
            if all(k in self.config for k in ("LASTFM_API_KEY", "LASTFM_API_SECRET", "LASTFM_USERNAME")):
                network = pylast.LastFMNetwork(
                    api_key=self.config["LASTFM_API_KEY"], 
                    api_secret=self.config["LASTFM_API_SECRET"]
                )
                self.user = network.get_user(self.config["LASTFM_USERNAME"])
            
            if "GENIUS_ACCESS_TOKEN" in self.config and self.config["GENIUS_ACCESS_TOKEN"]:
                self.genius = lyricsgenius.Genius(self.config["GENIUS_ACCESS_TOKEN"], verbose=False)
                self.genius.remove_section_headers = True
        except Exception as e:
            print(f"API Setup Error: {e}")

    def build_ui(self):
        # 1. Top Bar (Settings & Sync Toggle)
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=15, pady=(10, 0))
        
        ctk.CTkSwitch(top_bar, text="Auto-Sync Last.fm", variable=self.auto_sync, 
                      progress_color="#555555", button_color="#888888").pack(side="left")
        ctk.CTkButton(top_bar, text="⚙ Settings", width=80, fg_color="#333333", hover_color="#222222", 
                      command=self.open_settings).pack(side="right")

        # 2. Search Inputs (Editable Fields)
        search_frame = ctk.CTkFrame(self, fg_color="#2b2b2b")
        search_frame.pack(fill="x", padx=15, pady=15)

        self.artist_entry = ctk.CTkEntry(search_frame, placeholder_text="Artist Name", fg_color="#1e1e1e", border_color="#444444")
        self.artist_entry.pack(fill="x", padx=10, pady=(10, 5))

        self.title_entry = ctk.CTkEntry(search_frame, placeholder_text="Song Title", fg_color="#1e1e1e", border_color="#444444")
        self.title_entry.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(search_frame, text="Search Lyrics", fg_color="#555555", hover_color="#444444", 
                      command=self.manual_search).pack(pady=(0, 10))

        # 3. Lyrics Text Box
        self.textbox = ctk.CTkTextbox(self, font=("Helvetica", 14), wrap="word", fg_color="#252525", text_color="#d4d4d4")
        self.textbox.pack(expand=True, fill="both", padx=15, pady=5)
        self.textbox.insert("0.0", "Enter API keys in Settings, then play a song in Audirvana or search manually.")
        self.textbox.configure(state="disabled")

        # 4. Provider Buttons
        self.button_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.button_frame.pack(pady=15)

        self.btn_genius = self.create_provider_btn("Genius", 0)
        self.btn_lrclib = self.create_provider_btn("LRCLIB", 1)
        
        self.update_button_colors()

    def create_provider_btn(self, name, col):
        btn = ctk.CTkButton(self.button_frame, text=name, width=120, 
                            command=lambda: self.switch_provider(name))
        btn.grid(row=0, column=col, padx=10)
        return btn

    def update_button_colors(self):
        active_color = "#666666"
        inactive_color = "#333333"
        self.btn_genius.configure(fg_color=active_color if self.current_provider == "Genius" else inactive_color)
        self.btn_lrclib.configure(fg_color=active_color if self.current_provider == "LRCLIB" else inactive_color)

    def open_settings(self):
        SettingsWindow(self)

    def manual_search(self):
        self.auto_sync.set(False) # Turn off auto-sync when searching manually
        artist = self.artist_entry.get().strip()
        title = self.title_entry.get().strip()
        if artist and title:
            self.update_lyrics_ui("Loading lyrics...")
            threading.Thread(target=self.fetch_and_display_lyrics, args=(artist, title)).start()

    def switch_provider(self, provider):
        self.current_provider = provider
        self.update_button_colors()
        
        artist = self.artist_entry.get().strip()
        title = self.title_entry.get().strip()
        if artist and title:
            self.update_lyrics_ui(f"Loading from {provider}...")
            threading.Thread(target=self.fetch_and_display_lyrics, args=(artist, title)).start()

    def poll_lastfm(self):
        current_playing_id = ""
        while True:
            if self.auto_sync.get() and self.user:
                try:
                    now_playing = self.user.get_now_playing()
                    if now_playing:
                        artist = now_playing.artist.name
                        title = now_playing.title
                        song_id = f"{artist} - {title}"

                        if song_id != current_playing_id:
                            current_playing_id = song_id
                            
                            self.after(0, self.update_entries, artist, title)
                            self.after(0, self.update_lyrics_ui, "Loading lyrics...")
                            
                            self.fetch_and_display_lyrics(artist, title)
                except Exception:
                    pass # Silently ignore network blips
            time.sleep(5)

    def update_entries(self, artist, title):
        self.artist_entry.delete(0, "end")
        self.artist_entry.insert(0, artist)
        self.title_entry.delete(0, "end")
        self.title_entry.insert(0, title)

    def fetch_and_display_lyrics(self, artist, title):
        cache_key = f"{artist}_{title}_{self.current_provider}"
        if cache_key in self.lyrics_cache:
            self.after(0, self.update_lyrics_ui, self.lyrics_cache[cache_key])
            return

        lyrics = "Lyrics not found on this provider. Try another one!"

        if self.current_provider == "Genius" and self.genius:
            try:
                song = self.genius.search_song(title, artist)
                if song: lyrics = song.lyrics.replace("Embed", "") 
            except Exception:
                lyrics = "Error connecting to Genius API."

        elif self.current_provider == "LRCLIB":
            try:
                response = requests.get(f"https://lrclib.net/api/get?artist_name={artist}&track_name={title}")
                if response.status_code == 200:
                    data = response.json()
                    lyrics = data.get("plainLyrics") or data.get("syncedLyrics") or lyrics
            except Exception:
                 lyrics = "Error connecting to LRCLIB."

        self.lyrics_cache[cache_key] = lyrics
        self.after(0, self.update_lyrics_ui, lyrics)

    def update_lyrics_ui(self, text):
        self.textbox.configure(state="normal")
        self.textbox.delete("0.0", "end")
        self.textbox.insert("0.0", text)
        self.textbox.configure(state="disabled")

if __name__ == "__main__":
    app = LyricsApp()
    app.mainloop()