"""
setup.py
────────
One-time setup script. Run this ONCE after cloning the project.

What it does:
  1. Creates output and temp directories.
  2. Copies .env.example → .env (if .env doesn't exist).
  3. Downloads the Montserrat Bold font for captions.
  4. Installs Python dependencies.

Usage:
  python setup.py
"""

import os
import sys
import shutil
import urllib.request

DIRS_TO_CREATE = [
    "output/drawing",
    "output/gaming",
    "output/informative",
    "temp",
    "temp/pexels_cache",
    "assets/fonts",
    "src",
]

FONT_URL = (
    "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Bold.ttf"
)
FONT_DEST = "assets/fonts/Montserrat-Bold.ttf"


def create_directories():
    print("[+] Creating directories...")
    for d in DIRS_TO_CREATE:
        os.makedirs(d, exist_ok=True)
        print(f"    OK {d}/")


def setup_env():
    if not os.path.exists(".env"):
        if os.path.exists(".env.example"):
            shutil.copy(".env.example", ".env")
            print("[+] Created .env from .env.example")
            print("    NOTE: Open .env and paste in your API keys before running main.py!")
        else:
            print("[!] .env.example not found -- please create .env manually.")
    else:
        print("[OK] .env already exists -- skipping.")


def download_font():
    if os.path.exists(FONT_DEST):
        print(f"[OK] Font already exists: {FONT_DEST}")
        return

    print("[+] Downloading Montserrat Bold font...")
    try:
        urllib.request.urlretrieve(FONT_URL, FONT_DEST)
        print(f"    Saved to {FONT_DEST}")
    except Exception as e:
        print(f"[!] Font download failed: {e}")
        print("    You can manually download Montserrat-Bold.ttf and place it in assets/fonts/")


def install_dependencies():
    print("\n[+] Installing Python dependencies (this may take a few minutes)...")
    ret = os.system(f"{sys.executable} -m pip install -r requirements.txt")
    if ret == 0:
        print("    Dependencies installed.")
    else:
        print("[!] Some dependencies may have failed. Check output above.")


def create_src_init():
    init_path = "src/__init__.py"
    if not os.path.exists(init_path):
        with open(init_path, "w") as f:
            f.write("# Auto Reels -- Source Package\n")
        print(f"    Created {init_path}")


def main():
    print("\n" + "="*55)
    print("  Auto Reels - One-Time Setup")
    print("="*55 + "\n")

    create_directories()
    create_src_init()
    setup_env()
    download_font()
    install_dependencies()

    print("\n" + "="*55)
    print("  Setup complete!")
    print("="*55)
    print("\nNext steps:")
    print("  1. Open .env and paste in your API keys")
    print("     - GEMINI_API_KEY  -> https://aistudio.google.com")
    print("     - PEXELS_API_KEY  -> https://www.pexels.com/api/")
    print("\n  2. Test the script generator:")
    print("     python main.py --channel gaming --dry-run")
    print("\n  3. Generate your first reel:")
    print("     python main.py --channel gaming")
    print("\n  4. Run all channels:")
    print("     python main.py")
    print()


if __name__ == "__main__":
    main()
