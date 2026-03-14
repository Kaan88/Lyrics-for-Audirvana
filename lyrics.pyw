import customtkinter as ctk
import tkinter.font as tkfont
import tkinter as tk
import tkinter.colorchooser as colorchooser
import pylast
import lyricsgenius
import requests
import threading
import traceback
import unicodedata
import difflib
import json
import os
import sys
import re
import time
from collections import OrderedDict
from io import BytesIO
try:
    from PIL import Image, ImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

CONFIG_FILE   = "config.json"
HEX_RE        = re.compile(r'^#[0-9a-fA-F]{6}$')
def _log(msg):
    pass

CONFIG_DEFAULTS = {
    # API credentials
    "LASTFM_USERNAME":        "",
    "LASTFM_API_KEY":         "",
    "LASTFM_API_SECRET":      "",
    "GENIUS_ACCESS_TOKEN":    "",
    # Sync
    "DEFAULT_OFFSET":         0.0,
    # Audirvāna accessibility screen-read interval (seconds)
    "SCREEN_POLL_INTERVAL":   0.5,
    # Fuzzy matching
    "FUZZY_THRESHOLD":        0.45,   # artist similarity 0–1 below this → ask user
    # Lyrics cache
    "CACHE_MAX":              50,
    # Scroll animation
    "SCROLL_STEPS":           4,      # animation frames per lyric transition
    "SCROLL_STEP_MS":         10,     # ms between frames
    # Auto-fallback to Genius when LRCLIB finds nothing
    "AUTO_GENIUS_FALLBACK":   True,
    # Lyrics text buffer (blank lines above/below lyrics in textbox)
    "LYRICS_BUFFER_LINES":    12,
    # Window
    "WINDOW_GEOMETRY":        "520x920",
    # Synced lyrics appearance
    "SYNCED_FONT_FAMILY":     "Segoe UI",
    "SYNCED_FONT_SIZE":       22,
    "SYNCED_FONT_BOLD":       True,
    "SYNCED_INACTIVE_COLOR":  "#2a2a2a",
    "SYNCED_NEAR1_COLOR":     "#5a5a5a",
    "SYNCED_NEAR2_COLOR":     "#3d3d3d",
    "SYNCED_HIGHLIGHT_COLOR": "#ffffff",
    "SYNCED_HIGHLIGHT_SIZE":  28,     # font size of the active/highlighted lyric line
    "THUMB_BORDER_COLOR":     "#2a2a2a",
    "THUMB_BORDER_WIDTH":     1,
    # Unsynced / Genius appearance
    "UNSYNCED_FONT_FAMILY":   "Segoe UI",
    "UNSYNCED_FONT_SIZE":     16,
    "UNSYNCED_TEXT_COLOR":    "#d4d4d4",
}


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def normalize_for_search(text):
    if not text: return ""
    text = text.replace('İ', 'I').replace('ı', 'i')
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')

