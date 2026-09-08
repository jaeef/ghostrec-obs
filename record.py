"""
Window Recorder — manual, general-purpose, one exact window at a time.

You pick ANY window from a numbered list (a class, a meeting, a stream,
anything); the script points an OBS "Window Capture" source at that EXACT
window and starts recording. The lock is window-level (by HWND):

  - whenever the window's title changes (tab badge, meeting name, ...), the
    script re-aims the capture source at the SAME window under its new title,
    so OBS can never drift onto a different window of the same program;
  - recording runs until that exact window is closed — title changes never
    stop it and never switch what is captured;
  - anything you do in OTHER windows is never recorded.

Note: all tabs of one browser window share that one window. Switching tabs
INSIDE the recorded window changes what is recorded — do other work in other
windows.

While recording it:
  - confirms OBS says the recording output is still active,
  - watches the audio level and warns if the sound goes silent,
  - stops and files the finished video into your output folder when the
    recorded window closes,
  - then shows the window picker again for the next recording — no restart
    needed. Quit with 'q' at the picker or Ctrl+C.

Requires: OBS 28+ (WebSocket server enabled), Python packages in requirements.txt.
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import math
import os
import shutil
import sys
import threading
import time
import logging
from datetime import datetime

import obsws_python as obsws
import win32gui
import win32process

# Windows consoles default to cp1252 and crash on emoji / non-latin window titles.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def ensure_config():
    if os.path.exists(CONFIG_PATH):
        return
    example = os.path.join(os.path.dirname(CONFIG_PATH), "config.example.json")
    if os.path.exists(example):
        shutil.copy(example, CONFIG_PATH)
        print(f"[config] created {CONFIG_PATH} from example")
    else:
        default = {
            "obs": {"host": "127.0.0.1", "port": 4455, "password": ""},
            "capture_scene_name": "ClassRecScene",
            "capture_source_name": "ClassCapture",
            "output_folder": "./recordings",
            "poll_seconds": 3,
            "audio": {
                "check": True,
                "input_name": "Desktop Audio",
                "silence_db": -55.0,
                "silence_alert_seconds": 30,
                "minimize_warn_seconds": 60
            }
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
        print(f"[config] created default {CONFIG_PATH}")

def validate_config(cfg):
    required = ["obs", "output_folder"]
    for key in required:
        if key not in cfg:
            raise ValueError(f"Missing config key: {key}")
    cfg.setdefault("capture_scene_name", "ClassRecScene")
    cfg.setdefault("capture_source_name", "ClassCapture")
    cfg.setdefault("poll_seconds", 3)
    audio = cfg.setdefault("audio", {})
    audio.setdefault("check", True)
    audio.setdefault("input_name", "Desktop Audio")
    audio.setdefault("silence_db", -55.0)
    audio.setdefault("silence_alert_seconds", 30)
    audio.setdefault("minimize_warn_seconds", 60)
    obs = cfg.get("obs", {})
    obs.setdefault("host", "127.0.0.1")
    obs.setdefault("port", 4455)
    obs.setdefault("password", "")
    return cfg


# --------------------------------------------------------------------------- #
# Window enumeration (title / class / exe) via Win32                          #
# --------------------------------------------------------------------------- #

_QueryFullProcessImageName = ctypes.windll.kernel32.QueryFullProcessImageNameW
_OpenProcess = ctypes.windll.kernel32.OpenProcess
_CloseHandle = ctypes.windll.kernel32.CloseHandle
_pid_exe_cache = {}
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _exe_for_pid(pid):
    """Return basename of the executable for a pid, or '' on failure."""
    if pid in _pid_exe_cache:
        return _pid_exe_cache[pid]
    h = _OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        _pid_exe_cache[pid] = ""
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(1024)
        if _QueryFullProcessImageName(h, 0, buf, ctypes.byref(size)):
            exe = os.path.basename(buf.value)
            _pid_exe_cache[pid] = exe
            return exe
        _pid_exe_cache[pid] = ""
        return ""
    finally:
        _CloseHandle(h)


def list_windows():
    """Return list of dicts {hwnd, title, cls, exe} for visible titled windows."""
    out = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title.strip():
            return
        try:
            cls = win32gui.GetClassName(hwnd)
        except Exception:
            cls = ""
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        out.append({"hwnd": hwnd, "title": title, "cls": cls, "exe": _exe_for_pid(pid)})

    win32gui.EnumWindows(cb, None)
    return out


def get_window_info(hwnd):
    """Return {hwnd, title, cls, exe} for a live window handle, or None."""
    if not win32gui.IsWindow(hwnd):
        return None
    try:
        title = win32gui.GetWindowText(hwnd)
        cls = win32gui.GetClassName(hwnd)
    except Exception:
        return None
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    return {"hwnd": hwnd, "title": title, "cls": cls, "exe": _exe_for_pid(pid)}


# --------------------------------------------------------------------------- #
# Picker + recording name                                                      #
# --------------------------------------------------------------------------- #

def choose_window_interactively(windows):
    """Print a numbered list of windows and let the user pick one to record.

    Returns the chosen window dict, or None to quit ('q', Ctrl+C, or a closed
    stdin). 'r' re-lists the windows (they may have changed since the list
    was drawn).
    """
    while True:
        print("\n  Open windows:")
        print(f"  {'#':>4}  {'exe':<22}  title")
        for i, w in enumerate(windows, 1):
            print(f"  {i:>4}  {w['exe']:<22}  {w['title'][:58]}")
        try:
            raw = input("\n  Enter the # of the window to record "
                        "(r = refresh list, q = quit): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw == "q":
            return None
        if raw == "r":
            windows = list_windows()
            continue
        if raw.isdigit() and 1 <= int(raw) <= len(windows):
            return windows[int(raw) - 1]
        print("  Invalid choice, try again.")


def ask_recording_name():
    """Ask for a short label for this recording.

    Empty answer -> 'recording'. A timestamp is appended when the file is
    saved, so the default lands as recording_YYYY-MM-DD_HH-MM-SS.<ext>.
    Returns None if stdin closed / Ctrl+C (cancel this recording).
    """
    try:
        raw = input("  Name for this recording [recording]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    safe = "".join(c for c in raw if c.isalnum() or c in "-_ ").strip()
    return safe.replace(" ", "_") or "recording"


def _obs_escape(s):
    """Escape a component the way OBS stores window-capture strings."""
    return s.replace("#", "#22").replace(":", "#3A")


def obs_window_value(w):
    """Build the 'title:class:exe' value OBS window_capture expects."""
    return f"{_obs_escape(w['title'])}:{_obs_escape(w['cls'])}:{_obs_escape(w['exe'])}"


# --------------------------------------------------------------------------- #
# Audio level watcher (OBS high-volume InputVolumeMeters event)               #
# --------------------------------------------------------------------------- #

class AudioWatcher:
    def __init__(self, cfg):
        self.input_name = cfg["audio"]["input_name"]
        self.silence_db = float(cfg["audio"]["silence_db"])
        self._lock = threading.Lock()
        self._last_loud = time.time()
        self._last_db = -100.0
        self._client = None

    def start(self, host, port, password):
        try:
            self._client = obsws.EventClient(
                host=host, port=port, password=password,
                subs=obsws.Subs.INPUTVOLUMEMETERS,
            )
            self._client.callback.register(self.on_input_volume_meters)
            return True
        except Exception as e:
            print(f"[audio] level watch unavailable ({e}); recording continues without it")
            return False

    def on_input_volume_meters(self, data):
        peak = 0.0
        # OBS may pass inputs as attribute or dict key
        inputs = getattr(data, "inputs", None)
        if inputs is None:
            inputs = data.get("inputs", []) if isinstance(data, dict) else []
        for inp in inputs:
            if inp.get("inputName") != self.input_name:
                continue
            for ch in inp.get("inputLevelsMul", []):
                if ch:
                    peak = max(peak, ch[0])  # magnitude (linear)
        db = 20 * math.log10(peak) if peak > 0 else -100.0
        with self._lock:
            self._last_db = db
            if db > self.silence_db:
                self._last_loud = time.time()

    def silent_for(self):
        with self._lock:
            return time.time() - self._last_loud

    def last_db(self):
        with self._lock:
            return self._last_db

    def reset(self):
        with self._lock:
            self._last_loud = time.time()

    def stop(self):
        try:
            if self._client:
                self._client.disconnect()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# OBS control                                                                  #
# --------------------------------------------------------------------------- #

def ensure_scene_and_source(req, scene_name, source_name):
    """Make a DEDICATED scene that contains ONLY the window-capture source.

    Recording captures whatever scene is on Program. If we recorded your normal
    scene it would also grab any Display/Screen Capture sitting in it (= your
    whole screen). So we use our own scene with just the one window in it —
    nothing else you do on screen is recorded.
    """
    scenes = [s["sceneName"] for s in req.get_scene_list().scenes]
    if scene_name not in scenes:
        print(f"[obs] creating dedicated scene '{scene_name}'")
        req.create_scene(scene_name)

    # Remove all existing items from the scene to keep it clean
    items = req.get_scene_item_list(scene_name).scene_items
    for item in items:
        try:
            req.remove_scene_item(scene_name, item["sceneItemId"])
        except Exception:
            pass

    # OBS input names are GLOBAL. If the source exists (e.g. left in another scene
    # from a previous run) we add it to this scene instead of recreating it.
    existing = [i["inputName"] for i in req.get_input_list().inputs]
    if source_name in existing:
        print(f"[obs] adding existing source '{source_name}' to '{scene_name}'")
        req.create_scene_item(scene_name, source_name, True)
    else:
        print(f"[obs] creating source '{source_name}' in '{scene_name}'")
        req.create_input(
            scene_name, source_name, "window_capture",
            {"method": 2, "cursor": True},  # method 2 = Windows Graphics Capture (records hidden windows)
            True,
        )
    return scene_name


def fit_source_to_canvas(req, scene_name, source_name):
    """Scale/position the window source to fill the recording canvas."""
    try:
        vs = req.get_video_settings()
        cw, ch = vs.base_width, vs.base_height
        item_id = req.get_scene_item_id(scene_name, source_name).scene_item_id
        req.set_scene_item_transform(scene_name, item_id, {
            "boundsType": "OBS_BOUNDS_SCALE_INNER",
            "boundsWidth": cw, "boundsHeight": ch,
            "boundsAlignment": 0, "positionX": 0, "positionY": 0,
            "alignment": 5,  # top-left
        })
    except Exception as e:
        print(f"[obs] fit-to-canvas skipped: {e}")


def point_source_at(req, source_name, window):
    """Aim the window_capture source at ONE exact window — never anything else.

    We always pass the full 'title:class:exe' of the selected window and use
    priority 0 (match by window title). The caller re-points the source whenever
    the pinned window's title changes, so OBS can only ever bind to the window
    we selected — never to another window of the same program.
    """
    req.set_input_settings(
        source_name,
        {"window": obs_window_value(window), "priority": 0, "method": 2, "cursor": True},
        True,
    )


# --------------------------------------------------------------------------- #
# Main loop                                                                    #
# --------------------------------------------------------------------------- #

def stop_and_finalize(req, timeout=30):
    """Stop recording and WAIT until OBS finishes writing the file.

    OBS finalizes the container (e.g. the mp4 moov atom) asynchronously after
    stop_record() returns. Moving the file before that finishes yields a corrupt
    video that won't open. So we wait for the output to go inactive and for the
    file size to stop growing before returning the path.
    """
    try:
        res = req.stop_record()
    except Exception as e:
        print(f"[rec] stop_record failed: {e}")
        return "", True
    src_path = getattr(res, "output_path", "") or ""

    timed_out = True
    # 1) wait until OBS reports the recording output is no longer active
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if not req.get_record_status().output_active:
                timed_out = False
                break
        except Exception:
            break
        time.sleep(0.5)

    # 2) wait until the file exists and its size is stable across two reads
    last = -1
    stable_deadline = time.time() + timeout
    while time.time() < stable_deadline:
        if src_path and os.path.exists(src_path):
            size = os.path.getsize(src_path)
            if size == last and size > 0:
                timed_out = False
                break
            last = size
        time.sleep(0.7)
    if timed_out:
        print(f"[rec] WARNING: file finalization timed out; file may be incomplete.")
    return src_path, timed_out


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _hms(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def _file_recording(src_path, out_dir, name):
    """Move OBS's output file into out_dir as '<name>_YYYY-MM-DD_HH-MM-SS.<ext>'."""
    if not src_path or not os.path.exists(src_path):
        print(f"[file] OBS output path missing ('{src_path}'); check OBS recording folder")
        return
    # Ensure file is not locked by trying to open it read-only
    try:
        with open(src_path, 'rb') as f:
            pass
    except Exception as e:
        print(f"[file] File still locked or inaccessible: {e}. Skipping move.")
        return
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    ext = os.path.splitext(src_path)[1] or ".mkv"
    safe = "".join(c for c in name if c.isalnum() or c in "-_") or "recording"
    dst = os.path.join(out_dir, f"{safe}_{stamp}{ext}")
    # Retry move with backoff
    for attempt in range(1, 4):
        try:
            shutil.move(src_path, dst)
            print(f"[file] ✔ saved -> {dst}\n")
            return
        except Exception as e:
            if attempt < 3:
                print(f"[file] move attempt {attempt} failed: {e}, retrying in 1s...")
                time.sleep(1)
            else:
                print(f"[file] move failed after retries ({e}); left at {src_path}\n")


