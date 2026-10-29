"""Compatibility entry for the installed calib_capture command."""
import os
from pathlib import Path

os.environ.setdefault('SO101_CONFIG_DIR', str(Path(__file__).resolve().parent / 'config'))

if __name__ == '__main__':
    from so101_rollout.camera.calib_capture import main

    main()
