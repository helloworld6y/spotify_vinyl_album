# Spotify Vinyl Wallpaper

A live, spinning vinyl record for your Windows desktop. The album cover of the song playing on Spotify is the record's label, over a blurred copy of the cover. The record spins while music plays and slows to a stop when you pause.

> Personal, non-commercial project. Not affiliated with or endorsed by Spotify.

## Features
- Record with grooves, soft highlights, spindle pin and shadow
- Album cover as the rotating label, with song title and artist underneath
- Smooth sub-pixel rotation; only the label is redrawn each frame, so CPU use stays low
- Spins up and down smoothly on play and pause
- Two modes: fullscreen window, or embedded behind your desktop icons like a live wallpaper
- Read-only access to your Spotify playback

## Requirements
- Windows 10 or 11
- Python 3.9 or newer
- A Spotify developer app. Spotify's Development Mode rules changed in 2026 (the app owner needs Premium), so check the current rules at https://developer.spotify.com

## Setup
1. Install the dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Create an app at https://developer.spotify.com/dashboard
   - Redirect URI: `http://127.0.0.1:8888/callback` (use `127.0.0.1`, not `localhost`)
   - API used: Web API
3. Give the script your credentials **without editing the file**:
   ```
   setx SPOTIPY_CLIENT_ID "your-client-id"
   setx SPOTIPY_CLIENT_SECRET "your-client-secret"
   ```
   Then close and reopen Command Prompt.
4. Run it:
   ```
   python spotify_vinyl.py
   ```
   A browser tab opens once for you to log in.

## Modes
Set `MODE` at the top of `spotify_vinyl.py`:
- `"window"` (default): borderless fullscreen window. Good for testing. Esc quits.
- `"wallpaper"`: embeds behind the desktop icons. This relies on an undocumented Windows technique, so it is best-effort and can behave differently between Windows builds. If you get a black desktop, quit and use window mode.

**Quit from anywhere: Ctrl + Shift + Q**

## Options
| Option | Default | Meaning |
|---|---|---|
| `MODE` | `"window"` | `"window"` or `"wallpaper"` |
| `FPS` | `60` | Lower to save CPU |
| `RPM` | `33.3` | Record speed |
| `DISC_SIZE` | `0.76` | Record diameter vs. screen height |
| `LABEL_SIZE` | `0.40` | Cover diameter vs. record |
| `SHOW_TEXT` | `True` | Song title and artist |

## Run silently at login
Press `Win + R`, type `shell:startup`, and add a shortcut to:
```
pythonw "C:\path\to\spotify_vinyl.py"
```

## Security
Never commit your Client Secret. Keep it in environment variables. If it leaks, generate a new one in your Spotify app settings.