def print_banner(audio_cfg, ver, scene_name, source_name, out_dir):
    a = audio_cfg
    print("=" * 64)
    print("  WINDOW RECORDER — manual pick, one exact window per recording")
    print("=" * 64)
    print(f"  OBS            : {ver.obs_version}  (websocket {ver.obs_web_socket_version})")
    print(f"  record scene   : {scene_name}   (only the picked window is recorded)")
    print(f"  capture source : {source_name}")
    print(f"  save folder    : {out_dir}")
    print(f"  audio check    : {'on, input=' + a.get('input_name','?') if a.get('check') else 'off'}"
          f"   (warn below {a.get('silence_db','?')}dB for {a.get('silence_alert_seconds','?')}s)")
    print("  window lock    : exact window (HWND) — survives title changes,")
    print("                   never drifts to other windows, stops when it closes")
    print("  loop           : after each recording the picker returns; q quits")
    print("=" * 64)


def status_line(name, elapsed, audio, audio_cfg, pin_title=""):
    """One-line live overview, redrawn in place each tick."""
    db = audio.last_db() if audio else 0.0
    if audio and audio_cfg.get("check"):
        silent = audio.silent_for()
        limit = audio_cfg.get("silence_alert_seconds", 30)
        snd = f"audio {db:+5.1f}dB {'OK    ' if silent <= limit else 'SILENT'}"
    else:
        snd = "audio  --  "
    t = pin_title if len(pin_title) <= 32 else pin_title[:31] + "..."
    line = f"● REC  {name:<20} {_hms(elapsed)}  {snd}  '{t}'"
    sys.stdout.write("\r" + line.ljust(110))
    sys.stdout.flush()


