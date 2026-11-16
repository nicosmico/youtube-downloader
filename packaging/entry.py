"""PyInstaller entry point: the Launcher of the real app."""

import sys

from app.detach import detach_if_needed
from app.launcher import main

if __name__ == "__main__":
    # macOS .app: the server lives in a detached child so reopening the app reaches Single Instance.
    if detach_if_needed(sys.argv[1:]):
        sys.exit(0)
    sys.exit(main())
