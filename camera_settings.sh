#!/usr/bin/env bash
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || exit
exec "$ROOT/scripts/camera_settings.sh" "$@"