def record_window(req, win, name, scene_name, source_name, out_dir,
                  poll, audio, audio_cfg):
    """Record ONE window (locked by HWND) until it is closed, then save the file.

    Returns "done" (window closed, file saved), "interrupted" (user pressed
    Ctrl+C — file still saved), or "aborted" (safety check failed, nothing
    recorded).
    """
    # (re)build the dedicated single-window scene, aim it, switch to it
    ensure_scene_and_source(req, scene_name, source_name)
    point_source_at(req, source_name, win)
    fit_source_to_canvas(req, scene_name, source_name)
    req.set_current_program_scene(scene_name)  # record ONLY this window

    # SAFETY: verify the switch actually happened AND the scene holds nothing
    # but our window source. Otherwise we'd silently record the whole screen.
    cur = req.get_scene_list().current_program_scene_name
    items = req.get_scene_item_list(scene_name).scene_items
    kinds = [i.get("inputKind", "") for i in items]
    bad = [k for k in kinds if "monitor_capture" in k or "display" in k or "game_capture" in k]
    if cur != scene_name or bad or len(items) != 1:
        print(f"\n[rec] ✋ ABORTED: scene not clean (program='{cur}', "
              f"items={[i['sourceName'] for i in items]}). "
              f"Not recording — would capture whole screen.")
        return "aborted"

    time.sleep(1)  # let the capture bind before recording
    try:
        req.start_record()
    except obsws.error.OBSSDKError:
        # Most common cause: OBS is ALREADY recording (e.g. a previous run of
        # this script was killed before it could stop). Stop that recording,
        # wait for OBS to settle, then start ours.
        try:
            already = bool(req.get_record_status().output_active)
        except Exception:
            already = False
        if not already:
            raise
        print("\n[rec] OBS was already recording — stopping that first "
              "(its file stays in OBS's recording folder)")
        try:
            old = req.stop_record()
            print(f"[rec] previous output: {getattr(old, 'output_path', '?')}")
        except Exception:
            pass
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                if not req.get_record_status().output_active:
                    break
            except Exception:
                break
            time.sleep(0.5)
        req.start_record()
    rec_started = time.time()
    pinned = get_window_info(win["hwnd"]) or dict(win)
    last_pointed = obs_window_value(pinned)
    min_warn_sec = audio_cfg.get("minimize_warn_seconds", 60)
    last_min_warn = 0.0
    last_audio_warn = 0.0
    if audio:
        audio.reset()
    print(f"\n[rec] ● STARTED  '{name}'  window='{pinned['title']}'")
    print(f"[rec]   LOCKED on this exact window (hwnd {pinned['hwnd']}). "
          "Title changes re-lock it; other windows are never recorded. "
          "Close this window to stop.\n")

    interrupted = False
    try:
        while True:
            # 1) confirm OBS still recording; restart if it dropped
            try:
                st = req.get_record_status()
                if not st.output_active:
                    print("\n[rec] output not active — restarting record")
                    req.start_record()
                    rec_started = time.time()
            except Exception as e:
                print(f"\n[rec] status check failed: {e}")

            # 2) PIN: the recorded window itself still alive?
            if not win32gui.IsWindow(pinned["hwnd"]):
                print(f"\n[rec] ■ STOPPED  ({_hms(time.time() - rec_started)}) "
                      "— recorded window closed. Finalizing, do not close OBS...")
                break

            # 2a) refresh pinned info; re-lock OBS if the window's identity changed
            fresh = get_window_info(pinned["hwnd"])
            if fresh:
                if obs_window_value(fresh) != last_pointed:
                    print(f"\n[pin] window title changed — re-locking the SAME window: "
                          f"'{fresh['title'][:60]}'")
                    point_source_at(req, source_name, fresh)
                    last_pointed = obs_window_value(fresh)
                pinned = fresh

            # 2b) minimized? WGC freezes minimized windows
            if (win32gui.IsIconic(pinned["hwnd"])
                    and time.time() - last_min_warn > min_warn_sec):
                print("\n[pin] ⚠ window is MINIMIZED — recording is frozen. "
                      "Restore it (behind other windows is fine).")
                last_min_warn = time.time()

            # 2c) audio-alive check
            if audio and audio_cfg.get("check"):
                silent = audio.silent_for()
                limit = audio_cfg.get("silence_alert_seconds", 30)
                if silent > limit and time.time() - last_audio_warn > limit:
                    print(f"\n[audio] ⚠ WARNING: no sound for {int(silent)}s "
                          f"(last {audio.last_db():.1f} dB). Check mic/speaker output.")
                    last_audio_warn = time.time()

            status_line(name, time.time() - rec_started, audio, audio_cfg,
                        pinned["title"])
            time.sleep(poll)
    except KeyboardInterrupt:
        interrupted = True
        print(f"\n[quit] Ctrl+C — stopping & saving '{name}', do not close yet...")

    src_path, timed_out = stop_and_finalize(req)
    if timed_out:
        print(f"[rec] WARNING: recording file may be incomplete. Check {src_path}")
        # Do not move incomplete file; leave it in OBS output folder.
    else:
        _file_recording(src_path, out_dir, name)
    return "interrupted" if interrupted else "done"


