"""Launch Alpha 1S Studio from the portable source folder."""
from pathlib import Path
import subprocess
import sys


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Launch: /usr/bin/python3 src/main.py")
        return
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "alpha_demo/close_windows.py")], check=True)
    from alpha_demo.control_panel import main as launch
    launch()


if __name__ == "__main__":
    main()
