"""
Spotify Vinyl Wallpaper for Windows
===================================
A live, spinning vinyl record with the album cover as its label, drawn over a
blurred copy of the cover. It follows whatever is playing on Spotify and slows
to a stop when you pause.

SETUP
  pip install spotipy pillow requests pygame
  Uses the same Spotify app / redirect URI as spotify_wallpaper.py
  (http://127.0.0.1:8888/callback). Paste your Client Secret below.

MODES (set MODE below)
  "window"    borderless fullscreen window. Use this to test. Esc quits.
  "wallpaper" embedded behind your desktop icons like a live wallpaper.

QUIT from anywhere:  Ctrl + Shift + Q
"""
import ctypes
import io
import os
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame
import requests
import spotipy
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps
from spotipy.oauth2 import SpotifyOAuth

# ----------------------------- CONFIG ---------------------------------------
CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID", "PASTE_CLIENT_ID_HERE")
CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET", "PASTE_CLIENT_SECRET_HERE")
REDIRECT_URI = "http://127.0.0.1:8888/callback"

MODE = "window"        # "window" or "wallpaper"
FPS = 60               # lower to 30 to use less CPU
RPM = 33.3             # record speed (33.3 is a classic LP)
DISC_SIZE = 0.76       # record diameter as a fraction of screen height
LABEL_SIZE = 0.40      # album cover diameter as a fraction of the record
SHOW_TEXT = True       # song title + artist under the record
POLL_SECONDS = 3
# -----------------------------------------------------------------------------

WORK_DIR = Path(os.getenv("APPDATA", ".")) / "SpotifyWallpaper"


# ------------------------------ image building ------------------------------
def label_diameter(D: int) -> int:
    return int(D * LABEL_SIZE) // 2 * 2  # even, so the label centres exactly


def pin_radius(D: int) -> float:
    return max(3.0, D * 0.006)


def build_record(D: int) -> Image.Image:
    """The part that never visibly changes: record, grooves, label ring,
    highlights and spindle pin (RGBA, D x D). Baked into the background."""
    S, ld = D * 2, label_diameter(D)
    c, R = S / 2, S / 2 - 2
    disc = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(disc)
    d.ellipse((c - R, c - R, c + R, c + R), fill=(15, 15, 17, 255))

    r, i = R * 0.975, 0
    while r > ld * 1.08:  # fine grooves
        g = (24, 19, 22)[i % 3]
        d.ellipse((c - r, c - r, c + r, c + r), outline=(g, g, g + 2, 255), width=1)
        r -= 3.5
        i += 1
    for k in (0.58, 0.72, 0.86):  # smooth gaps between "tracks"
        rr = R * k
        d.ellipse((c - rr, c - rr, c + rr, c + rr), outline=(8, 8, 9, 255), width=5)

    ring = ld + 8  # dark rim around the label
    d.ellipse((c - ring, c - ring, c + ring, c + ring), fill=(6, 6, 7, 255))
    pr = pin_radius(D) * 2  # spindle pin
    d.ellipse((c - pr - 3, c - pr - 3, c + pr + 3, c + pr + 3), fill=(50, 50, 54, 255))
    d.ellipse((c - pr, c - pr, c + pr, c + pr), fill=(200, 200, 206, 255))
    rec = disc.resize((D, D), Image.LANCZOS)
    rec.alpha_composite(build_sheen(D))
    return rec


def build_label(cover: Image.Image, ld: int) -> Image.Image:
    return ImageOps.fit(cover.convert("RGB"), (ld, ld), Image.LANCZOS)


def build_label_mask(ld: int, D: int) -> Image.Image:
    """Smooth round mask with a hole in the middle for the spindle pin."""
    k = 4
    m = Image.new("L", (ld * k, ld * k), 0)
    md = ImageDraw.Draw(m)
    md.ellipse((0, 0, ld * k - 1, ld * k - 1), fill=255)
    c, hr = ld * k / 2, (pin_radius(D) + 3.5) * k
    md.ellipse((c - hr, c - hr, c + hr, c + hr), fill=0)
    return m.resize((ld, ld), Image.LANCZOS)


