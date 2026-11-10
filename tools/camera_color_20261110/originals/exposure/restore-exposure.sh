#!/bin/sh
set -eu
v4l2-ctl -d /dev/v4l/by-id/usb-icSpring_icspring_camera-video-index0 --set-ctrl=exposure_time_absolute=40
v4l2-ctl -d /dev/v4l/by-id/usb-icSpring_icspring_camera-video-index0 --get-ctrl=exposure_time_absolute
