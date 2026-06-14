"""Run the setup web app standalone (development):

    python -m daily_brief.web [--config config.toml] [--port 8080]
"""

from __future__ import annotations

import argparse

from . import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daily_brief.web")
    parser.add_argument("--config", help="Path to config.toml to edit.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)

    app = create_app(args.config)
    app.run(host=args.host, port=args.port, debug=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