def compose_static(cover: Image.Image, w: int, h: int, cx: int, cy: int, D: int) -> Image.Image:
    bg = build_background(cover, w, h, cx, cy, D).convert("RGBA")
    bg.alpha_composite(build_record(D), (cx - D // 2, cy - D // 2))
    return bg.convert("RGB")


def build_sheen(D: int) -> Image.Image:
    """Two soft highlights that stay still while the record spins under them."""
    box = (0, 0, D - 1, D - 1)
    s = Image.new("L", (D, D), 0)
    sd = ImageDraw.Draw(s)
    sd.pieslice(box, -66, -40, fill=42)
    sd.pieslice(box, 114, 140, fill=42)
    s = s.filter(ImageFilter.GaussianBlur(D * 0.04))
    ring = Image.new("L", (D, D), 0)
    rd = ImageDraw.Draw(ring)
    rd.ellipse(box, fill=255)
    lr = D * LABEL_SIZE / 2 * 1.08
    rd.ellipse((D / 2 - lr, D / 2 - lr, D / 2 + lr, D / 2 + lr), fill=0)
    out = Image.new("RGBA", (D, D), (255, 255, 255, 0))
    out.putalpha(ImageChops.multiply(s, ring))
    return out


def build_background(cover: Image.Image, w: int, h: int, cx: int, cy: int, D: int) -> Image.Image:
    """Blurred, dimmed cover with a soft shadow where the record sits."""
    small = ImageOps.fit(cover.convert("RGB"), (max(w // 8, 1), max(h // 8, 1)), Image.LANCZOS)
    bg = small.filter(ImageFilter.GaussianBlur(6)).resize((w, h), Image.LANCZOS)
    bg = ImageEnhance.Brightness(bg).enhance(0.45)

    q = 4
    sh = Image.new("L", (w // q, h // q), 0)
    r, x, y = D / 2 / q, cx / q + 3, cy / q + 5
    ImageDraw.Draw(sh).ellipse((x - r, y - r, x + r, y + r), fill=200)
    sh = sh.filter(ImageFilter.GaussianBlur(D * 0.03 / q)).resize((w, h), Image.BILINEAR)
    return Image.composite(Image.new("RGB", (w, h), (0, 0, 0)), bg, sh)


def to_surface(img: Image.Image, alpha: bool) -> "pygame.Surface":
    mode = "RGBA" if alpha else "RGB"
    img = img.convert(mode)
    surf = pygame.image.frombuffer(img.tobytes(), img.size, mode)
    return surf.convert_alpha() if alpha else surf.convert()


def fit_text(font, text: str, max_w: int) -> str:
    if font.size(text)[0] <= max_w:
        return text
    while text and font.size(text + "\u2026")[0] > max_w:
        text = text[:-1]
    return text + "\u2026"


def bake_text(surf, title: str, artist: str, w: int, h: int) -> None:
    big = pygame.font.SysFont("segoeui,arial", int(h * 0.036), bold=True)
    small = pygame.font.SysFont("segoeui,arial", int(h * 0.024))
    y = int(h * 0.885)
    for text, font, color, dy in ((title, big, (255, 255, 255), 0),
                                  (artist, small, (200, 200, 205), int(h * 0.05))):
        t = font.render(fit_text(font, text, int(w * 0.8)), True, color)
        surf.blit(t, t.get_rect(midtop=(w // 2, y + dy)))


# ------------------------------ Spotify polling -----------------------------
class NowPlaying:
    def __init__(self):
        self.lock = threading.Lock()
        self.cover = None
        self.title = self.artist = ""
        self.playing = False
        self.version = 0


def pick_image_url(item: dict):
    images = (item.get("album") or {}).get("images") or item.get("images") \
        or (item.get("show") or {}).get("images") or []
    return images[0]["url"] if images else None


def poll_spotify(sp, state: NowPlaying, stop: threading.Event) -> None:
    last_key = None
    while not stop.is_set():
        try:
            cur = sp.current_user_playing_track()
            item = cur.get("item") if cur else None
            with state.lock:
                state.playing = bool(item and cur.get("is_playing"))
            key = (item.get("uri") or item.get("name")) if item else None
            if item and key != last_key:
                last_key = key
                url = pick_image_url(item)
                if url:
                    raw = requests.get(url, timeout=10).content
                    img = Image.open(io.BytesIO(raw)).convert("RGB")
                    artist = ", ".join(a["name"] for a in item.get("artists", [])) \
                        or (item.get("show") or {}).get("name", "")
                    with state.lock:
                        state.cover, state.title, state.artist = img, item.get("name", ""), artist
                        state.version += 1
        except Exception as e:
            print(f"Warning: {e}")
        stop.wait(POLL_SECONDS)


# ------------------------------ Windows helpers -----------------------------
def attach_to_desktop(hwnd: int, w: int, h: int) -> bool:
    """Re-parent our window behind the desktop icons (best effort)."""
    u = ctypes.windll.user32
    H, UINT = wintypes.HWND, wintypes.UINT
    u.FindWindowW.argtypes, u.FindWindowW.restype = [wintypes.LPCWSTR, wintypes.LPCWSTR], H
    u.FindWindowExW.argtypes = [H, H, wintypes.LPCWSTR, wintypes.LPCWSTR]
    u.FindWindowExW.restype = H
    u.SetParent.argtypes, u.SetParent.restype = [H, H], H
    u.SetWindowPos.argtypes = [H, H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, UINT]
    u.SendMessageTimeoutW.argtypes = [H, UINT, wintypes.WPARAM, wintypes.LPARAM,
                                      UINT, UINT, ctypes.c_void_p]

    progman = u.FindWindowW("Progman", None)
    if not progman:
        return False
    u.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0, 1000, None)  # ask Windows to spawn a WorkerW

    found = []
    Enum = ctypes.WINFUNCTYPE(wintypes.BOOL, H, wintypes.LPARAM)

    def cb(top, _):
        if u.FindWindowExW(top, None, "SHELLDLL_DefView", None):
            ww = u.FindWindowExW(None, top, "WorkerW", None)
            if ww:
                found.append(ww)
        return True

    proc = Enum(cb)
    u.EnumWindows(proc, 0)

    if found:  # classic layout
        parent, after = found[0], 1  # 1 = HWND_BOTTOM
    else:      # newer Win11 builds keep everything inside Progman
        parent = progman
        after = u.FindWindowExW(progman, None, "SHELLDLL_DefView", None) or 1
    u.SetParent(hwnd, parent)
    u.SetWindowPos(hwnd, after, 0, 0, w, h, 0x0010)  # SWP_NOACTIVATE
    return True


def quit_hotkey_down() -> bool:
    gs = ctypes.windll.user32.GetAsyncKeyState
    return all(gs(k) & 0x8000 for k in (0x11, 0x10, 0x51))  # Ctrl + Shift + Q


def get_wallpaper() -> str:
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.user32.SystemParametersInfoW(0x0073, 260, buf, 0)
    return buf.value


def set_wallpaper(path: str) -> None:
    ctypes.windll.user32.SystemParametersInfoW(0x0014, 0, path, 3)


# ----------------------------------- main -----------------------------------
def main() -> None:
    if sys.platform != "win32":
        sys.exit("This script only works on Windows.")
    if "PASTE_" in CLIENT_ID or "PASTE_" in CLIENT_SECRET:
        sys.exit("Add your Spotify Client ID and Client Secret at the top of the script.")
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    WORK_DIR.mkdir(exist_ok=True)
    auth = SpotifyOAuth(client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
                        redirect_uri=REDIRECT_URI,
                        scope="user-read-currently-playing user-read-playback-state",
                        cache_path=str(WORK_DIR / ".spotify_token"))
    auth.get_access_token(as_dict=False)  # log in now (opens a browser the first time)
    sp = spotipy.Spotify(auth_manager=auth)

    state, stop = NowPlaying(), threading.Event()
    threading.Thread(target=poll_spotify, args=(sp, state, stop), daemon=True).start()

    original = get_wallpaper()
    user32 = ctypes.windll.user32
    w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    D = int(min(w, h) * DISC_SIZE) // 2 * 2
    cx, cy = w // 2, int(h * (0.46 if SHOW_TEXT else 0.5))

    os.environ["SDL_VIDEO_WINDOW_POS"] = "0,0"
    pygame.init()
    screen = pygame.display.set_mode((w, h), pygame.NOFRAME)
    pygame.display.set_caption("Spotify Vinyl")
    if MODE == "wallpaper":
        hwnd = pygame.display.get_wm_info()["window"]
        if not attach_to_desktop(hwnd, w, h):
            print("Could not attach to the desktop; staying in window mode.")

    idle_font = pygame.font.SysFont("segoeui,arial", int(h * 0.03))
    idle = idle_font.render("Play something on Spotify", True, (150, 150, 155))
    ld = label_diameter(D)
    label_rect = pygame.Rect(cx - ld // 2, cy - ld // 2, ld, ld)
    label_mask = build_label_mask(ld, D)
    bg_surf = label_src = None
    clock, angle, speed, seen = pygame.time.Clock(), 0.0, 0.0, -1
    full, frame, last = True, 0, time.perf_counter()
    expose = getattr(pygame, "WINDOWEXPOSED", None)
    running = True

    while running:
        clock.tick(FPS)
        now = time.perf_counter()
        dt, last = min(now - last, 0.1), now  # real elapsed time -> constant-speed motion
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                running = False
            elif e.type == expose:
                full = True
        if quit_hotkey_down():
            running = False

        with state.lock:
            version, playing, cover = state.version, state.playing, state.cover
            title, artist = state.title, state.artist
        if cover is not None and version != seen:  # new song -> rebuild visuals
            seen = version
            bg_surf = to_surface(compose_static(cover, w, h, cx, cy, D), alpha=False)
            if SHOW_TEXT:
                bake_text(bg_surf, title, artist, w, h)
            label_src = build_label(cover, ld)
            full = True

        # spin up / spin down smoothly
        speed += ((RPM * 6 if playing else 0) - speed) * min(1.0, dt * 2.5)
        angle = (angle - speed * dt) % 360  # clockwise
        frame += 1
        if frame % (FPS * 5) == 0:
            full = True  # safety refresh (matters in wallpaper mode)

        if bg_surf is None:
            if full:
                screen.fill((14, 14, 16))
                screen.blit(idle, idle.get_rect(center=(w // 2, h // 2)))
                pygame.display.flip()
                full = False
            continue
        if abs(speed) < 0.02 and not full:
            continue  # record is stopped: nothing to redraw

        # Only the label moves. Rotate it with sub-pixel accuracy around its exact
        # centre and redraw just that small rectangle.
        if full:
            screen.blit(bg_surf, (0, 0))
        else:
            screen.blit(bg_surf, label_rect, label_rect)
        rot = label_src.rotate(angle, resample=Image.BICUBIC)
        rot.putalpha(label_mask)
        screen.blit(pygame.image.frombuffer(rot.tobytes(), rot.size, "RGBA"), label_rect)
        if full:
            pygame.display.flip()
            full = False
        else:
            pygame.display.update(label_rect)

    stop.set()
    pygame.quit()
    if original:
        set_wallpaper(original)  # also forces the desktop to repaint


if __name__ == "__main__":
    main()
