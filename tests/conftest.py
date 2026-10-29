import pathlib
import sys


def pytest_sessionstart(session) -> None:
    """Record tempfile placement only for explicitly controlled evidence runs."""
    import os

    run_dir_value = os.environ.get("SO101_TEST_EVIDENCE_RUN_DIR")
    if not run_dir_value:
        return

    import json
    import tempfile

    import pytest

    run_dir = pathlib.Path(run_dir_value).resolve(strict=True)
    expected = run_dir / "tmp"
    actual = pathlib.Path(tempfile.gettempdir()).resolve()
    exported = [
        pathlib.Path(os.environ[name]).resolve() if os.environ.get(name) else None
        for name in ("TMPDIR", "TMP", "TEMP")
    ]
    if not expected.is_dir() or actual != expected or any(p != expected for p in exported):
        raise pytest.UsageError("controlled evidence run requires TMPDIR/TMP/TEMP and tempfile under run/tmp")

    worker = getattr(session.config, "workerinput", {}).get("workerid", "controller")
    proof = {
        "worker": worker,
        "pid": os.getpid(),
        "python": sys.executable,
        "tempfile": str(actual),
        "scratch": str(expected),
    }
    with (run_dir / f"tempfile-{worker}-{os.getpid()}.json").open("x") as stream:
        json.dump(proof, stream, indent=2)
        stream.write("\n")
