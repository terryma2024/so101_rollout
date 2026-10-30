"""Small shared I/O helpers. Generated output must stay outside its inputs."""
import json
from pathlib import Path


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def new_output(path, protected=None):
    """Fail before writing if a run would overwrite evidence or write into source."""
    path = Path(path).resolve()
    if protected is not None:
        source = Path(protected).resolve()
        if path == source or path.is_relative_to(source) or source.is_relative_to(path):
            raise ValueError('output and source must not overlap')
    path.mkdir(parents=True, exist_ok=False)
    return path
