"""PyInstaller entry point: the Launcher of the real app."""

import sys

from app.launcher import main

if __name__ == "__main__":
    sys.exit(main())
