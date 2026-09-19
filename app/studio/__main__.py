"""Entry point for python -m app.studio."""
import argparse
from app.studio.server import run_studio

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start MemeTrading Local Studio GUI")
    parser.add_argument("--port", type=int, default=3000, help="Port to listen on (default 3000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address (default 127.0.0.1)")
    args = parser.parse_args()

    run_studio(host=args.host, port=args.port)
