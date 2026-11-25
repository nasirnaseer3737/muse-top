"""Allow ``python -m muse_top`` to start the chat CLI."""

import sys

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
