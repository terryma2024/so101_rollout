"""Locate external configuration and read legacy env assignments literally."""
import os
import pathlib


def resolve_config_dir(explicit: str | pathlib.Path | None = None) -> pathlib.Path:
    selected = explicit if explicit is not None else os.environ.get('SO101_CONFIG_DIR', pathlib.Path.cwd() / 'config')
    directory = pathlib.Path(selected).resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f'Configuration directory does not exist: {directory}')
    return directory


def read_env_file(path: str | pathlib.Path) -> dict[str, str]:
    return dict(line.split('=', 1) for line in pathlib.Path(path).read_text().splitlines()
                if '=' in line and not line.startswith('#'))


def load_arms_env(path: str | pathlib.Path | None = None) -> dict[str, str]:
    values = read_env_file(path if path is not None else resolve_config_dir() / 'arms.env')
    return {key: os.environ.get(key, value) for key, value in values.items()}
