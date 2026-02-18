import os
import sys
import subprocess
import time

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    item = """
    ╔════════════════════════════════════════════════════╗
    ║           LIVE TRANSLATION BRIDGE (BETA)           ║
    ║        [ En <-> Es |  Deepgram + Groq + Cartesia ] ║
    ╚════════════════════════════════════════════════════╝
    """
    print(item)

def check_env():
    env_path = ".env"
    
    # Required keys
    keys = [
        "DEEPGRAM_API_KEY",
        "GROQ_API_KEY",
        "CARTESIA_API_KEY",
        "VOICE_ID_OUTGOING"
    ]
    
    current_config = {}
    
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    current_config[k] = v
    
    missing_keys = [k for k in keys if k not in current_config or not current_config[k]]
    
    if missing_keys:
        print("\n[!] Missing Configuration. Please enter your API Keys:")
        print("    (You can copy-paste them here, they will be saved to .env)\n")
        
        new_config = current_config.copy()
        for key in keys:
            if key not in new_config or not new_config[key]:
                value = input(f" > Enter {key}: ").strip()
                if value:
                    new_config[key] = value
        
        # Save Env
        with open(env_path, "w") as f:
            for k, v in new_config.items():
                f.write(f"{k}={v}\n")
        print("\n[+] Configuration Saved!")
        time.sleep(1)

def run_translator():
    # Install deps first just in case
    # subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    
    print("\n[+] Starting Bridge... (Press Ctrl+C to Stop)\n")
    try:
        subprocess.run([sys.executable, "modular_bridge.py"])
    except KeyboardInterrupt:
        pass

def main_menu():
    while True:
        clear_screen()
        print_header()
        
        print("1. Start Translation Bridge")
        print("2. Update API Keys")
        print("3. Check Audio Devices")
        print("4. Exit")
        
        choice = input("\nSelect option (1-4): ")
        
        if choice == "1":
            check_env()
            run_translator()
            input("\nPress Enter to return to menu...")
        elif choice == "2":
            if os.path.exists(".env"):
                os.remove(".env")
            check_env()
        elif choice == "3":
             # We can run a small python snippet to list devices
             cmd = """
import pyaudio
p = pyaudio.PyAudio()
print('\\nAudio Devices found:')
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    print(f'  {i}: {info["name"]}')
"""
             subprocess.run([sys.executable, "-c", cmd])
             print("\nMake sure you see 'BlackHole 2ch' and 'BlackHole 16ch'.")
             input("\nPress Enter to return to menu...")
        elif choice == "4":
            sys.exit()

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\nGoodbye!")
