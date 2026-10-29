"""Compatibility entry for the installed read_pose command."""
import os
from pathlib import Path

os.environ.setdefault('SO101_CONFIG_DIR', str(Path(__file__).resolve().parent / 'config'))

if __name__ == '__main__':
    from so101_rollout.operations.read_pose import main

    main()
