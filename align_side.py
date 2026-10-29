"""Compatibility entry for the installed align_side command."""
import os
from pathlib import Path

os.environ.setdefault('SO101_CONFIG_DIR', str(Path(__file__).resolve().parent / 'config'))

if __name__ == '__main__':
    os.chdir(Path(__file__).resolve().parent)

    from so101_test.camera.align_side import main

    main()
