<div align="center">

# 🎬 GhostRec OBS

**Record any window. Only that window. Never your whole screen.**

A Python-powered OBS automation tool that locks onto a single window by its Windows handle (HWND), survives title changes, and stops recording when you close the window.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![OBS Studio](https://img.shields.io/badge/OBS_Studio-28+-302E33?style=for-the-badge&logo=obs-studio&logoColor=white)](https://obsproject.com)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white)](https://microsoft.com)


<br>

**Pick a window → Record → Close to stop → Done.**

</div>

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔒 **HWND Lock** | Pins the exact window by its handle. Title changes re-lock it; other windows are never recorded. |
| 🎬 **Auto Scene** | Creates a dedicated OBS scene with only the window capture source — no manual setup needed. |
| 🔇 **Audio Monitoring** | Warns when sound goes silent for too long. |
| 🔄 **Loop Picker** | Record multiple windows back-to-back without restarting. |
| ⚡ **One-Click Launcher** | `start_recorder.bat` handles deps, OBS connection, and opens the picker. |

---

## 📋 Requirements

- **OS:** Windows 10 / 11
- **Python:** 3.10+
- **OBS Studio:** 28+ with WebSocket server enabled

---

## 🚀 Quick Start

### Option 1: One-Click (Recommended)

1. **Clone** the repo
2. **Copy** `config.example.json` → `config.json` and fill in your OBS password
3. **Double-click** `start_recorder.bat`

That's it. The launcher handles everything.

### Option 2: Manual

```bash
# Clone
git clone https://github.com/jaeef/ghostrec-obs.git
cd ghostrec-obs

# Install dependencies
pip install -r requirements.txt

# Setup config
copy config.example.json config.json
# Edit config.json → fill in obs.password

# Run
python record.py
```

---

## ⚙️ Configuration

Copy `config.example.json` to `config.json` and edit:

```json
{
  "obs": {
    "host": "127.0.0.1",
    "port": 4455,
    "password": "YOUR_OBS_WEBSOCKET_PASSWORD"
  },
  "output_folder": "./recordings",
  "audio": {
    "check": true,
    "input_name": "Desktop Audio",
    "silence_db": -55.0,
    "silence_alert_seconds": 30
  }
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `obs.host` | `127.0.0.1` | OBS WebSocket host |
| `obs.port` | `4455` | OBS WebSocket port |
| `obs.password` | — | Your OBS WebSocket password |
| `output_folder` | `./recordings` | Where saved videos go |
| `audio.check` | `true` | Enable silence detection |
| `audio.silence_db` | `-55.0` | Silence threshold (dB) |
| `audio.silence_alert_seconds` | `30` | Seconds of silence before warning |

### 🔌 Enable OBS WebSocket

1. Open **OBS Studio**
2. Go to **Tools → WebSocket Server Settings**
3. Enable the server (port `4455`)
4. Copy the password into `config.json`

---

## 🎯 Usage

### Start Recording

```bash
python record.py
```

1. A numbered list of all open windows appears
2. Type the **number** of the window to record (`r` = refresh, `q` = quit)
3. Type a **name** for the recording (Enter = `recording`)
4. Recording starts — locked to that exact window
5. **Close the window** to stop and save
6. The picker returns for the next recording

### List Windows

```bash
python record.py --list
```

### 📟 Log Output

```
[rec] ● STARTED  'my-class'  window='Teams Meeting'
[pin] window title changed — re-locking the SAME window: 'Teams Meeting - John'
[audio] ⚠ WARNING: no sound for 45s (last -62.3 dB). Check mic/speaker output.
[rec] ■ STOPPED  (00:45:12) — recorded window closed. Finalizing...
[file] ✔ saved -> recordings/my-class_2026-09-08_14-30-00.mkv
```

---

## 🔧 How It Works

OBS Window Capture matches windows by `title:class:exe` with a priority rule. Its "match by exe" fallback can drift to other windows when titles change. GhostRec eliminates that:

```
┌─────────────────────────────────────────────────────────┐
│  1. PIN by HWND        →  Exact window locked           │
│  2. RE-AIM on title    →  Same window, new title        │
│  3. STOP on close      →  Never on title change         │
│  4. DEDICATED scene    →  Only your window is captured  │
└─────────────────────────────────────────────────────────┘
```

---

## ⚠️ Intel iGPU Workaround

On machines with Intel integrated graphics, Window Capture may record **black** for desktop apps and standard Chrome.

**Fix:** Use a GPU-disabled browser.

1. Double-click `open_class_browser.bat`
2. Open your meeting/class in that browser window
3. Run `python record.py` and pick that window

> 🚫 Do not use the Teams desktop app — it captures black on Intel iGPU. Use the browser.

---

## 📝 Limitations

| Limitation | Notes |
|------------|-------|
| 🪟 Windows only | Uses Win32 API (`win32gui`, `win32process`) |
| 🔴 OBS must stay open | Can be minimized, but not closed |
| ❄️ Minimized windows | Recording freezes — keep window open behind others |
| 🎥 Recording quality | Controlled by OBS Settings → Output → Recording |

---

## 📁 Project Structure

```
ghostrec-obs/
├── record.py              # Main script
├── config.example.json    # Config template
├── requirements.txt       # Python dependencies
├── start_recorder.bat     # One-click launcher
├── open_class_browser.bat # GPU-disabled Chrome helper
├── .gitignore
└── README.md
```

---

## 🤝 Contributing

Contributions welcome! Feel free to open issues or submit PRs.

---



<div align="center">

**Made with ❤️ for content creators who want clean recordings.**

</div>
