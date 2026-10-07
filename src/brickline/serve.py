import argparse
import os

import uvicorn

from .api import create_app


def main():
    parser = argparse.ArgumentParser(description="Brickline operating intelligence")
    parser.add_argument(
        "--demo", action="store_true", help="Synthetic data and explicit local demo identities"
    )
    parser.add_argument("--db", default=os.environ.get("BRICKLINE_DB", "runtime/brickline.db"))
    parser.add_argument("--port", type=int, default=8106)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--model", default="", help="Optional installed Ollama model for live review drafts")
    args = parser.parse_args()
    if args.demo and args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Demo identities may only be served on loopback")
    uvicorn.run(create_app(args.db, args.demo, args.model), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
