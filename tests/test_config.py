"""Configuration selection and literal parsing contracts."""
import importlib
import pathlib
import subprocess

import pytest


def test_config_selection_and_missing_path(tmp_path, monkeypatch):
    config = importlib.import_module('so101_test.config')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('SO101_CONFIG_DIR', raising=False)
    default = tmp_path / 'config'
    default.mkdir()
    selected = tmp_path / 'selected directory'
    selected.mkdir()
    assert config.resolve_config_dir() == default
    (default / 'arms.env').write_text('KEY=from-cwd\n')
    assert config.load_arms_env() == {'KEY': 'from-cwd'}
    monkeypatch.setenv('SO101_CONFIG_DIR', str(selected))
    assert config.resolve_config_dir() == selected
    assert config.resolve_config_dir(default) == default
    monkeypatch.setenv('SO101_CONFIG_DIR', str(tmp_path / 'missing'))
    with pytest.raises(FileNotFoundError):
        config.resolve_config_dir()
    with pytest.raises(FileNotFoundError):
        config.resolve_config_dir(tmp_path / 'also-missing')
    monkeypatch.setenv('SO101_CONFIG_DIR', str(selected))
    with pytest.raises(FileNotFoundError):
        config.load_arms_env()
    (selected / 'arms.env').write_text('KEY=from-environment-directory\n')
    assert config.load_arms_env() == {'KEY': 'from-environment-directory'}
    explicit = tmp_path / 'explicit.env'
    explicit.write_text('KEY=explicit\n')
    assert config.load_arms_env(explicit) == {'KEY': 'explicit'}
    explicit.unlink()
    with pytest.raises(FileNotFoundError):
        config.load_arms_env(explicit)


def test_literal_parser_never_evaluates_shell(tmp_path, monkeypatch):
    config = importlib.import_module('so101_test.config')
    path = tmp_path / 'literal.env'
    path.write_text('# ignored=x\nA=${HOME}\nB=$(touch forbidden)\nC=a=b\nD="quoted" # literal\n E= spaced \nEMPTY=\nno assignment\n')
    def forbidden(*args, **kwargs):
        pytest.fail('Python config must not invoke a shell')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    assert config.read_env_file(path) == {
        'A': '${HOME}', 'B': '$(touch forbidden)', 'C': 'a=b',
        'D': '"quoted" # literal', ' E': ' spaced ', 'EMPTY': '',
    }


def test_process_values_override_defaults(tmp_path, monkeypatch):
    # Legacy public API remains valid throughout migration; this exposes the old bug.
    from so101_test.voice.voice_policy import read_arms_env
    path = tmp_path / 'arms.env'
    path.write_text('FOLLOWER_PORT=default\nLEADER_PORT=default\n')
    monkeypatch.setenv('FOLLOWER_PORT', 'port with spaces')
    monkeypatch.setenv('LEADER_PORT', '')
    monkeypatch.setenv('UNDECLARED', 'not configuration')
    assert read_arms_env(path) == {'FOLLOWER_PORT': 'port with spaces', 'LEADER_PORT': ''}
