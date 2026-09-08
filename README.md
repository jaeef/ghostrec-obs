# Window Recorder

Record **one exact window** with OBS — never your whole screen. Pick any window from a list, work freely in other windows, and stop recording by simply closing the recorded window.

## Features

- **HWND lock** — pins the exact window by its handle. Survives title changes, never drifts to other windows.
- **Auto scene** — creates a dedicated OBS scene with only the window capture source. No manual scene setup.
- **Audio monitoring** — warns when sound goes silent for too long.
- **Loop picker** — record multiple windows back-to-back without restarting.
- **One-click launcher** — `start_recorder.bat` handles deps, OBS connection, and opens the picker.

## Requirements

- Windows 10/11
- Python 3.10+
- [OBS Studio](https://obsproject.com/) 28+ with WebSocket server enabled

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/yourname/window-recorder.git
cd window-recorder

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy config template and fill in your OBS password
copy config.example.json config.json

# 4. Run
start_recorder.bat
```

Or double-click `start_recorder.bat` — it installs missing deps and waits for OBS automatically.

## Configuration

Edit `config.json` (copied from `config.example.json`):

| Key | Default | Description |
|-----|---------|-------------|
| `obs.host` | `127.0.0.1` | OBS WebSocket host |
| `obs.port` | `4455` | OBS WebSocket port |
| `obs.password` | — | Your OBS WebSocket password |
| `output_folder` | `./recordings` | Where saved videos go |
| `audio.check` | `true` | Enable silence detection |
| `audio.silence_db` | `-55.0` | Silence threshold (dB) |
| `audio.silence_alert_seconds` | `30` | Seconds of silence before warning |

### Enable OBS WebSocket

1. Open OBS Studio
2. **Tools > WebSocket Server Settings**
3. Enable the server (port `4455`)
4. Copy the password into `config.json`

## Usage

### Interactive picker

```bash
python record.py
```

1. A numbered list of open windows appears
2. Type the **number** of the window to record (`r` to refresh, `q` to quit)
3. Type a **name** for the recording (Enter = `recording`)
4. Recording starts — locked to that exact window
5. **Close the window** to stop and save
6. The picker returns for the next recording

### List windows

```bash
python record.py --list
```

Prints all open windows (exe | title) and exits.

### Log output

```
[rec] ● STARTED  'my-class'  window='Teams Meeting'
[pin] window title changed — re-locking the SAME window: 'Teams Meeting - John'
[audio] ⚠ WARNING: no sound for 45s (last -62.3 dB). Check mic/speaker output.
[rec] ■ STOPPED  (00:45:12) — recorded window closed. Finalizing...
[file] ✔ saved -> recordings/my-class_2026-09-08_14-30-00.mkv
```

## How It Works

OBS Window Capture matches windows by `title:class:exe` with a priority rule. Its "match by exe" fallback means that when a window's title changes, OBS can re-bind to *any* window of that program. This script eliminates that failure:

1. **Pins the exact window** by its Windows handle (HWND) at recording start.
2. **Re-aims on title change** — every tick, if the window title changed, the script points OBS at the same HWND's new identity before the fallback can drift.
3. **Stops only on window close** — title changes never stop recording, and a new matching window never hijacks it.
4. **Dedicated scene** — the OBS scene holds only one source (window capture). The script verifies this before every recording and aborts if anything else is present.

## Intel iGPU Workaround

On machines with Intel integrated graphics, Window Capture may record **black** for desktop apps and standard Chrome. Fix: use a GPU-disabled browser.

1. Double-click `open_class_browser.bat` (opens Chrome with `--disable-gpu`, separate profile)
2. Open your meeting/class in that browser window
3. Run `python record.py` and pick that window

> Do not use the Teams desktop app — it captures black on Intel iGPU. Use the browser instead.

## Limitations

- **Windows only** — uses Win32 API (`win32gui`, `win32process`)
- **OBS must stay open** — can be minimized, but must not be closed
- **Minimized windows** — recording freezes if the window is minimized (keep it open behind other windows)
- **Recording quality** — controlled by OBS Settings > Output > Recording

## License

MIT
