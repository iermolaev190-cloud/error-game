"""Application entry point: CLI by default, Telegram polling on request."""

import asyncio
import sys

from world_error.interfaces.cli.main import main

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "telegram":
        from world_error.interfaces.telegram.bot import start_polling

        asyncio.run(start_polling())
    else:
        raise SystemExit(main())