def clean_title_display(title):
    title = re.sub(r'^\d+[\s.\-]*', '', title)
    title = re.sub(r'[\(\[].*?[\)\]]', '', title)
    title = re.sub(r'\s*-\s*(Remaster|Live|Mono|Stereo|Acoustic|Bonus|Instrumental|Radio Edit).*',
                   '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+(feat\.|ft\.).*', '', title, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', title).strip()

def clean_title_for_search(title):
    return normalize_for_search(clean_title_display(title))

def clean_genius_lyrics(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r'^[^\n]*Lyrics\n', '', text, count=1)
    text = re.sub(r'\d*Embed$', '', text).strip()
    return text

def artist_similarity(a: str, b: str) -> float:
    a = normalize_for_search(a).lower().strip()
    b = normalize_for_search(b).lower().strip()
    if not a or not b: return 0.0
    if a in b or b in a: return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Resource helper
# ---------------------------------------------------------------------------

def resource_path(relative_path):
    try:    base_path = sys._MEIPASS
    except Exception: base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# ---------------------------------------------------------------------------
# Settings window
# ---------------------------------------------------------------------------

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("560x920")
        self.resizable(False, True)
        self.parent = parent
        self._saved = False
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        try: self.iconbitmap(resource_path("icon.ico"))
        except Exception: pass
        self._build()
        self._load()

    # ------------------------------------------------------------------ helpers

    def _section(self, frame, text):
        ctk.CTkLabel(frame, text=text, text_color="#555555",
                     font=("Helvetica", 10, "bold")).pack(anchor="w", padx=12, pady=(12, 2))

    def _sep(self, frame):
        """Thin horizontal rule between sections."""
        f = ctk.CTkFrame(frame, height=1, fg_color="#2a2a2a")
        f.pack(fill="x", padx=12, pady=(8, 0))

    def _entry(self, frame, label, show="", width=200):
        ctk.CTkLabel(frame, text=label, text_color="#aaaaaa",
                     font=("Helvetica", 11)).pack(anchor="w", padx=12, pady=(5, 0))
        e = ctk.CTkEntry(frame, width=width, fg_color="#1e1e1e", show=show)
        e.pack(anchor="w", padx=12, pady=(0, 2))
        return e

    def _two_col(self, frame):
        """Returns (left_frame, right_frame) for side-by-side fields."""
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=4)
        lf = ctk.CTkFrame(row, fg_color="transparent")
        rf = ctk.CTkFrame(row, fg_color="transparent")
        lf.pack(side="left", fill="x", expand=True)
        rf.pack(side="left", fill="x", expand=True)
        return lf, rf

    def _num(self, frame, label, width=90):
        ctk.CTkLabel(frame, text=label, text_color="#aaaaaa",
                     font=("Helvetica", 11)).pack(anchor="w", padx=12, pady=(5, 0))
        e = ctk.CTkEntry(frame, width=width, fg_color="#1e1e1e")
        e.pack(anchor="w", padx=12, pady=(0, 2))
        return e

    def _color(self, frame, label):
        ctk.CTkLabel(frame, text=label, text_color="#aaaaaa",
                     font=("Helvetica", 11)).pack(anchor="w", padx=12, pady=(5, 0))
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(anchor="w", padx=12, pady=(0, 2))
        entry = ctk.CTkEntry(row, width=95, fg_color="#1e1e1e")
        entry.pack(side="left", padx=(0, 6))
        swatch = tk.Button(row, width=3, relief="flat", cursor="hand2",
                           bd=0, highlightthickness=1, highlightbackground="#555555")
        swatch.pack(side="left")
        def _upd(*_):
            v = entry.get().strip()
            if HEX_RE.match(v): swatch.configure(bg=v, activebackground=v)
        def _pick():
            cur = entry.get().strip()
            init = cur if HEX_RE.match(cur) else "#ffffff"
            res = colorchooser.askcolor(color=init, title=label, parent=self)
            if res and res[1]:
                entry.delete(0, "end"); entry.insert(0, res[1].upper()); _upd()
        entry.bind("<KeyRelease>", _upd)
        swatch.configure(command=_pick)
        entry._update_swatch = _upd
        return entry

    def _switch(self, frame, label):
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(anchor="w", padx=12, pady=(6, 2))
        v = ctk.BooleanVar()
        ctk.CTkSwitch(row, text=label, variable=v,
                      progress_color="#444444").pack(side="left")
        return v

    def _font_picker(self, frame, label, on_change=None):
        ctk.CTkLabel(frame, text=label, text_color="#aaaaaa",
                     font=("Helvetica", 11)).pack(anchor="w", padx=12, pady=(5, 0))
        var = tk.StringVar(); sv = tk.StringVar()
        outer = ctk.CTkFrame(frame, fg_color="#1e1e1e", corner_radius=6)
        outer.pack(padx=12, pady=(0, 4), fill="x")
        ctk.CTkEntry(outer, textvariable=sv, placeholder_text="Search font…",
                     fg_color="#2a2a2a", border_width=0).pack(fill="x", padx=6, pady=(5, 2))
        lbf = ctk.CTkFrame(outer, fg_color="#1e1e1e")
        lbf.pack(fill="x", padx=6, pady=(0, 5))
        sb = tk.Scrollbar(lbf, orient="vertical", bg="#2a2a2a", troughcolor="#1e1e1e",
                          activebackground="#555555", relief="flat", bd=0)
        lb = tk.Listbox(lbf, yscrollcommand=sb.set, height=5,
                        bg="#1e1e1e", fg="#cccccc", selectbackground="#3a3a3a",
                        selectforeground="#ffffff", relief="flat",
                        highlightthickness=0, bd=0, font=("Helvetica", 11),
                        activestyle="none")
        sb.config(command=lb.yview); sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)
        fonts = self.parent.font_families
        def refresh(*_):
            term = sv.get().lower(); lb.delete(0, "end")
            for f in fonts:
                if term in f.lower(): lb.insert("end", f)
            cur = var.get()
            for i in range(lb.size()):
                if lb.get(i) == cur:
                    lb.selection_clear(0, "end")
                    lb.selection_set(i)
                    lb.see(i)
                    break
        def on_sel(_):
            sel = lb.curselection()
            if sel:
                var.set(lb.get(sel[0]))
                if on_change:
                    on_change(var.get())
        sv.trace_add("write", refresh)
        lb.bind("<<ListboxSelect>>", on_sel)
        refresh()
        var._lb = lb
        var._refresh = refresh
        return var

    def _preview_synced_font(self, *_):
        font_name = (self.synced_family_var.get() or self.parent.cfg("SYNCED_FONT_FAMILY") or "Segoe UI").strip()
        self.parent.preview_synced_font(font_name)

    def _preview_unsynced_font(self, *_):
        font_name = (self.unsynced_family_var.get() or self.parent.cfg("UNSYNCED_FONT_FAMILY") or "Segoe UI").strip()
        self.parent.preview_unsynced_font(font_name)

    def _on_close(self):
        if not self._saved:
            self.parent.apply_appearance()
        self.destroy()

    # ------------------------------------------------------------------ build

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="#181818")
        scroll.pack(fill="both", expand=True, padx=8, pady=8)

        # ── API CREDENTIALS ──────────────────────────────────────────────────
        self._section(scroll, "API CREDENTIALS")
        l, r = self._two_col(scroll)
        self.lf_user   = self._entry(l, "Last.fm Username")
        self.lf_key    = self._entry(l, "Last.fm API Key")
        self.lf_secret = self._entry(r, "Last.fm API Secret", show="*")
        self.genius_tok = self._entry(r, "Genius Access Token", show="*")

        self._sep(scroll)

        # ── SYNC ─────────────────────────────────────────────────────────────
        self._section(scroll, "SYNC")
        l, r = self._two_col(scroll)
        self.sync_offset     = self._num(l, "Default offset (seconds)")
        self.screen_poll_int = self._num(r, "Audirvāna read interval (seconds)")

        self._sep(scroll)

        # ── SYNCED LYRICS ────────────────────────────────────────────────────
        self._section(scroll, "SYNCED LYRICS  (LRCLIB)")
        self.synced_family_var = self._font_picker(scroll, "Font Family", self._preview_synced_font)
        l, r = self._two_col(scroll)
        self.synced_size      = self._num(l, "Inactive size")
        self.synced_hl_size   = self._num(l, "Highlight size")
        self.synced_bold_var  = self._switch(l, "Bold")
        self.synced_inactive  = self._color(r, "Inactive colour")
        self.synced_near1     = self._color(r, "Near line 1 colour")
        self.synced_near2     = self._color(r, "Near line 2 colour")
        self.synced_highlight = self._color(r, "Highlight colour")

        self._sep(scroll)

        # ── UNSYNCED / GENIUS ─────────────────────────────────────────────────
        self._section(scroll, "UNSYNCED / GENIUS")
        self.unsynced_family_var = self._font_picker(scroll, "Font Family", self._preview_unsynced_font)
        l, r = self._two_col(scroll)
        self.unsynced_size  = self._num(l, "Font size")
        self.unsynced_color = self._color(r, "Text colour")

        self._sep(scroll)

        # ── ADVANCED ─────────────────────────────────────────────────────────
        self._section(scroll, "THUMBNAILS")
        l, r = self._two_col(scroll)
        self.thumb_border_width = self._num(l, "Thumbnail border width")
        self.thumb_border_color = self._color(r, "Thumbnail border colour")

        self._sep(scroll)

        self._section(scroll, "ADVANCED")
        l, r = self._two_col(scroll)
        self.fuzzy_threshold = self._num(l, "Fuzzy match threshold (0–1)")
        self.cache_max       = self._num(l, "Max cached songs")
        self.scroll_steps    = self._num(r, "Scroll animation steps")
        self.scroll_step_ms  = self._num(r, "Scroll step delay (ms)")
        self.lyrics_buffer   = self._num(r, "Lyrics padding lines")
        self.auto_fallback_var = self._switch(scroll, "Auto-fallback to Genius when LRCLIB has no results")

        self._sep(scroll)

        self._error_label = ctk.CTkLabel(scroll, text="", text_color="#ff6666",
                                         font=("Helvetica", 11))
        self._error_label.pack(padx=12, pady=(8, 0))
        ctk.CTkButton(scroll, text="Save & Apply", fg_color="#444444",
                      hover_color="#555555", width=480,
                      command=self._save).pack(padx=12, pady=(4, 20))

    # ------------------------------------------------------------------ load

    def _load(self):
        p = self.parent
        def ins(w, k): w.insert(0, str(p.cfg(k)))
        def ins_c(w, k): w.insert(0, str(p.cfg(k))); w._update_swatch()
        def sfont(v, k): v.set(p.cfg(k)); v._refresh()

        ins(self.lf_user,       "LASTFM_USERNAME")
        ins(self.lf_key,        "LASTFM_API_KEY")
        ins(self.lf_secret,     "LASTFM_API_SECRET")
        ins(self.genius_tok,    "GENIUS_ACCESS_TOKEN")
        ins(self.sync_offset,    "DEFAULT_OFFSET")
        ins(self.screen_poll_int,"SCREEN_POLL_INTERVAL")
        sfont(self.synced_family_var, "SYNCED_FONT_FAMILY")
        ins(self.synced_size,     "SYNCED_FONT_SIZE")
        ins(self.synced_hl_size,  "SYNCED_HIGHLIGHT_SIZE")
        self.synced_bold_var.set(p.cfg("SYNCED_FONT_BOLD"))
        ins_c(self.synced_inactive,  "SYNCED_INACTIVE_COLOR")
        ins_c(self.synced_near1,     "SYNCED_NEAR1_COLOR")
        ins_c(self.synced_near2,     "SYNCED_NEAR2_COLOR")
        ins_c(self.synced_highlight, "SYNCED_HIGHLIGHT_COLOR")
        sfont(self.unsynced_family_var, "UNSYNCED_FONT_FAMILY")
        ins(self.unsynced_size,    "UNSYNCED_FONT_SIZE")
        ins_c(self.unsynced_color, "UNSYNCED_TEXT_COLOR")
        ins(self.thumb_border_width, "THUMB_BORDER_WIDTH")
        ins_c(self.thumb_border_color, "THUMB_BORDER_COLOR")
        ins(self.fuzzy_threshold,  "FUZZY_THRESHOLD")
        ins(self.cache_max,        "CACHE_MAX")
        ins(self.scroll_steps,     "SCROLL_STEPS")
        ins(self.scroll_step_ms,   "SCROLL_STEP_MS")
        ins(self.lyrics_buffer,    "LYRICS_BUFFER_LINES")
        self.auto_fallback_var.set(p.cfg("AUTO_GENIUS_FALLBACK"))

    # ------------------------------------------------------------------ save

    def _save(self):
        def fget(w): return w.get().strip()
        def fnum(w, key, cast=int):
            try: return cast(fget(w))
            except ValueError: return CONFIG_DEFAULTS[key]
        try:    offset = float(fget(self.sync_offset))
        except (ValueError, TypeError): offset = CONFIG_DEFAULTS["DEFAULT_OFFSET"]

        for val, name in [
            (fget(self.synced_inactive),  "Synced Inactive Colour"),
            (fget(self.synced_near1),     "Synced Near Line 1 Colour"),
            (fget(self.synced_near2),     "Synced Near Line 2 Colour"),
            (fget(self.synced_highlight), "Synced Highlight Colour"),
            (fget(self.thumb_border_color), "Thumbnail Border Colour"),
            (fget(self.unsynced_color),   "Unsynced Text Colour"),
        ]:
            if val and not HEX_RE.match(val):
                self._error_label.configure(text=f"Invalid hex — {name}: {val!r}")
                return
        self._error_label.configure(text="")

        self.parent.config.update({
            "LASTFM_USERNAME":        fget(self.lf_user),
            "LASTFM_API_KEY":         fget(self.lf_key),
            "LASTFM_API_SECRET":      fget(self.lf_secret),
            "GENIUS_ACCESS_TOKEN":    fget(self.genius_tok),
            "DEFAULT_OFFSET":         offset,
            "SCREEN_POLL_INTERVAL":   fnum(self.screen_poll_int, "SCREEN_POLL_INTERVAL", float),
            "SYNCED_FONT_FAMILY":     self.synced_family_var.get() or CONFIG_DEFAULTS["SYNCED_FONT_FAMILY"],
            "SYNCED_FONT_SIZE":       fnum(self.synced_size,     "SYNCED_FONT_SIZE"),
            "SYNCED_HIGHLIGHT_SIZE":  fnum(self.synced_hl_size,  "SYNCED_HIGHLIGHT_SIZE"),
            "SYNCED_FONT_BOLD":       self.synced_bold_var.get(),
            "SYNCED_INACTIVE_COLOR":  fget(self.synced_inactive)  or CONFIG_DEFAULTS["SYNCED_INACTIVE_COLOR"],
            "SYNCED_HIGHLIGHT_COLOR": fget(self.synced_highlight) or CONFIG_DEFAULTS["SYNCED_HIGHLIGHT_COLOR"],
            "UNSYNCED_FONT_FAMILY":   self.unsynced_family_var.get() or CONFIG_DEFAULTS["UNSYNCED_FONT_FAMILY"],
            "UNSYNCED_FONT_SIZE":     fnum(self.unsynced_size,   "UNSYNCED_FONT_SIZE"),
            "UNSYNCED_TEXT_COLOR":    fget(self.unsynced_color)  or CONFIG_DEFAULTS["UNSYNCED_TEXT_COLOR"],
            "THUMB_BORDER_WIDTH":     fnum(self.thumb_border_width, "THUMB_BORDER_WIDTH"),
            "THUMB_BORDER_COLOR":     fget(self.thumb_border_color) or CONFIG_DEFAULTS["THUMB_BORDER_COLOR"],
            "FUZZY_THRESHOLD":        fnum(self.fuzzy_threshold, "FUZZY_THRESHOLD", float),
            "CACHE_MAX":              fnum(self.cache_max,       "CACHE_MAX"),
            "SCROLL_STEPS":           fnum(self.scroll_steps,    "SCROLL_STEPS"),
            "SCROLL_STEP_MS":         fnum(self.scroll_step_ms,  "SCROLL_STEP_MS"),
            "LYRICS_BUFFER_LINES":    fnum(self.lyrics_buffer,   "LYRICS_BUFFER_LINES"),
            "AUTO_GENIUS_FALLBACK":   self.auto_fallback_var.get(),
        })
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.parent.config, f, indent=4)
        self.parent.base_offset  = offset
        self.parent.manual_nudge = 0.0
        self.parent.update_sync_label()
        self.parent.setup_apis()
        self.parent.apply_appearance()
        self.parent._apply_thumb_border()
        self._saved = True
        self.destroy()


