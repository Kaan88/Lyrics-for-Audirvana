import customtkinter as ctk
import pylast
import lyricsgenius
import requests
import threading
import time
import json
import os
import sys
import re

CONFIG_FILE = "config.json"

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def clean_title(title):
    title = re.sub(r'[\(\[].*?[\)\]]', '', title)
    title = re.sub(r'\s*-\s*(Remaster|Live|Mono|Stereo|Acoustic|Bonus|Instrumental|Radio Edit).*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+(feat\.|ft\.).*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title).strip()
    return title

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("API & Sync Settings")
        self.geometry("400x420")
        self.parent = parent
        self.transient(parent)
        self.grab_set()
        try: self.iconbitmap(resource_path("icon.ico"))
        except Exception: pass
        self.create_widgets()
        self.load_current_settings()

    def create_widgets(self):
        ctk.CTkLabel(self, text="Last.fm Username:").pack(pady=(10, 0))
        self.lf_user = ctk.CTkEntry(self, width=300, fg_color="#1e1e1e")
        self.lf_user.pack()
        ctk.CTkLabel(self, text="Last.fm API Key:").pack(pady=(10, 0))
        self.lf_key = ctk.CTkEntry(self, width=300, fg_color="#1e1e1e")
        self.lf_key.pack()
        ctk.CTkLabel(self, text="Last.fm API Secret:").pack(pady=(10, 0))
        self.lf_secret = ctk.CTkEntry(self, width=300, fg_color="#1e1e1e", show="*")
        self.lf_secret.pack()
        ctk.CTkLabel(self, text="Genius Access Token:").pack(pady=(10, 0))
        self.genius_token = ctk.CTkEntry(self, width=300, fg_color="#1e1e1e", show="*")
        self.genius_token.pack()
        ctk.CTkLabel(self, text="Default Sync Offset (seconds):").pack(pady=(10, 0))
        self.sync_offset_entry = ctk.CTkEntry(self, width=300, fg_color="#1e1e1e")
        self.sync_offset_entry.pack()
        ctk.CTkButton(self, text="Save & Reload", fg_color="#555555", command=self.save_settings).pack(pady=20)

    def load_current_settings(self):
        self.lf_user.insert(0, self.parent.config.get("LASTFM_USERNAME", ""))
        self.lf_key.insert(0, self.parent.config.get("LASTFM_API_KEY", ""))
        self.lf_secret.insert(0, self.parent.config.get("LASTFM_API_SECRET", ""))
        self.genius_token.insert(0, self.parent.config.get("GENIUS_ACCESS_TOKEN", ""))
        self.sync_offset_entry.insert(0, str(self.parent.config.get("DEFAULT_OFFSET", -4.0)))

    def save_settings(self):
        try: new_offset = float(self.sync_offset_entry.get().strip())
        except ValueError: new_offset = -4.0
        self.parent.config = {"LASTFM_USERNAME": self.lf_user.get().strip(), "LASTFM_API_KEY": self.lf_key.get().strip(), "LASTFM_API_SECRET": self.lf_secret.get().strip(), "GENIUS_ACCESS_TOKEN": self.genius_token.get().strip(), "DEFAULT_OFFSET": new_offset}
        with open(CONFIG_FILE, "w") as f: json.dump(self.parent.config, f, indent=4)
        self.parent.base_offset = new_offset
        self.parent.manual_nudge = 0.0 # Reset nudge on new config save
        self.parent.update_sync_label()
        self.parent.setup_apis()
        self.destroy()

class LyricsApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.configure(fg_color="#121212")
        self.title("Audirvana Lyrics Viewer")
        self.geometry("520x880")
        try: self.iconbitmap(resource_path("icon.ico"))
        except Exception: pass
        
        self.config = self.load_config()
        self.current_provider = "LRCLIB"
        self.parsed_lrc = []
        self.start_time = 0
        
        # SPLIT OFFSETS
        self.base_offset = float(self.config.get("DEFAULT_OFFSET", -4.0))
        self.manual_nudge = 0.0
        
        self.sync_enabled = ctk.BooleanVar(value=True)
        self.auto_sync = ctk.BooleanVar(value=True)
        self.last_manual_scroll_time = 0

        self.setup_apis()
        self.build_ui()

        threading.Thread(target=self.poll_lastfm, daemon=True).start()
        threading.Thread(target=self.sync_loop, daemon=True).start()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f: return json.load(f)
        return {}

    def setup_apis(self):
        self.user = None; self.genius = None
        try:
            # macOS: Python doesn't use the system keychain, so point requests/pylast
            # at certifi's CA bundle to prevent silent HTTPS failures.
            try:
                import certifi, os
                os.environ.setdefault("SSL_CERT_FILE", certifi.where())
                os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
            except ImportError:
                pass
            if all(k in self.config for k in ("LASTFM_API_KEY", "LASTFM_API_SECRET", "LASTFM_USERNAME")):
                network = pylast.LastFMNetwork(api_key=self.config["LASTFM_API_KEY"], api_secret=self.config["LASTFM_API_SECRET"])
                self.user = network.get_user(self.config["LASTFM_USERNAME"])
            if self.config.get("GENIUS_ACCESS_TOKEN"):
                self.genius = lyricsgenius.Genius(self.config["GENIUS_ACCESS_TOKEN"], verbose=False)
        except Exception: pass

    def build_ui(self):
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=15, pady=(10, 5))
        ctk.CTkSwitch(top_bar, text="Auto-Sync Player", variable=self.auto_sync, progress_color="#444444").pack(side="left")
        ctk.CTkButton(top_bar, text="⚙", width=35, fg_color="#222222", command=self.open_settings).pack(side="right")

        search_frame = ctk.CTkFrame(self, fg_color="#1e1e1e")
        search_frame.pack(fill="x", padx=15, pady=5)
        self.artist_entry = ctk.CTkEntry(search_frame, placeholder_text="Artist", fg_color="#121212", border_width=0)
        self.artist_entry.pack(fill="x", padx=10, pady=(10, 5))
        self.title_entry = ctk.CTkEntry(search_frame, placeholder_text="Title", fg_color="#121212", border_width=0)
        self.title_entry.pack(fill="x", padx=10, pady=5)
        
        btn_row = ctk.CTkFrame(search_frame, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(btn_row, text="Search / Restart", width=140, fg_color="#333333", command=self.manual_search).pack(side="left", padx=10)
        self.sync_btn = ctk.CTkButton(btn_row, text="Disable Sync", width=140, fg_color="#552222", command=self.toggle_sync_feature)
        self.sync_btn.pack(side="right", padx=10)

        # TEXTBOX (CENTERED & HAND CURSOR)
        self.textbox = ctk.CTkTextbox(self, font=("Helvetica", 22, "bold"), wrap="word", fg_color="#0a0a0a", text_color="#2a2a2a", cursor="hand2")
        self.textbox.pack(expand=True, fill="both", padx=15, pady=5)
        self.textbox.tag_config("highlight", foreground="#ffffff")
        self.textbox.tag_config("center", justify='center')
        self.textbox.configure(state="disabled")
        
        self.textbox.bind("<Button-1>", self.on_lyrics_click)
        self.textbox.bind("<MouseWheel>", self.on_manual_scroll)

        # BOTTOM CONTROLS
        bottom_controls = ctk.CTkFrame(self, fg_color="transparent")
        bottom_controls.pack(fill="x", pady=15)

        nudge_frame = ctk.CTkFrame(bottom_controls, fg_color="transparent")
        nudge_frame.pack(pady=(0, 10))
        
        self.sync_label = ctk.CTkLabel(nudge_frame, text="", text_color="#ffffff", font=("Helvetica", 12, "bold"))
        self.sync_label.pack(side="left", padx=15)
        self.update_sync_label()

        ctk.CTkButton(nudge_frame, text="-0.5s", width=60, height=30, fg_color="#222222", command=lambda: self.adjust_nudge(-0.5)).pack(side="left", padx=5)
        ctk.CTkButton(nudge_frame, text="Reset", width=60, height=30, fg_color="#222222", command=self.reset_nudge).pack(side="left", padx=5)
        ctk.CTkButton(nudge_frame, text="+0.5s", width=60, height=30, fg_color="#222222", command=lambda: self.adjust_nudge(0.5)).pack(side="left", padx=5)

        provider_frame = ctk.CTkFrame(bottom_controls, fg_color="transparent")
        provider_frame.pack()
        self.btn_lrclib = ctk.CTkButton(provider_frame, text="LRCLIB", width=140, height=35, fg_color="#333333", command=lambda: self.switch_provider("LRCLIB"))
        self.btn_lrclib.grid(row=0, column=0, padx=10)
        self.btn_genius = ctk.CTkButton(provider_frame, text="Genius", width=140, height=35, fg_color="#333333", command=lambda: self.switch_provider("Genius"))
        self.btn_genius.grid(row=0, column=1, padx=10)

    def on_manual_scroll(self, event=None):
        self.last_manual_scroll_time = time.time()

    def on_lyrics_click(self, event):
        if not self.parsed_lrc or not self.sync_enabled.get(): return
        index = self.textbox.index(f"@{event.x},{event.y}")
        line_num = int(index.split(".")[0])
        lrc_index = round((line_num - 13) / 2)
        
        if 0 <= lrc_index < len(self.parsed_lrc):
            clicked_timestamp = self.parsed_lrc[lrc_index][0]
            # Calculate what the nudge SHOULD be to make current time match click
            current_raw_elapsed = (time.time() - self.start_time) - self.base_offset
            self.manual_nudge = current_raw_elapsed - clicked_timestamp
            
            self.last_manual_scroll_time = 0
            self.update_sync_label()
            self.smooth_scroll_to(lrc_index)

    def adjust_nudge(self, amount):
        self.manual_nudge += amount; self.update_sync_label()

    def reset_nudge(self):
        self.manual_nudge = 0.0; self.update_sync_label()

    def update_sync_label(self):
        state = "● SYNC" if self.sync_enabled.get() else "○ STATIC"
        total_offset = self.base_offset + self.manual_nudge
        color = "#ffffff" if self.sync_enabled.get() else "#666666"
        # Display: SYNC -4.0s [+1.5s]
        nudge_str = f" [{self.manual_nudge:+.1f}s]" if self.manual_nudge != 0 else ""
        self.sync_label.configure(text=f"{state} {total_offset:+.1f}s{nudge_str}", text_color=color)

    def toggle_sync_feature(self):
        new_state = not self.sync_enabled.get(); self.sync_enabled.set(new_state); self.update_sync_label()
        if new_state:
            self.textbox.configure(font=("Helvetica", 22, "bold"), text_color="#2a2a2a")
            self.sync_btn.configure(text="Disable Sync", fg_color="#552222")
        else:
            self.textbox.configure(font=("Helvetica", 16), text_color="#d4d4d4")
            self.sync_btn.configure(text="Enable Sync", fg_color="#225522")
            self.textbox.tag_remove("highlight", "1.0", "end")
        self.fetch_and_display_lyrics(self.artist_entry.get().strip(), self.title_entry.get().strip())

    def open_settings(self): SettingsWindow(self)

    def manual_search(self):
        self.auto_sync.set(False); self.manual_nudge = 0.0 # Clear nudge on fresh manual search
        self.fetch_and_display_lyrics(self.artist_entry.get().strip(), self.title_entry.get().strip())

    def switch_provider(self, provider):
        self.current_provider = provider
        self.fetch_and_display_lyrics(self.artist_entry.get().strip(), self.title_entry.get().strip())

    def poll_lastfm(self):
        last_id = ""
        while True:
            if self.auto_sync.get() and self.user:
                try:
                    track = self.user.get_now_playing()
                    if track:
                        song_id = f"{track.artist.name} - {track.title}"
                        if song_id != last_id:
                            last_id = song_id
                            self.manual_nudge = 0.0 # Reset nudge on track change
                            self.after(0, self.update_ui_new_song, track.artist.name, track.title)
                except Exception: pass
            time.sleep(5)

    def update_ui_new_song(self, artist, title):
        clean = clean_title(title)
        self.artist_entry.delete(0, "end"); self.artist_entry.insert(0, artist)
        self.title_entry.delete(0, "end"); self.title_entry.insert(0, clean); self.update_sync_label()
        self.fetch_and_display_lyrics(artist, title)

    def parse_lrc_text(self, lrc_content):
        self.parsed_lrc = []
        lines = lrc_content.splitlines()
        for line in lines:
            match = re.search(r'\[(\d+):(\d+\.\d+)\](.*)', line)
            if match:
                minutes, seconds, text = match.groups()
                total_seconds = int(minutes) * 60 + float(seconds)
                if text.strip(): self.parsed_lrc.append((total_seconds, text.strip()))
        self.parsed_lrc.sort()

    def fetch_and_display_lyrics(self, artist, title):
        self.start_time = time.time(); search_title = clean_title(title); lyrics_out = "No lyrics found."
        if self.current_provider == "LRCLIB":
            try:
                r = requests.get("https://lrclib.net/api/get", params={"artist_name": artist, "track_name": search_title}, timeout=5)
                if r.status_code == 200:
                    data = r.json(); lrc = data.get("syncedLyrics")
                    if lrc:
                        self.parse_lrc_text(lrc); lyrics_out = "\n\n".join([line[1] for line in self.parsed_lrc])
                    else: lyrics_out = data.get("plainLyrics") or lyrics_out; self.parsed_lrc = []
            except Exception: pass
        elif self.current_provider == "Genius" and self.genius:
            self.parsed_lrc = []
            try:
                song = self.genius.search_song(search_title, artist)
                if song:
                    def norm(s): return re.sub(r'[^a-z0-9 ]', '', s.lower())
                    if norm(artist) in norm(song.artist) and norm(search_title) in norm(song.title):
                        lyrics_out = song.lyrics.replace("Embed", "")
                    else: lyrics_out = "Genius mismatch."
            except Exception: pass
        self.after(0, self.show_lyrics, lyrics_out)

    def show_lyrics(self, text):
        self.textbox.configure(state="normal"); self.textbox.delete("0.0", "end")
        buffer = "\n" * 12; self.textbox.insert("0.0", buffer + text + buffer)
        self.textbox.tag_add("center", "1.0", "end"); self.textbox.configure(state="disabled")
        if not self.sync_enabled.get(): self.textbox.yview_moveto(0)

    def sync_loop(self):
        last_idx = -1
        while True:
            if self.parsed_lrc and self.sync_enabled.get() and self.current_provider == "LRCLIB":
                # FINAL PRECISION MATH
                total_offset = self.base_offset + self.manual_nudge
                elapsed = (time.time() - self.start_time) - total_offset
                
                current_idx = -1
                for i, (ts, txt) in enumerate(self.parsed_lrc):
                    if elapsed >= ts: current_idx = i
                    else: break
                if current_idx != last_idx and current_idx != -1:
                    last_idx = current_idx
                    if time.time() - self.last_manual_scroll_time > 3:
                        self.after(0, self.smooth_scroll_to, current_idx)
                    else:
                        self.after(0, self.highlight_only, current_idx)
            time.sleep(0.05)

    def highlight_only(self, index):
        self.textbox.configure(state="normal"); self.textbox.tag_remove("highlight", "1.0", "end")
        line_num = 13 + (index * 2); self.textbox.tag_add("highlight", f"{line_num}.0", f"{line_num}.end"); self.textbox.configure(state="disabled")

    def smooth_scroll_to(self, index):
        self.textbox.configure(state="normal"); self.textbox.tag_remove("highlight", "1.0", "end")
        line_num = 13 + (index * 2); start = f"{line_num}.0"; end = f"{line_num}.end"
        self.textbox.tag_add("highlight", start, end)
        def glide():
            self.textbox.update_idletasks()
            bbox = self.textbox.bbox(start)
            if bbox:
                y_text = bbox[1]; height_box = self.textbox.winfo_height(); current_scroll = float(self.textbox.yview()[0])
                total_content_height = height_box / (float(self.textbox.yview()[1]) - current_scroll)
                offset_pixels = y_text - (height_box / 2); target_scroll = current_scroll + (offset_pixels / total_content_height)
                steps = 6; diff = (target_scroll - current_scroll) / steps
                for _ in range(steps):
                    current_scroll += diff; self.textbox.yview_moveto(max(0.0, current_scroll))
                    self.textbox.update(); time.sleep(0.01)
        threading.Thread(target=glide, daemon=True).start(); self.textbox.configure(state="disabled")

if __name__ == "__main__":
    LyricsApp().mainloop()