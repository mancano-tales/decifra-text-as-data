"""Copy a completed Vite build into the package for `decifra serve`."""
from pathlib import Path
import shutil
root = Path(__file__).resolve().parents[1]
source = root / "frontend/dist"
if not (source / "index.html").exists():
    raise SystemExit("Run npm ci and npm run build in frontend first.")
shutil.copytree(source, root / "src/text_as_data/static", dirs_exist_ok=True)
print("Frontend copied into the Decifra package.")
