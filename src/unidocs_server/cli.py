"""Command line entry point for the UniDocs server.

    unidocs-server --host 0.0.0.0 --port 8550

Prints the API token once on startup so a desktop app can be connected. The
token is also written to ``~/.config/UniDocs/server_token.txt`` (or taken from
``UNIDOCS_API_TOKEN``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from unidocs_server.auth import current_token  # noqa: E402
from unidocs_server.app import create_app  # noqa: E402

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8550


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve UniDocs as a web app + sync API.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="bind address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port")
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
    )
    args = parser.parse_args(argv)

    import uvicorn

    token = current_token()
    print(f"UniDocs server: http://{args.host}:{args.port}/")
    print(f"API token:      {token}")
    print("Connect the desktop app with this URL + token under Settings -> Cloud sync.")

    uvicorn.run(
        create_app(),
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        ws="websockets-sansio",
    )


if __name__ == "__main__":
    main()
