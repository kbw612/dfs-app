import json
import threading
from pathlib import Path

from backend.repositories.atomic_json import atomic_write_json, locked_read_modify_write


def test_atomic_write_json_creates_parent_dirs(tmp_path: Path):
    path = tmp_path / "nested" / "dir" / "file.json"
    atomic_write_json(path, {"a": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}


def test_atomic_write_json_overwrites_existing_file(tmp_path: Path):
    path = tmp_path / "file.json"
    atomic_write_json(path, {"a": 1})
    atomic_write_json(path, {"a": 2, "b": 3})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 2, "b": 3}


def test_atomic_write_json_leaves_no_temp_files_behind(tmp_path: Path):
    path = tmp_path / "file.json"
    atomic_write_json(path, {"a": 1})
    leftovers = [p for p in tmp_path.iterdir() if p != path]
    assert leftovers == []


def test_locked_read_modify_write_applies_the_modification(tmp_path: Path):
    path = tmp_path / "file.json"
    atomic_write_json(path, {"a": 1})

    def load() -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def modify(data: dict) -> None:
        data["b"] = 2

    locked_read_modify_write(path, load, modify)
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1, "b": 2}


def test_locked_read_modify_write_serializes_concurrent_callers(tmp_path: Path):
    # Regression test for the exact failure mode locked_read_modify_write
    # exists to prevent -- see atomic_json.py's own docstring. Without the
    # per-path lock, N threads racing a read-modify-write on the same file
    # can both lose updates and corrupt the file outright.
    path = tmp_path / "file.json"
    atomic_write_json(path, {})

    def load() -> dict:
        text = path.read_text(encoding="utf-8")
        return json.loads(text) if text else {}

    def save(key: str) -> None:
        def modify(data: dict) -> None:
            data[key] = key

        locked_read_modify_write(path, load, modify)

    keys = [f"key-{i}" for i in range(30)]
    threads = [threading.Thread(target=save, args=(k,)) for k in keys]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == set(keys)
