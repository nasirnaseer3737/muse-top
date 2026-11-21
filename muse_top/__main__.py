"""Allow ``python -m muse_top`` to start the chat CLI."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
