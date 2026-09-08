import os
import json
import sys
import subprocess
import time
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"
REQUIREMENTS = Path(__file__).parent / "requirements.txt"

def install_deps():
    print("[setup] Checking dependencies...")
    try:
        import obsws_python, win32gui
        print("[OK] Dependencies already installed.")
        return
    except ImportError:
        print("[setup] Installing required packages...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)])
        print("[OK] Dependencies installed.")

def is_obs_running():
    try:
        output = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq obs64.exe"],
            text=True,
            stderr=subprocess.DEVNULL
        )
        return "obs64.exe" in output
    except:
        return False

def is_port_listening(port):
    try:
        output = subprocess.check_output(
            ["netstat", "-ano", "|", "findstr", f":{port}"],
            shell=True,
            text=True,
            stderr=subprocess.DEVNULL
        )
        return "LISTENING" in output
    except:
        return False

def wait_for_port(port, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        if is_port_listening(port):
            return True
        time.sleep(1)
    return False

def start_obs():
    paths = [
        r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
        r"C:\Program Files (x86)\obs-studio\bin\64bit\obs64.exe"
    ]
    for p in paths:
        if os.path.exists(p):
            print(f"[setup] Starting OBS from {p}...")
            subprocess.Popen([p, "--startminimized", "--locale", "en-US"], cwd=os.path.dirname(p), shell=False)
            return True
    return False

def ensure_obs_running():
    # Read port from config if exists, else default 4455
    port = 4455
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            port = cfg.get("obs", {}).get("port", 4455)
        except Exception:
            pass
    if is_obs_running() and is_port_listening(port):
        return True
    if is_obs_running() and not is_port_listening(port):
        print(f"\n[setup] OBS running but WebSocket port {port} not listening.")
        print("  Enable WebSocket server in OBS: Tools -> WebSocket Server Settings")
        print("  Then press Enter to continue...")
        input()
        if is_port_listening(port):
            return True
        else:
            print(f"[setup] Port {port} still not listening. Check OBS settings.")
            return False
    print("\n[setup] OBS is not running.")
    while True:
        print("  Options:")
        print("    [1] Start OBS automatically (if installed in default location)")
        print("    [2] I will start OBS manually (then press Enter to continue)")
        print("    [q] Quit setup")
        choice = input("Choose [1/2/q]: ").strip().lower()
        if choice == "1":
            if start_obs():
                print(f"[setup] OBS started. Waiting for WebSocket port {port}...")
                if wait_for_port(port, timeout=30):
                    print("[OK] WebSocket port ready.")
                    return True
                else:
                    print(f"[setup] WebSocket port {port} not ready after 30s. Check OBS WebSocket settings.")
                    return False
            else:
                print("[setup] Could not find OBS executable. Start it manually.")
                continue
        elif choice == "2":
            print("Please open OBS Studio manually and ensure WebSocket is enabled.")
            input("Press Enter after OBS is running and WebSocket enabled...")
            if is_obs_running() and is_port_listening(port):
                return True
            else:
                print(f"[setup] OBS or WebSocket (port {port}) not detected. Try again.")
                continue
        elif choice == "q":
            print("[setup] Setup cancelled.")
            sys.exit(0)
        else:
            print("Invalid choice.")

def get_password():
    print("\nTo get OBS WebSocket password:")
    print("  1. Open OBS Studio.")
    print("  2. Go to Tools -> WebSocket Server Settings.")
    print("  3. Enable the server (port 4455 by default).")
    print("  4. Copy the password from the 'Server Password' field.")
    print("     (If password is empty, just press Enter below.)")
    pwd = input("\nEnter OBS WebSocket password: ").strip()
    return pwd

def create_config(password):
    config = {
        "obs": {"host": "127.0.0.1", "port": 4455, "password": password},
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
        json.dump(config, f, indent=2)
    print(f"[setup] Config saved to {CONFIG_PATH}")

def test_connection(password, port=4455, retries=5):
    import time
    for attempt in range(1, retries+1):
        try:
            import obsws_python
            req = obsws_python.ReqClient(host="127.0.0.1", port=port, password=password, timeout=3)
            ver = req.get_version()
            print(f"[OK] Connected to OBS {ver.obs_version} (WebSocket {ver.obs_web_socket_version})")
            return True
        except Exception as e:
            if "ConnectionRefusedError" in str(e) or "10061" in str(e):
                if attempt < retries:
                    print(f"[setup] WebSocket not ready yet, retrying in 2s... (attempt {attempt}/{retries})")
                    time.sleep(2)
                    continue
                else:
                    print(f"[ERROR] Connection refused. Make sure OBS WebSocket server is enabled on port {port}.")
                    print("  In OBS: Tools -> WebSocket Server Settings -> Enable server")
                    return False
            else:
                print(f"[ERROR] Connection failed: {e}")
                return False
    return False

def main():
    print("\n" + "=" * 60)
    print("  WINDOW RECORDER SETUP")
    print("=" * 60 + "\n")
    install_deps()
    print("\n[step 1/3] OBS Studio")
    if not ensure_obs_running():
        print("[setup] OBS not running. Aborting.")
        sys.exit(1)
    print("[OK] OBS is running.\n")
    print("[step 2/3] OBS WebSocket password")
    pwd = ""
    port = 4455
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            pwd = cfg.get("obs", {}).get("password", "")
            port = cfg.get("obs", {}).get("port", 4455)
        except json.JSONDecodeError:
            print("[setup] config.json is corrupted. Recreating.")
            pwd = ""
            port = 4455
    else:
        pwd = ""
    if pwd:
        print("[setup] Using existing password from config.")
        if test_connection(pwd, port):
            print("[OK] Connection successful.\n")
            print("[step 3/3] Complete")
            print("Setup complete. You can now run start_recorder.bat.")
            return
        else:
            print("[ERROR] Password in config is incorrect or OBS WebSocket settings are wrong.")
            print(f"Check OBS WebSocket password and port {port}, then run setup again.")
            sys.exit(1)
    else:
        pwd = get_password()
    create_config(pwd)
    print("\n[step 3/3] Testing connection...")
    if test_connection(pwd, port):
        print("[OK] Setup complete. You can now run start_recorder.bat.")
    else:
        print("[ERROR] Connection failed. Please check:")
        print("  - OBS is running")
        print("  - WebSocket server is enabled (Tools -> WebSocket Server Settings)")
        print("  - Password matches")
        print(f"  - Port is {port} (check OBS WebSocket settings)")
        print("Run setup again after fixing.")
        sys.exit(1)

if __name__ == "__main__":
    main()