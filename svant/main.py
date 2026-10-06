"""
Main entry point for SVANT application.
Launches the FastAPI backend and desktop user interface.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
import uvicorn

from svant import __version__, __app_name__
from svant.config import settings
from svant.logger import get_logger

logger = get_logger("svant.main")


def print_banner() -> None:
    banner = f"""
========================================================================
   ____ _    __ ___     _   __ _____
  / __/| |  / // _ |   / | / //_  __/
 _\\ \\  | | / // __ |  /  |/ /  / /   
/___/  |___//_/ |_| /_/|_/  /_/    
 Local-First Project & File Intelligence Desktop Application
 Version: {__version__} | Environment: {settings.env}
 Data Directory: {settings.data_dir}
========================================================================
"""
    print(banner)


def run_app(host: str, port: int, open_browser: bool = False) -> None:
    """Launch SVANT server."""
    print_banner()
    logger.info(f"Starting {__app_name__} on http://{host}:{port}")

    if open_browser:
        try:
            webbrowser.open(f"http://{host}:{port}")
        except Exception:
            pass

    uvicorn.run(
        "svant.api.app:app",
        host=host,
        port=port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=f"{__app_name__} Desktop Server")
    parser.add_argument("--host", default=settings.host, help=f"Host interface (default: {settings.host})")
    parser.add_argument("--port", type=int, default=settings.port, help=f"Port (default: {settings.port})")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open browser on start")

    args = parser.parse_args()
    run_app(host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
