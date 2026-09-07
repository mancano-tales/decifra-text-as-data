"""Importing test helpers must never create or migrate a real database."""
import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor


def test_importing_app_does_not_create_database(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    result = subprocess.run(
        [sys.executable, "-c", "import text_as_data.app"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "decifra.sqlite").exists()


def test_concurrent_first_requests_share_one_engine(monkeypatch):
    import text_as_data.app as api
    from text_as_data.db import get_engine

    calls = []
    def build():
        engine = get_engine("sqlite://")
        calls.append(engine)
        return engine

    monkeypatch.setattr(api, "_engine", None)
    monkeypatch.setattr(api, "get_engine", build)
    with ThreadPoolExecutor(max_workers=4) as pool:
        engines = list(pool.map(lambda _: api.get_engine_dependency(), range(8)))
    assert len(calls) == 1
    assert all(engine is engines[0] for engine in engines)
    engines[0].dispose()
