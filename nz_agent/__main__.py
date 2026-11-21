"""Allow ``python -m nz_agent`` to start the chat CLI."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