# ---------------------------------------------------------------------------
# Fuzzy match confirmation popup
# ---------------------------------------------------------------------------

class FuzzyMatchPopup(ctk.CTkToplevel):
    def __init__(self, parent, matched_artist, matched_title, on_yes, on_no):
        super().__init__(parent)
        self.title("Fuzzy Match")
        self.resizable(False, False)
        self.transient(parent)
        self.configure(fg_color="#1a1a1a")
        try: self.iconbitmap(resource_path("icon.ico"))
        except Exception: pass
        popup_w, popup_h = 300, 160
        px = parent.winfo_x() + parent.winfo_width() - popup_w - 20
        py = parent.winfo_y() + 60
        # Clamp to screen bounds
        screen_w = parent.winfo_screenwidth()
        screen_h = parent.winfo_screenheight()
        px = max(0, min(px, screen_w - popup_w))
        py = max(0, min(py, screen_h - popup_h))
        self.geometry(f"{popup_w}x{popup_h}+{px}+{py}")
        ctk.CTkLabel(self, text="Low-confidence fuzzy match found:",
                     text_color="#888888", font=("Helvetica", 11)).pack(pady=(14, 4))
        ctk.CTkLabel(self, text=f'\u201c{matched_title}\u201d',
                     text_color="#ffffff", font=("Helvetica", 13, "bold"),
                     wraplength=270).pack(padx=12)
        ctk.CTkLabel(self, text=f"by  {matched_artist}",
                     text_color="#aaaaaa", font=("Helvetica", 11)).pack(pady=(2, 12))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack()
        ctk.CTkButton(row, text="Use it", width=110, fg_color="#335533",
                      hover_color="#446644",
                      command=lambda: self._respond(True, on_yes, on_no)).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Skip", width=110, fg_color="#333333",
                      hover_color="#444444",
                      command=lambda: self._respond(False, on_yes, on_no)).pack(side="left", padx=8)

    def _respond(self, accepted, on_yes, on_no):
        self.destroy()
        (on_yes if accepted else on_no)()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class LyricsApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        bad_fonts = {"Wingdings", "Wingdings 2", "Wingdings 3", "Webdings", "Symbol", "Marlett"}
        preferred_fonts = ["Segoe UI", "Helvetica", "Verdana", "Tahoma", "Arial"]
        fonts = sorted({f for f in tkfont.families() if f not in bad_fonts}, key=str.casefold)
        for name in reversed(preferred_fonts):
            if name in fonts:
                fonts.remove(name)
            fonts.insert(0, name)
        self.font_families = fonts

        ctk.set_appearance_mode("dark")
        self.configure(fg_color="#121212")
        self.title("Audirvāna Lyrics Viewer")
        try: self.iconbitmap(resource_path("icon.ico"))
        except Exception: pass

        self.config = self.load_config()
        self.geometry(self.cfg("WINDOW_GEOMETRY"))
        self._geo_save_id = None

        self.current_provider = "LRCLIB"

        self._lrc_lock        = threading.Lock()
        self._parsed_lrc_safe = []

        self.audirvana_pos       = 0.0
        self.audirvana_read_wall = time.time()
        self.audirvana_duration  = 0.0
        self.audirvana_ok        = False
        self._audir_prev_raw     = -1    # last raw pos from UIA, for change detection
        self._audir_prev_dur     = -1.0  # last duration from UIA
        self._song_change_event  = threading.Event()  # signals poll_lastfm to fetch
        self._skip_debounce_until = 0.0  # suppress rapid song-change signals

        self.base_offset  = float(self.cfg("DEFAULT_OFFSET"))
        self.manual_nudge = 0.0

        self.sync_enabled = ctk.BooleanVar(value=True)
        self.auto_sync    = ctk.BooleanVar(value=True)
        self.last_manual_scroll_time = 0
        self.window_visible = True

        self._api_call_count   = 0
        self._api_lock         = threading.Lock()
        self._poll_reset       = False
        self._last_duration_displayed = -1
        self._initial_poll_done = False     # prevents duplicate fetch on startup
        self._initial_song_id  = ""        # song_id from initial poll, carried into poll_lastfm

        self._lyrics_cache: OrderedDict = OrderedDict()
        self._cache_lock                = threading.Lock()
        self._current_cache_key = None
        self._fuzzy_popup       = None
        self._last_album        = ""
        self._force_scroll      = False   # force sync_loop to re-scroll on provider switch back
        self._post_scroll_snapped = True  # False while waiting to snap back after manual scroll
        self._scroll_paused_shown = False # True while "scroll paused" indicator is displayed

        self._fetch_generation  = 0       # incremented per search; stale workers bail out
        self._fetch_lock        = threading.Lock()
        self._loading_anim_id   = None    # after-id for the "Loading…" animation
        self._loading_anim_run  = False

        # Plain (unsynced) lyrics cache: (artist_lower, title_lower, album_lower) -> str
        self._plain_lyrics_cache: dict = {}
        self._plain_cache_lock          = threading.Lock()

        # Artist / album images
        self._artist_img_ref   = None
        self._album_img_ref    = None
        self._artist_full_img  = None
        self._album_full_img   = None
        self._artist_img_gen   = 0
        self._artist_img_lock  = threading.Lock()
        self._smooth_scroll_job = None
        self._hover_popup      = None
        self._hover_img_ref    = None

        self.setup_apis()
        self.build_ui()

        self.bind("<Unmap>",     self._on_unmap)
        self.bind("<Map>",       self._on_map)
        self.bind("<Configure>", self._on_configure)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Keyboard shortcuts
        self.bind("<Control-Left>",  lambda _: self.adjust_nudge(-0.25))
        self.bind("<Control-Right>", lambda _: self.adjust_nudge(0.25))
        self.bind("<Control-r>",     lambda _: self.reset_nudge())
        self.bind("<Control-f>",     lambda _: self.artist_entry.focus_set())
        self.bind("<Control-Return>",lambda _: self.manual_search())
        self.bind("<Escape>",        lambda _: self.textbox.focus_set())

        # Defer first visibility check — winfo_viewable() returns 0 before mainloop starts,
        # which would immediately set window_visible=False and block the first poll.
        self.after(2000, self._check_visibility)

        threading.Thread(target=self.poll_lastfm,     daemon=True).start()
        threading.Thread(target=self._initial_poll,   daemon=True).start()
        threading.Thread(target=self.poll_audirvana,  daemon=True).start()
        threading.Thread(target=self.sync_loop,       daemon=True).start()

    # ------------------------------------------------------------------
    # parsed_lrc — thread-safe property
    # ------------------------------------------------------------------

    @property
    def parsed_lrc(self):
        with self._lrc_lock: return list(self._parsed_lrc_safe)

    @parsed_lrc.setter
    def parsed_lrc(self, value):
        with self._lrc_lock: self._parsed_lrc_safe = value

    # ------------------------------------------------------------------
    # Visibility polling (catches occlusion, not just minimize)
    # ------------------------------------------------------------------

    def _check_visibility(self):
        """Runs on main thread every 2 s. Marks window_visible=False if the window
        is iconic (minimized), withdrawn, or not viewable (fully obscured / off-screen)."""
        try:
            state = self.wm_state()
            viewable = bool(self.winfo_viewable())
            self.window_visible = (state not in ("iconic", "withdrawn")) and viewable
        except Exception:
            pass
        self.after(2000, self._check_visibility)

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def cfg(self, key):
        return self.config.get(key, CONFIG_DEFAULTS.get(key))

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f: return json.load(f)
        return {}

    def save_config(self):
        with open(CONFIG_FILE, "w") as f: json.dump(self.config, f, indent=4)

    def setup_apis(self):
        self.user = None; self.genius = None
        try:
            if all(self.config.get(k) for k in
                   ("LASTFM_API_KEY", "LASTFM_API_SECRET", "LASTFM_USERNAME")):
                net = pylast.LastFMNetwork(api_key=self.config["LASTFM_API_KEY"],
                                           api_secret=self.config["LASTFM_API_SECRET"])
                self.user = net.get_user(self.config["LASTFM_USERNAME"])
            if self.config.get("GENIUS_ACCESS_TOKEN"):
                self.genius = lyricsgenius.Genius(
                    self.config["GENIUS_ACCESS_TOKEN"],
                    verbose=False,
                    retries=2,
                    remove_section_headers=False,
                    skip_non_songs=True,
                )
        except Exception: traceback.print_exc()

    # ------------------------------------------------------------------
    # Window events
    # ------------------------------------------------------------------

    def _on_unmap(self, event):
        if event.widget is self: self.window_visible = False

    def _on_map(self, event):
        if event.widget is self: self.window_visible = True

    def _on_configure(self, event):
        if event.widget is not self: return
        if self._geo_save_id: self.after_cancel(self._geo_save_id)
        self._geo_save_id = self.after(3000, self._save_geometry)

    def _save_geometry(self):
        self.config["WINDOW_GEOMETRY"] = self.geometry()
        self.save_config()

    def _on_close(self):
        """Clean shutdown: save geometry once and exit."""
        try:
            if self._geo_save_id:
                self.after_cancel(self._geo_save_id)
            self.config["WINDOW_GEOMETRY"] = self.geometry()
            self.save_config()
        except Exception:
            pass
        self.destroy()

    # ------------------------------------------------------------------
    # Appearance
    # ------------------------------------------------------------------

    def apply_appearance(self):
        """Apply font/colour based on current provider AND sync state.
        Genius is always unsynced-styled regardless of the sync toggle."""
        use_synced = self.sync_enabled.get() and self.current_provider == "LRCLIB"
        if use_synced:
            weight = "bold" if self.cfg("SYNCED_FONT_BOLD") else "normal"
            font   = (self.cfg("SYNCED_FONT_FAMILY"), self.cfg("SYNCED_FONT_SIZE"), weight)
            self.textbox.configure(font=font, text_color=self.cfg("SYNCED_INACTIVE_COLOR"))
        else:
            font = (self.cfg("UNSYNCED_FONT_FAMILY"), self.cfg("UNSYNCED_FONT_SIZE"))
            self.textbox.configure(font=font, text_color=self.cfg("UNSYNCED_TEXT_COLOR"))
        self.textbox.tag_config("near1", foreground=self.cfg("SYNCED_NEAR1_COLOR"))
        self.textbox.tag_config("near2", foreground=self.cfg("SYNCED_NEAR2_COLOR"))
        self.textbox.tag_config("highlight", foreground=self.cfg("SYNCED_HIGHLIGHT_COLOR"))
        weight_hl = "bold" if self.cfg("SYNCED_FONT_BOLD") else "normal"
        font_hl   = (self.cfg("SYNCED_FONT_FAMILY"), self.cfg("SYNCED_HIGHLIGHT_SIZE"), weight_hl)
        self.textbox._textbox.tag_config("highlight", font=font_hl)

    def preview_synced_font(self, font_name):
        weight = "bold" if self.cfg("SYNCED_FONT_BOLD") else "normal"
        if self.sync_enabled.get() and self.current_provider == "LRCLIB":
            self.textbox.configure(font=(font_name, self.cfg("SYNCED_FONT_SIZE"), weight))
        self.textbox._textbox.tag_config("highlight",
                                         font=(font_name, self.cfg("SYNCED_HIGHLIGHT_SIZE"), weight))

    def preview_unsynced_font(self, font_name):
        if not (self.sync_enabled.get() and self.current_provider == "LRCLIB"):
            self.textbox.configure(font=(font_name, self.cfg("UNSYNCED_FONT_SIZE")))

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def build_ui(self):
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=15, pady=(10, 5))
        ctk.CTkSwitch(top_bar, text="Auto-Sync Player", variable=self.auto_sync,
                      command=self._on_auto_sync_toggle,
                      progress_color="#444444").pack(side="left")
        ctk.CTkButton(top_bar, text="⚙", width=35, fg_color="#222222",
                      command=self.open_settings).pack(side="right")

        search_frame = ctk.CTkFrame(self, fg_color="#1e1e1e")
        search_frame.pack(fill="x", padx=15, pady=5)

        header_row = ctk.CTkFrame(search_frame, fg_color="transparent")
        header_row.pack(fill="x", padx=10, pady=10)
        header_row.grid_columnconfigure(0, weight=0)
        header_row.grid_columnconfigure(1, weight=1)
        header_row.grid_columnconfigure(2, weight=0)

        thumb_size = 72
        thumb_box_size = 84

        self._artist_box = ctk.CTkFrame(header_row, width=thumb_box_size, height=thumb_box_size,
                                        fg_color="#101010", corner_radius=10,
                                        border_width=int(self.cfg("THUMB_BORDER_WIDTH")),
                                        border_color=self.cfg("THUMB_BORDER_COLOR"))
        self._artist_box.grid(row=0, column=0, padx=(0, 10), sticky="nw")
        self._artist_box.grid_propagate(False)

        self._artist_img_label = tk.Label(
            self._artist_box,
            bg="#101010",
            bd=0,
            highlightthickness=0
        )
        self._artist_img_label.place(relx=0.5, rely=0.5, anchor="center", width=thumb_size, height=thumb_size)
        self._artist_img_label.bind("<Enter>", self._show_artist_popup)
        self._artist_img_label.bind("<Leave>", self._hide_popup)

        center_box = ctk.CTkFrame(header_row, fg_color="transparent")
        center_box.grid(row=0, column=1, sticky="ew")
        center_box.grid_columnconfigure(0, weight=1)

        self.artist_entry = ctk.CTkEntry(center_box, placeholder_text="Artist",
                                         fg_color="#121212", border_width=0)
        self.artist_entry.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        self.title_entry = ctk.CTkEntry(center_box, placeholder_text="Title",
                                        fg_color="#121212", border_width=0)
        self.title_entry.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        self.artist_entry.bind("<Return>", lambda _: self.manual_search())
        self.title_entry.bind("<Return>",  lambda _: self.manual_search())

        btn_row = ctk.CTkFrame(center_box, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew")
        btn_row.grid_columnconfigure(3, weight=1)

        ctk.CTkButton(btn_row, text="Search / Restart", width=80, fg_color="#333333",
                      command=self.manual_search).grid(row=0, column=0, padx=(0, 6), sticky="w")
        ctk.CTkButton(btn_row, text="⎘ Copy", width=70, fg_color="#2a2a2a",
                      command=self.copy_lyrics).grid(row=0, column=1, padx=(0, 6), sticky="w")
        self.sync_btn = ctk.CTkButton(btn_row, text="Disable Sync", width=80,
                                      fg_color="#552222", command=self.toggle_sync_feature)
        self.sync_btn.grid(row=0, column=2, sticky="w")

        self._album_box = ctk.CTkFrame(header_row, width=thumb_box_size, height=thumb_box_size,
                                       fg_color="#101010", corner_radius=10,
                                       border_width=int(self.cfg("THUMB_BORDER_WIDTH")),
                                       border_color=self.cfg("THUMB_BORDER_COLOR"))
        self._album_box.grid(row=0, column=2, padx=(10, 0), sticky="ne")
        self._album_box.grid_propagate(False)

        self._album_img_label = tk.Label(
            self._album_box,
            bg="#101010",
            bd=0,
            highlightthickness=0
        )
        self._album_img_label.place(relx=0.5, rely=0.5, anchor="center", width=thumb_size, height=thumb_size)
        self._album_img_label.bind("<Enter>", self._show_album_popup)
        self._album_img_label.bind("<Leave>", self._hide_popup)

        weight = "bold" if self.cfg("SYNCED_FONT_BOLD") else "normal"

        self.lyrics_frame = ctk.CTkFrame(self, fg_color="#0a0a0a", corner_radius=10)
        self.lyrics_frame.pack(expand=True, fill="both", padx=15, pady=5)

        self.textbox = ctk.CTkTextbox(
            self.lyrics_frame, font=(self.cfg("SYNCED_FONT_FAMILY"), self.cfg("SYNCED_FONT_SIZE"), weight),
            wrap="word", fg_color="#0a0a0a",
            text_color=self.cfg("SYNCED_INACTIVE_COLOR"), cursor="hand2")
        self.textbox.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.textbox.tag_config("near1", foreground=self.cfg("SYNCED_NEAR1_COLOR"))
        self.textbox.tag_config("near2", foreground=self.cfg("SYNCED_NEAR2_COLOR"))
        self.textbox.tag_config("highlight", foreground=self.cfg("SYNCED_HIGHLIGHT_COLOR"))
        self.textbox._textbox.tag_config("highlight",
                                         font=(self.cfg("SYNCED_FONT_FAMILY"),
                                               self.cfg("SYNCED_HIGHLIGHT_SIZE"), weight))
        self.textbox.tag_config("center", justify="center")
        self.textbox.configure(state="disabled")
        self.textbox.bind("<Button-1>",   self.on_lyrics_click)
        self.textbox.bind("<MouseWheel>", self.on_manual_scroll)

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", pady=15)

        status_bar = ctk.CTkFrame(bottom, fg_color="transparent")
        status_bar.pack(fill="x")
        self.sync_label = ctk.CTkLabel(status_bar, text="", text_color="#ffffff",
                                       font=("Helvetica", 12, "bold"))
        self.sync_label.pack(side="top")
        self.duration_label = ctk.CTkLabel(status_bar, text="--:--",
                                           text_color="#888888", font=("Helvetica", 11))
        self.duration_label.pack(side="top")
        self.lyrics_status_label = ctk.CTkLabel(status_bar, text="",
                                                text_color="#555555", font=("Helvetica", 10))
        self.lyrics_status_label.pack(side="top")
        self.debug_label = ctk.CTkLabel(status_bar, text="API: 0  |  Audirvāna –",
                                        text_color="#3a3a3a", font=("Helvetica", 10))
        self.debug_label.pack(side="top")
        self.update_sync_label()

        nudge_row = ctk.CTkFrame(bottom, fg_color="transparent")
        nudge_row.pack(pady=(10, 10))
        ctk.CTkButton(nudge_row, text="-0.25s", width=65, height=30, fg_color="#222222",
                      command=lambda: self.adjust_nudge(-0.25)).pack(side="left", padx=5)
        ctk.CTkButton(nudge_row, text="Reset",   width=60, height=30, fg_color="#222222",
                      command=self.reset_nudge).pack(side="left", padx=5)
        ctk.CTkButton(nudge_row, text="+0.25s", width=65, height=30, fg_color="#222222",
                      command=lambda: self.adjust_nudge(0.25)).pack(side="left", padx=5)

        provider_frame = ctk.CTkFrame(bottom, fg_color="transparent")
        provider_frame.pack()
        self._provider_btns = {}
        for col, name in enumerate(("LRCLIB", "Genius")):
            b = ctk.CTkButton(provider_frame, text=name, width=140, height=35,
                              fg_color="#333333",
                              command=lambda n=name: self.switch_provider(n))
            b.grid(row=0, column=col, padx=10)
            self._provider_btns[name] = b
        self._update_provider_ui()


    def _apply_thumb_border(self):
        for box in (getattr(self, "_artist_box", None), getattr(self, "_album_box", None)):
            if box is not None:
                try:
                    box.configure(border_width=max(0, int(self.cfg("THUMB_BORDER_WIDTH"))),
                                  border_color=self.cfg("THUMB_BORDER_COLOR"))
                except Exception:
                    pass

    def _update_provider_ui(self):
        for name, btn in self._provider_btns.items():
            if name == self.current_provider:
                btn.configure(fg_color="#555555", text_color="#ffffff")
            else:
                btn.configure(fg_color="#2a2a2a", text_color="#777777")

    # ------------------------------------------------------------------
    # UI interaction
    # ------------------------------------------------------------------

    def on_manual_scroll(self, event=None):
        self.last_manual_scroll_time = time.time()
        self._post_scroll_snapped = False

    def on_lyrics_click(self, event):
        lrc = self.parsed_lrc
        if not lrc or not self.sync_enabled.get(): return
        line_num = int(self.textbox.index(f"@{event.x},{event.y}").split(".")[0])
        lrc_idx  = round((line_num - self.cfg("LYRICS_BUFFER_LINES") - 1) / 2)
        if 0 <= lrc_idx < len(lrc):
            clicked_ts = lrc[lrc_idx][0]
            max_interp = float(self.cfg("SCREEN_POLL_INTERVAL")) + 0.2
            interp_pos = self.audirvana_pos + min(time.time() - self.audirvana_read_wall, max_interp)
            self.manual_nudge = interp_pos - self.base_offset - clicked_ts
            self.last_manual_scroll_time = 0
            self.update_sync_label()
            self.smooth_scroll_to(lrc_idx)

    def adjust_nudge(self, amount):
        self.manual_nudge += amount; self.update_sync_label()

    def reset_nudge(self):
        self.manual_nudge = 0.0; self.update_sync_label()

    def update_sync_label(self):
        state = "● SYNC" if self.sync_enabled.get() else "○ STATIC"
        total = self.base_offset + self.manual_nudge
        color = "#ffffff" if self.sync_enabled.get() else "#666666"
        nudge = f" [{self.manual_nudge:+.1f}s]" if self.manual_nudge != 0 else ""
        self.sync_label.configure(text=f"{state} {total:+.1f}s{nudge}", text_color=color)

    def update_debug_label(self):
        paused = "  PAUSED" if not self.window_visible else ""
        uia_status = "Audirvāna ✓" if self.audirvana_ok else "Audirvāna –"
        self.debug_label.configure(
            text=f"API: {self._api_call_count}  |  {uia_status}{paused}")

    def _update_scroll_indicator(self, paused):
        """Show/hide the manual-scroll pause indicator on the sync label."""
        if paused:
            self.sync_label.configure(text_color="#886622")
        else:
            color = "#ffffff" if self.sync_enabled.get() else "#666666"
            self.sync_label.configure(text_color=color)

    # ------------------------------------------------------------------
    # Loading animation
    # ------------------------------------------------------------------

    def _start_loading_anim(self):
        self._stop_loading_anim()
        self._loading_dot_count = 0
        self._loading_anim_run = True
        self._tick_loading()

    def _tick_loading(self):
        if not self._loading_anim_run:
            return
        self._loading_dot_count = (self._loading_dot_count + 1) % 4
        dots = "." * self._loading_dot_count
        self.lyrics_status_label.configure(text=f"searching{dots}")
        self._loading_anim_id = self.after(400, self._tick_loading)

    def _stop_loading_anim(self):
        self._loading_anim_run = False
        if self._loading_anim_id:
            self.after_cancel(self._loading_anim_id)
            self._loading_anim_id = None


    def set_lyrics_status(self, text):
        self._stop_loading_anim()
        self.lyrics_status_label.configure(text=text)

    def copy_lyrics(self):
        self.textbox.configure(state="normal")
        full = self.textbox.get("1.0", "end-1c")
        self.textbox.configure(state="disabled")
        buf  = self.cfg("LYRICS_BUFFER_LINES")
        lines = full.split("\n")
        content = "\n".join(lines[buf:-buf]).strip()
        if content:
            self.clipboard_clear(); self.clipboard_append(content)

    def toggle_sync_feature(self):
        new = not self.sync_enabled.get()
        self.sync_enabled.set(new); self.update_sync_label()
        if new:
            self.sync_btn.configure(text="Disable Sync", fg_color="#552222")
        else:
            self.sync_btn.configure(text="Enable Sync",  fg_color="#225522")
            self.textbox.tag_remove("highlight", "1.0", "end")
        self.apply_appearance()

        # When disabling sync with LRCLIB active, prefer plain unsynced lyrics
        if not new and self.current_provider == "LRCLIB":
            artist = self.artist_entry.get().strip().lower()
            title  = self.title_entry.get().strip().lower()
            plain_key = (artist, title, self._last_album.lower())
            with self._plain_cache_lock:
                plain = (self._plain_lyrics_cache.get(plain_key) or
                         self._plain_lyrics_cache.get((artist, title, "")))
            if plain:
                self.show_lyrics(plain)
                self.set_lyrics_status("LRCLIB · plain lyrics")
                return
            # No plain cached yet — fetch (worker will swap in plain at display time)
            self.fetch_lyrics_async(self.artist_entry.get().strip(),
                                    self.title_entry.get().strip())
            return

        # Re-enabling sync or non-LRCLIB provider — restore synced text from cache
        cached = self._cache_get(self._current_cache_key) if self._current_cache_key else None
        if cached:
            lrc_list, lyrics_out, status = cached
            self.parsed_lrc = lrc_list
            self.show_lyrics(lyrics_out)
            self.set_lyrics_status(status + "  (cached)")
        else:
            self.fetch_lyrics_async(self.artist_entry.get().strip(),
                                    self.title_entry.get().strip())

    def open_settings(self): SettingsWindow(self)

    def _on_auto_sync_toggle(self):
        if self.auto_sync.get():
            self._poll_reset = True
            self._song_change_event.set()  # wake poll_lastfm immediately

    def manual_search(self):
        self.manual_nudge = 0.0
        artist = self.artist_entry.get().strip()
        title  = self.title_entry.get().strip()
        if artist:
            self._clear_artist_image()
            self._clear_album_image()
            self._fetch_artist_image_async(artist, title)
        self.fetch_lyrics_async(artist, title)

    def switch_provider(self, provider):
        prev_provider = self.current_provider
        self.current_provider = provider
        self._update_provider_ui()
        self.apply_appearance()
        artist = self.artist_entry.get().strip()
        title  = self.title_entry.get().strip()

        if provider == "LRCLIB":
            self._force_scroll = True  # sync_loop will re-scroll to current line
            # Switching back to LRCLIB — restore from cache, sync resumes in-place.
            for album_guess in ("", self._last_album):
                key = (artist.lower(), title.lower(), album_guess.lower(), "LRCLIB")
                cached = self._cache_get(key)
                if cached:
                    lrc_list, lyrics_out, status = cached
                    self._current_cache_key = key
                    self.parsed_lrc = lrc_list
                    self.show_lyrics(lyrics_out)
                    self.set_lyrics_status(status + "  (cached)")
                    return
            self.show_lyrics("Loading…")
            self.fetch_lyrics_async(artist, title)

        else:
            # Switching to Genius (or any non-LRCLIB provider).
            # Keep parsed_lrc intact so sync_loop can resume if user comes back.
            for album_guess in ("", self._last_album):
                key = (artist.lower(), title.lower(), album_guess.lower(), provider)
                cached = self._cache_get(key)
                if cached:
                    lrc_list, lyrics_out, status = cached
                    self._current_cache_key = key
                    # Don't overwrite parsed_lrc — LRCLIB sync keeps running silently
                    self.show_lyrics(lyrics_out)
                    self.set_lyrics_status(status + "  (cached)")
                    return
            self.show_lyrics("Loading…")
            self.fetch_lyrics_async(artist, title)

    # ------------------------------------------------------------------
    # Fuzzy popup
    # ------------------------------------------------------------------

    def _close_fuzzy_popup(self):
        if self._fuzzy_popup and self._fuzzy_popup.winfo_exists():
            self._fuzzy_popup.destroy()
        self._fuzzy_popup = None

    def _show_fuzzy_popup(self, matched_artist, matched_title,
                          lrc_list, lyrics_out, status, cache_key):
        self._close_fuzzy_popup()

        def on_yes():
            self._fuzzy_popup = None
            self.parsed_lrc = lrc_list
            self._cache_put(cache_key, lrc_list, lyrics_out, status)
            self._current_cache_key = cache_key
            self.show_lyrics(lyrics_out)
            self.set_lyrics_status(status + "  (fuzzy — accepted)")

        def on_no():
            self._fuzzy_popup = None
            self.set_lyrics_status("LRCLIB · fuzzy match skipped")

        self._fuzzy_popup = FuzzyMatchPopup(
            self, matched_artist, matched_title, on_yes, on_no)

    # ------------------------------------------------------------------
    # Lyrics cache
    # ------------------------------------------------------------------

    def _cache_put(self, key, lrc_list, lyrics_out, status):
        cache_max = self.cfg("CACHE_MAX")
        with self._cache_lock:
            if key in self._lyrics_cache:
                self._lyrics_cache.move_to_end(key)
            else:
                if len(self._lyrics_cache) >= cache_max:
                    self._lyrics_cache.popitem(last=False)
                self._lyrics_cache[key] = (lrc_list, lyrics_out, status)

    def _cache_get(self, key):
        """Return (lrc_list, lyrics_out, status) or None. Moves hit to end."""
        with self._cache_lock:
            if key in self._lyrics_cache:
                self._lyrics_cache.move_to_end(key)
                return self._lyrics_cache[key]
        return None

    # ------------------------------------------------------------------
    # Audirvāna accessibility reader
    # ------------------------------------------------------------------

    def _read_audirvana_times(self):
        """Return (pos_sec, dur_sec) from Audirvāna via uiautomation, or None.

        Audirvāna may expose 2 time elements (position, duration) or 3+ when
        album-level totals are visible.  We collect all of them, sort ascending,
        and take the two smallest.  The album time is always ≥ track duration,
        so sorting naturally filters it out.  position ≤ duration holds for the
        two smallest values in every practical scenario.
        """
        try:
            import uiautomation as auto
            time_pattern = re.compile(r"^(\d{1,2}:)?\d{2}:\d{2}$")
            win = None
            for win_name in ("Audirvāna Studio", "Audirvana - MiniPlayer"):
                w = auto.WindowControl(searchDepth=1, Name=win_name)
                if w.Exists(0, 0):
                    win = w
                    break
            if not win:
                return None
            times = []
            for control, _ in auto.WalkControl(win):
                if control.ControlType == auto.ControlType.TextControl:
                    name = control.Name.strip()
                    if time_pattern.match(name):
                        parts = name.split(":")
                        secs = sum(int(p) * (60 ** (len(parts) - 1 - i))
                                   for i, p in enumerate(parts))
                        times.append(float(secs))
            if len(times) >= 2:
                times.sort()
                return times[0], times[1]  # position (smallest), duration (second smallest)
        except Exception:
            pass
        return None

    def poll_audirvana(self):
        """Daemon thread: continuously read playback position from Audirvāna UI.
        Detects song changes via duration shifts or large position resets and
        signals poll_lastfm to fetch metadata immediately."""
        last_change_wall = time.time()
        while True:
            interval = float(self.cfg("SCREEN_POLL_INTERVAL"))
            if not self.window_visible:
                # Lyrics app hidden — skip expensive UIA walk, keep state intact
                time.sleep(interval)
                continue
            result = self._read_audirvana_times()
            now = time.time()
            if result:
                pos, dur = result

                if pos != self._audir_prev_raw:
                    # Position moved — genuine playback
                    prev_pos = self._audir_prev_raw
                    prev_dur = self._audir_prev_dur
                    self._audir_prev_raw    = pos
                    self.audirvana_pos      = pos
                    self.audirvana_read_wall = now
                    self.audirvana_duration = dur
                    self._audir_prev_dur   = dur
                    last_change_wall        = now
                    if not self.audirvana_ok:
                        self.audirvana_ok = True
                        self.after(0, self.update_debug_label)
                        # Playback resumed — track may have changed while
                        # paused/stopped, so always re-check metadata.
                        self._song_change_event.set()

                    # ── Song-change detection (during continuous playback) ──
                    if prev_dur >= 0 and now >= self._skip_debounce_until:
                        duration_changed = (dur != prev_dur)
                        # Position jumped backward by >30s with same duration
                        # (covers repeat-one and consecutive same-length tracks)
                        pos_reset = (prev_pos >= 0
                                     and (prev_pos - pos) > 30
                                     and not duration_changed)
                        if duration_changed or pos_reset:
                            self._skip_debounce_until = now + 1.0  # 1s debounce
                            self._song_change_event.set()

                else:
                    # Same value — check if stopped (no change for >2s)
                    if now - last_change_wall > 2.0:
                        if self.audirvana_ok:
                            self.audirvana_ok = False
                            self.after(0, self.update_debug_label)
            else:
                last_change_wall = now  # reset so we don't false-trigger on resume
                self._audir_prev_raw = -1
                self._audir_prev_dur = -1.0
                if self.audirvana_ok:
                    self.audirvana_ok = False
                    self.after(0, self.update_debug_label)
            time.sleep(interval)

    # ------------------------------------------------------------------
    # Last.fm polling
    # ------------------------------------------------------------------

    def _initial_poll(self):
        """Fire immediate Last.fm checks at startup, retrying until a track is found."""
        time.sleep(0.5)
        if self.user:
            for attempt in range(5):
                try:
                    track = self.user.get_now_playing()
                    if track:
                        album_name = ""
                        try:
                            album = track.get_album()
                            if album: album_name = album.title
                        except Exception: pass
                        self._initial_song_id = f"{track.artist.name} - {track.title}"
                        self._initial_poll_done = True
                        self.after(0, self.update_ui_new_song,
                                   track.artist.name, track.title, album_name)
                        return
                except Exception: pass
                if attempt < 4:
                    time.sleep(3)  # wait 3s between retries
        self._initial_poll_done = True

    def poll_lastfm(self):
        """Daemon thread: fetches Last.fm metadata on song-change events
        signalled by poll_audirvana.  Does nothing when Audirvāna is not running."""
        # Wait for initial poll to finish so we don't double-fetch the first song
        while not self._initial_poll_done:
            time.sleep(0.2)
        last_id = self._initial_song_id
        while True:
            # If a reset was requested (e.g. auto_sync re-enabled), clear last_id
            if self._poll_reset:
                last_id = ""
                self._poll_reset = False

            # Wait for song-change event from UIA; re-check every 2s
            # so we notice if auto_sync is toggled or poll_reset is set.
            triggered = self._song_change_event.wait(timeout=2.0)
            if triggered:
                self._song_change_event.clear()
            else:
                continue  # timeout — no song change, loop back

            if not (self.window_visible and self.auto_sync.get() and self.user):
                continue

            try:
                with self._api_lock:
                    self._api_call_count += 1
                self.after(0, self.update_debug_label)
                track = self.user.get_now_playing()
                if track:
                    song_id = f"{track.artist.name} - {track.title}"
                    if song_id != last_id:
                        last_id = song_id
                        album_name = ""
                        try:
                            album = track.get_album()
                            if album: album_name = album.title
                        except Exception: pass
                        self.after(0, self.update_ui_new_song,
                                   track.artist.name, track.title, album_name)
            except Exception: traceback.print_exc()

    # ------------------------------------------------------------------
    # Song change
    # ------------------------------------------------------------------

    def update_ui_new_song(self, artist, title, album=""):
        display_title = clean_title_display(title)
        self.artist_entry.delete(0, "end"); self.artist_entry.insert(0, artist)
        self.title_entry.delete(0, "end");  self.title_entry.insert(0, display_title)

        self.base_offset  = float(self.cfg("DEFAULT_OFFSET"))
        self.manual_nudge = 0.0

        self.update_sync_label()
        self.title(f"{artist}  —  {display_title}")
        self._last_album = album
        self._close_fuzzy_popup()
        self._clear_artist_image()
        self._clear_album_image()
        self._fetch_artist_image_async(artist, display_title)
        self.fetch_lyrics_async(artist, display_title, album)

    # ------------------------------------------------------------------
    # Artist image (Genius)
    # ------------------------------------------------------------------

    def _fetch_artist_image_async(self, artist, title=""):
        if not _PIL_OK or not self.cfg("GENIUS_ACCESS_TOKEN"):
            self._clear_artist_image()
            self._clear_album_image()
            return

        self.after(0, self._clear_artist_image)
        self.after(0, self._clear_album_image)

        with self._artist_img_lock:
            self._artist_img_gen += 1
            gen = self._artist_img_gen
        threading.Thread(target=self._fetch_artist_image_worker,
                         args=(artist, title, gen), daemon=True).start()

    def _fetch_artist_image_worker(self, artist, title, gen):
        try:
            if not _PIL_OK:
                return
            token = self.cfg("GENIUS_ACCESS_TOKEN")
            if not token:
                return
            headers = {"Authorization": f"Bearer {token}"}

            queries = []
            if title:
                queries.append(f"{artist} {title}")
            queries.append(artist)

            img_url = None
            album_img_url = None

            for query in queries:
                r = requests.get("https://api.genius.com/search",
                                 params={"q": query}, headers=headers, timeout=6)
                if r.status_code != 200:
                    continue
                with self._artist_img_lock:
                    if gen != self._artist_img_gen:
                        return

                hits = r.json().get("response", {}).get("hits", [])
                for hit in hits:
                    result = hit.get("result", {})
                    a = result.get("primary_artist", {})
                    url = a.get("image_url", "")
                    a_name = a.get("name", "")
                    song_art = result.get("song_art_image_url", "") or result.get("header_image_url", "")

                    if url and "default_avatar" not in url:
                        a_name_n = normalize_for_search(a_name).lower()
                        q_name = normalize_for_search(artist).lower()
                        sim = artist_similarity(q_name, a_name_n)
                        if sim >= 0.35:
                            img_url = url
                            album_img_url = song_art
                            break
                if img_url:
                    break

            if not img_url:
                return

            with self._artist_img_lock:
                if gen != self._artist_img_gen:
                    return

            ir = requests.get(img_url, timeout=8)
            if ir.status_code != 200:
                return

            with self._artist_img_lock:
                if gen != self._artist_img_gen:
                    return

            size = 72
            raw_full = Image.open(BytesIO(ir.content)).convert("RGBA")
            artist_full = raw_full.copy()
            artist_thumb = self._center_crop_square(raw_full).resize((size, size), Image.LANCZOS)

            self.after(0, self._display_artist_image, artist_thumb, artist_full, gen)

            if album_img_url:
                try:
                    ar = requests.get(album_img_url, timeout=8)
                    if ar.status_code == 200:
                        alb_full = Image.open(BytesIO(ar.content)).convert("RGBA")
                        alb = self._center_crop_square(alb_full).resize((72, 72), Image.LANCZOS)
                        self.after(0, self._display_album_image, alb, alb_full, gen)
                except Exception:
                    pass
        except Exception:
            pass

    def _center_crop_square(self, img):
        width, height = img.size
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        return img.crop((left, top, left + side, top + side))

    def _display_artist_image(self, img, full_img, gen):
        with self._artist_img_lock:
            if gen != self._artist_img_gen:
                return
        try:
            tk_img = ImageTk.PhotoImage(img)
            self._artist_img_ref = tk_img
            self._artist_full_img = full_img
            self._artist_img_label.configure(image=tk_img)
        except Exception:
            pass

    def _clear_artist_image(self):
        try:
            self._artist_img_label.configure(image="")
        except Exception:
            pass
        self._artist_img_ref = None
        self._artist_full_img = None
        self._hide_popup()

    def _display_album_image(self, img, full_img, gen):
        with self._artist_img_lock:
            if gen != self._artist_img_gen:
                return
        try:
            tk_img = ImageTk.PhotoImage(img)
            self._album_img_ref = tk_img
            self._album_full_img = full_img
            self._album_img_label.configure(image=tk_img)
        except Exception:
            pass

    def _clear_album_image(self):
        try:
            self._album_img_label.configure(image="")
        except Exception:
            pass
        self._album_img_ref = None
        self._album_full_img = None
        self._hide_popup()

    def _show_popup(self, pil_img, event):
        if pil_img is None:
            return

        self._hide_popup()

        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)

        preview = pil_img.copy()
        preview.thumbnail((500, 500), Image.LANCZOS)

        x = event.x_root + 12
        y = event.y_root + 12
        popup.geometry(f"+{x}+{y}")

        tk_img = ImageTk.PhotoImage(preview)
        self._hover_img_ref = tk_img

        lbl = tk.Label(popup, image=tk_img, bg="#000000", bd=0, highlightthickness=1,
                       highlightbackground="#444444")
        lbl.pack()
        lbl.bind("<Leave>", self._hide_popup)

        self._hover_popup = popup

    def _show_artist_popup(self, event):
        self._show_popup(self._artist_full_img, event)

    def _show_album_popup(self, event):
        self._show_popup(self._album_full_img, event)

    def _hide_popup(self, event=None):
        try:
            if self._hover_popup is not None and self._hover_popup.winfo_exists():
                self._hover_popup.destroy()
        except Exception:
            pass
        self._hover_popup = None
        self._hover_img_ref = None

    # ------------------------------------------------------------------
    # Lyrics fetch
    # ------------------------------------------------------------------

    def fetch_lyrics_async(self, artist, title, album=""):
        with self._fetch_lock:
            self._fetch_generation += 1
            gen = self._fetch_generation
        self.after(0, self._start_loading_anim)
        threading.Thread(target=self._fetch_worker,
                         args=(artist, title, album, gen), daemon=True).start()

    def _is_stale(self, gen):
        """True if a newer fetch has been launched since *gen*."""
        with self._fetch_lock:
            return gen != self._fetch_generation

    def _fetch_worker(self, artist, title, album, gen):
        search_artist = normalize_for_search(artist)
        search_title  = clean_title_for_search(title)
        cache_key     = (artist.lower(), title.lower(), album.lower(), self.current_provider)

        cached = self._cache_get(cache_key)
        if cached:
            if self._is_stale(gen): return
            lrc_list, lyrics_out, status = cached
            self.parsed_lrc = lrc_list
            self._current_cache_key = cache_key
            self.after(0, self.show_lyrics, lyrics_out)
            self.after(0, self.set_lyrics_status, status + "  (cached)")
            return

        if self.current_provider == "LRCLIB":
            result = self._fetch_lrclib(
                search_artist, search_title,
                normalize_for_search(album) if album else "")
            if self._is_stale(gen): return
            if result["needs_confirm"]:
                self.parsed_lrc = []
                self.after(0, self.show_lyrics, "No lyrics found.")
                self.after(0, self.set_lyrics_status, "LRCLIB · fuzzy match — see popup")
                self.after(0, self._show_fuzzy_popup,
                           result["matched_artist"], result["matched_title"],
                           result["lrc_list"], result["lyrics_out"], result["status"],
                           cache_key)
                return
            lrc_list, lyrics_out, status = result["lrc_list"], result["lyrics_out"], result["status"]

            # Cache plain lyrics separately so we can show them when sync is off
            plain_key = (artist.lower(), title.lower(), album.lower())
            if result.get("plain_lyrics"):
                with self._plain_cache_lock:
                    self._plain_lyrics_cache[plain_key] = result["plain_lyrics"]

            # Auto-fallback to Genius if LRCLIB returned nothing
            if (lyrics_out == "No lyrics found."
                    and self.cfg("AUTO_GENIUS_FALLBACK")
                    and self.genius):
                if self._is_stale(gen): return
                g_lrc, g_lyrics, g_status = self._fetch_genius(search_artist, search_title)
                if self._is_stale(gen): return
                if g_lyrics and g_lyrics != "No lyrics found." and g_lyrics != "Genius mismatch.":
                    # Cache Genius result under the Genius provider key
                    g_key = (artist.lower(), title.lower(), album.lower(), "Genius")
                    self._cache_put(g_key, g_lrc, g_lyrics, g_status)
                    lrc_list = g_lrc
                    lyrics_out = g_lyrics
                    status = g_status + "  (auto-fallback)"

        elif self.current_provider == "Genius" and self.genius:
            lrc_list, lyrics_out, status = self._fetch_genius(search_artist, search_title)
            if self._is_stale(gen): return
        else:
            lrc_list, lyrics_out, status = [], "No lyrics found.", "Genius — no token"

        if self._is_stale(gen): return

        # Only update parsed_lrc for LRCLIB results — Genius has no LRC data
        # and we want to keep the LRCLIB sync state alive in the background.
        if self.current_provider == "LRCLIB":
            self.parsed_lrc = lrc_list
        self._cache_put(cache_key, lrc_list, lyrics_out, status)
        self._current_cache_key = cache_key

        # When sync is off and we have plain lyrics, show those instead
        display_text = lyrics_out
        if (not self.sync_enabled.get()
                and self.current_provider == "LRCLIB"
                and "auto-fallback" not in status):
            plain_key = (artist.lower(), title.lower(), album.lower())
            with self._plain_cache_lock:
                plain = self._plain_lyrics_cache.get(plain_key)
            if plain:
                display_text = plain

        self.after(0, self.show_lyrics, display_text)
        self.after(0, self.set_lyrics_status, status)
        if self.current_provider == "Genius" or "auto-fallback" in status:
            self.after(0, self.apply_appearance)

    def _fetch_lrclib(self, artist, title, album):
        base = {"needs_confirm": False, "lrc_list": [], "lyrics_out": "No lyrics found.",
                "plain_lyrics": "", "status": "LRCLIB"}
        fuzzy_thr = float(self.cfg("FUZZY_THRESHOLD"))
        try:
            params = {"artist_name": artist, "track_name": title}
            if album: params["album_name"] = album
            r = requests.get("https://lrclib.net/api/get", params=params, timeout=5)
            if r.status_code == 200:
                data = r.json()
                lrc  = data.get("syncedLyrics")
                plain = data.get("plainLyrics", "") or ""
                if lrc:
                    lrc_list = self._parse_lrc(lrc)
                    return {**base, "lrc_list": lrc_list,
                            "lyrics_out": "\n\n".join(l[1] for l in lrc_list),
                            "plain_lyrics": plain,
                            "status": f"LRCLIB · synced · {len(lrc_list)} lines"}
                if plain:
                    return {**base, "lyrics_out": plain, "plain_lyrics": plain,
                            "status": "LRCLIB · plain lyrics"}

            r2 = requests.get("https://lrclib.net/api/search",
                              params={"artist_name": artist, "track_name": title}, timeout=5)
            if r2.status_code == 200:
                results = r2.json()
                for res in results:
                    lrc = res.get("syncedLyrics")
                    if not lrc: continue
                    result_artist = res.get("artistName", "")
                    sim = artist_similarity(artist, result_artist)
                    lrc_list = self._parse_lrc(lrc)
                    plain    = res.get("plainLyrics", "") or ""
                    status   = f"LRCLIB · synced (fuzzy) · {len(lrc_list)} lines"
                    if sim >= fuzzy_thr:
                        return {**base, "lrc_list": lrc_list,
                                "lyrics_out": "\n\n".join(l[1] for l in lrc_list),
                                "plain_lyrics": plain,
                                "status": status}
                    else:
                        return {**base, "needs_confirm": True,
                                "matched_artist": result_artist,
                                "matched_title":  res.get("trackName", title),
                                "lrc_list": lrc_list,
                                "lyrics_out": "\n\n".join(l[1] for l in lrc_list),
                                "plain_lyrics": plain,
                                "status": status}
                for res in results:
                    plain = res.get("plainLyrics")
                    if not plain: continue
                    result_artist = res.get("artistName", "")
                    sim = artist_similarity(artist, result_artist)
                    if sim >= fuzzy_thr:
                        return {**base, "lyrics_out": plain, "plain_lyrics": plain,
                                "status": "LRCLIB · plain (fuzzy)"}
                    else:
                        return {**base, "needs_confirm": True,
                                "matched_artist": result_artist,
                                "matched_title":  res.get("trackName", title),
                                "lrc_list": [], "lyrics_out": plain,
                                "plain_lyrics": plain,
                                "status": "LRCLIB · plain (fuzzy)"}

            return {**base, "status": "LRCLIB · not found"}
        except Exception:
            traceback.print_exc()
            return {**base, "status": "LRCLIB · error"}

    def _fetch_genius(self, artist, title):
        lrc_list = []; lyrics_out = "No lyrics found."; status = "Genius"
        try:
            song = self.genius.search_song(title, artist)
            if song:
                def norm(s): return re.sub(r'[^a-z0-9 ]', '',
                                           normalize_for_search(s).lower())
                a_sim = artist_similarity(artist, song.artist)
                t_sim = artist_similarity(title,  song.title)
                if a_sim >= 0.4 and t_sim >= 0.4:
                    lyrics_out = clean_genius_lyrics(song.lyrics)
                    status     = "Genius · plain lyrics"
                else:
                    lyrics_out = "Genius mismatch."
                    status     = f"Genius · mismatch ({song.artist} / {song.title})"
            else:
                status = "Genius · not found"
        except Exception:
            traceback.print_exc(); status = "Genius · error"
        return lrc_list, lyrics_out, status

    def show_lyrics(self, text):
        buf = self.cfg("LYRICS_BUFFER_LINES")
        self.textbox.configure(state="normal")
        self.textbox.delete("0.0", "end")
        self.textbox.insert("0.0", "\n" * buf + text + "\n" * buf)
        self.textbox.tag_add("center", "1.0", "end")
        self.textbox.configure(state="disabled")
        if not self.sync_enabled.get():
            self.textbox.yview_moveto(0)

    # ------------------------------------------------------------------
    # Sync loop — no duration countdown, only lyric highlighting
    # ------------------------------------------------------------------

    def sync_loop(self):
        last_idx = -1
        while True:
            # ── Throttle: sleep longer when there's nothing useful to do ──
            lrc = self.parsed_lrc
            actively_syncing = (
                self.window_visible
                and lrc
                and self.sync_enabled.get()
                and self.current_provider == "LRCLIB"
                and self.audirvana_ok
            )
            if not self.window_visible:
                time.sleep(0.5)
                continue

            # Interpolate sub-second position between whole-second UIA ticks.
            # Cap at poll_interval + 0.2s so a gap in reads never causes runaway.
            max_interp = float(self.cfg("SCREEN_POLL_INTERVAL")) + 0.2
            interp = min(time.time() - self.audirvana_read_wall, max_interp)
            pos     = self.audirvana_pos + interp
            elapsed = pos - (self.base_offset + self.manual_nudge)

            # Duration label — only show live position when Audirvāna is being read
            if not self.audirvana_ok:
                if self._last_duration_displayed != -2:
                    self._last_duration_displayed = -2
                    self.after(0, lambda: self.duration_label.configure(text="--:-- / --:--"))
            else:
                cur_sec = int(pos)
                if cur_sec != self._last_duration_displayed:
                    self._last_duration_displayed = cur_sec
                    dur = self.audirvana_duration
                    if dur > 0:
                        pm, ps = divmod(int(pos), 60)
                        tm, ts = divmod(int(dur), 60)
                        txt = f"{pm:02d}:{ps:02d} / {tm:02d}:{ts:02d}"
                    else:
                        pm, ps = divmod(max(0, int(pos)), 60)
                        txt = f"{pm:02d}:{ps:02d} / --:--"
                    self.after(0, lambda t=txt: self.duration_label.configure(text=t))

            if actively_syncing:
                current_idx = -1
                for i, (ts, _) in enumerate(lrc):
                    if elapsed >= ts: current_idx = i
                    else: break
                if current_idx != -1:
                    since_scroll = time.time() - self.last_manual_scroll_time
                    manual_paused = (self.last_manual_scroll_time > 0 and since_scroll <= 3)

                    # Show/hide the scroll-paused indicator
                    if manual_paused and not self._scroll_paused_shown:
                        self._scroll_paused_shown = True
                        self.after(0, self._update_scroll_indicator, True)
                    elif not manual_paused and self._scroll_paused_shown:
                        self._scroll_paused_shown = False
                        self.after(0, self._update_scroll_indicator, False)

                    # Re-snap after manual scroll once 3 s have elapsed,
                    # even if the lyric index hasn't changed yet.
                    if (not self._post_scroll_snapped
                            and self.last_manual_scroll_time > 0
                            and since_scroll > 3):
                        self._post_scroll_snapped = True
                        last_idx = -1          # force scroll branch below to fire

                    if current_idx != last_idx or self._force_scroll:
                        last_idx = current_idx
                        self._force_scroll = False
                        if since_scroll > 3:
                            self.after(0, self.smooth_scroll_to, current_idx)
                        else:
                            self.after(0, self.highlight_only, current_idx)

            time.sleep(0.05 if actively_syncing else 0.25)

    # ------------------------------------------------------------------
    # LRC parsing
    # ------------------------------------------------------------------

    def _parse_lrc(self, lrc_content):
        result = []
        for line in lrc_content.splitlines():
            m = re.search(r'\[(\d+):(\d+\.\d+)\](.*)', line)
            if m:
                mins, secs, text = m.groups()
                ts = int(mins) * 60 + float(secs)
                if text.strip(): result.append((ts, text.strip()))
        result.sort()
        return result

    # ------------------------------------------------------------------
    # Scroll / highlight
    # ------------------------------------------------------------------

    def _apply_lyric_proximity_tags(self, index):
        self.textbox.tag_remove("highlight", "1.0", "end")
        self.textbox.tag_remove("near1", "1.0", "end")
        self.textbox.tag_remove("near2", "1.0", "end")
        if index < 0:
            return
        buf = self.cfg("LYRICS_BUFFER_LINES")
        current_ln = buf + 1 + (index * 2)
        for offset, tag in ((0, "highlight"), (-1, "near1"), (1, "near1"), (-2, "near2"), (2, "near2")):
            ln = current_ln + (offset * 2)
            if ln >= 1:
                self.textbox.tag_add(tag, f"{ln}.0", f"{ln}.end")

    def highlight_only(self, index):
        self.textbox.configure(state="normal")
        self._apply_lyric_proximity_tags(index)
        self.textbox.configure(state="disabled")

    def smooth_scroll_to(self, index):
        self.textbox.configure(state="normal")
        self._apply_lyric_proximity_tags(index)
        self.textbox.configure(state="disabled")

        raw_tb = self.textbox._textbox
        raw_tb.update_idletasks()
        total_lines = int(raw_tb.index("end-1c").split(".")[0])
        if total_lines <= 1:
            return
        buf = self.cfg("LYRICS_BUFFER_LINES")
        ln = buf + 1 + (index * 2)
        v0, v1 = raw_tb.yview()
        viewport = v1 - v0
        line_frac = (ln - 1) / total_lines
        target = max(0.0, min(1.0 - viewport, line_frac - viewport / 2))

        steps = max(1, int(self.cfg("SCROLL_STEPS")))
        step_ms = max(1, int(self.cfg("SCROLL_STEP_MS")))

        if self._smooth_scroll_job is not None:
            try:
                self.after_cancel(self._smooth_scroll_job)
            except Exception:
                pass
            self._smooth_scroll_job = None

        def ease_out_cubic(t):
            return 1 - pow(1 - t, 3)

        positions = [v0 + (target - v0) * ease_out_cubic((i + 1) / steps) for i in range(steps)]

        def step(i=0):
            if i < len(positions):
                raw_tb.yview_moveto(positions[i])
                self._smooth_scroll_job = self.after(step_ms, step, i + 1)
            else:
                self._smooth_scroll_job = None
        step()


if __name__ == "__main__":
    LyricsApp().mainloop()
