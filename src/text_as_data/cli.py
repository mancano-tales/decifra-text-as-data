"""Run the local application, serving the built UI and API on one port."""
import argparse
import os
from pathlib import Path
import webbrowser
from threading import Timer


def main():
    parser = argparse.ArgumentParser(prog="decifra")
    parser.add_argument("command", choices=["serve"])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    from .config import data_directory
    directory = (args.data_dir or data_directory()).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DECIFRA_DB_URL", "sqlite:///" + (directory / "decifra.sqlite").as_posix())
    from .app import app
    from .webapp import mount_frontend
    mount_frontend(app)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Decifra: {url} (data: {directory})", flush=True)
    if not args.no_browser:
        Timer(1.5, lambda: webbrowser.open(url)).start()
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