def prompt_password():
    print("\nOBS WebSocket password not set.")
    print("To get it: OBS -> Tools -> WebSocket Server Settings -> copy password.")
    pwd = input("Enter password (or leave empty to skip): ").strip()
    return pwd

def find_window_by_title(target):
    """Return first window dict whose title contains target (case-insensitive)."""
    target_lower = target.lower()
    for w in list_windows():
        if target_lower in w['title'].lower():
            return w
    return None

def main():
    parser = argparse.ArgumentParser(
        description="Record ONE exact window with OBS — you pick the window "
                    "from a list; other windows are never recorded.")
    parser.add_argument("--list", action="store_true",
                        help="print every open window (exe | title) and exit")
    parser.add_argument("--version", action="store_true",
                        help="print version and exit")
    parser.add_argument("--auto", action="store_true",
                        help="skip picker and record the first window matching --target")
    parser.add_argument("--target", type=str,
                        help="window title substring to match (used with --auto)")
    args = parser.parse_args()

    if args.list:
        for w in list_windows():
            print(f"{w['exe']:<26} | {w['title']}")
        return
    if args.version:
        print("GhostRec OBS v1.0.0")
        return

    ensure_config()  # Create default config if missing
    cfg = load_config()
    cfg = validate_config(cfg)
    if not cfg.get("obs", {}).get("password"):
        pwd = prompt_password()
        if pwd:
            cfg["obs"]["password"] = pwd
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            print("[config] password saved")
        else:
            print("[obs] ERROR: password required.")
            sys.exit(1)

    os.makedirs(cfg["output_folder"], exist_ok=True)

    print("[obs] connecting...")
    req = obsws.ReqClient(host=cfg["obs"]["host"], port=cfg["obs"]["port"],
                          password=cfg["obs"]["password"], timeout=5)
    ver = req.get_version()
    print(f"[obs] connected. OBS {ver.obs_version}, ws {ver.obs_web_socket_version}")

    ensure_scene_and_source(req, cfg["capture_scene_name"], cfg["capture_source_name"])

    audio = None
    if cfg["audio"].get("check"):
        audio = AudioWatcher(cfg)
        audio.start(cfg["obs"]["host"], cfg["obs"]["port"], cfg["obs"]["password"])

    print_banner(cfg["audio"], ver, cfg["capture_scene_name"],
                 cfg["capture_source_name"], cfg["output_folder"])

    if args.auto:
        if not args.target:
            print("[auto] ERROR: --target required with --auto")
            sys.exit(1)
        win = find_window_by_title(args.target)
        if not win:
            print(f"[auto] No window found with title containing '{args.target}'")
            sys.exit(1)
        print(f"[auto] Found window: {win['exe']} | {win['title']}")
        name = args.target.replace(" ", "_")[:30] or "auto_recording"
        result = record_window(req, win, name, cfg["capture_scene_name"],
                               cfg["capture_source_name"], cfg["output_folder"],
                               cfg["poll_seconds"], audio, cfg["audio"])
        if result == "interrupted":
            print("[quit] bye.")
        elif result == "aborted":
            print("[auto] Recording aborted.")
        else:
            print("[auto] Recording saved.")
        if audio:
            audio.stop()
        return

    try:
        while True:
            win = choose_window_interactively(list_windows())
            if win is None:
                print("[quit] bye.")
                break
            name = ask_recording_name()
            if name is None:
                print("[quit] no name given — back to the picker.\n")
                continue
            result = record_window(req, win, name, cfg["capture_scene_name"],
                                   cfg["capture_source_name"], cfg["output_folder"],
                                   cfg["poll_seconds"], audio, cfg["audio"])
            if result == "interrupted":
                print("[quit] bye.")
                break
            if result == "aborted":
                print("[loop] nothing recorded — picker again (q quits).\n")
            else:
                print("[loop] recording saved — picker again, pick the next "
                      "window (q quits).\n")
    except KeyboardInterrupt:
        print("\n[quit] Ctrl+C — bye.")
    finally:
        if audio:
            audio.stop()


if __name__ == "__main__":
    try:
        main()
    except obsws.error.OBSSDKError as e:
        print(f"[obs] ERROR: {e}\nIs OBS running with WebSocket enabled and the password in config.json correct?")
        sys.exit(1)