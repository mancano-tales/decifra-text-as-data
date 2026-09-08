from pathlib import Path
from fastapi.staticfiles import StaticFiles


def mount_frontend(app, directory: Path | None = None):
    directory = directory or Path(__file__).parent / "static"
    if not (directory / "index.html").is_file():
        raise RuntimeError("Frontend not built. Run npm ci and npm run build in frontend, then python scripts/build_frontend.py.")
    app.mount("/", StaticFiles(directory=directory, html=True), name="frontend")
