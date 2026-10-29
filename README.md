# SO101 arm setup with LeRobot

This repository configures SO101 leader and follower arms for teleoperation with [LeRobot](https://github.com/huggingface/lerobot).

## 1. Environment

| Component | Version or setting |
|---|---|
| System | Ubuntu, Linux x86_64 |
| Python | 3.12 in the uv-managed project `.venv` |
| LeRobot | 0.6.1, `lerobot[feetech,viz]`; the `viz` extra provides rerun visualization |
| PyTorch | 2.11.0 + CUDA 13.0, usable with the RTX 5060 Ti |
| Servos | Six Feetech STS3215 servos per arm, 1 Mbps, IDs 1 through 6 |
| Cameras | icSpring USB cameras named `wrist` and `side`, 640×480, used at about 20 fps |

## 2. Hardware connections

Both arms use CH343 USB serial adapters (`1a86:55d3`). Use `/dev/serial/by-id/` paths, which remain stable after reconnecting:

| Arm | Serial number | Serial path | Current device |
|---|---|---|---|
| Leader | `5CE5113682` | `/dev/serial/by-id/usb-1a86_USB_Single_Serial_5CE5113682-if00` | `/dev/ttyACM0` |
| Follower | `5CE5122459` | `/dev/serial/by-id/usb-1a86_USB_Single_Serial_5CE5122459-if00` | `/dev/ttyACM1` |

The `ttyACM0/1` numbers can change with connection order. The scripts use the by-id paths.

Wrist camera:

| Property | Value |
|---|---|
| Model | icSpring camera, USB `32e6:9005`, USB 2.0 |
| Device | `/dev/v4l/by-id/usb-icSpring_icspring_camera-video-index0`, currently `/dev/video0`; `/dev/video1` carries metadata, not images |
| Format | 640×480 YUYV only |
| Frame rate | Nominally 30 fps; measured maximum about 22.6 fps regardless of exposure, so configured at 20 fps |

Record datasets at 20 fps as well. Recording at 30 fps produces about one quarter duplicate frames.

Side camera:

| Property | Value |
|---|---|
| Model | icSpring camera, USB `32e6:9221`, serial `202404160005`, USB 2.0 |
| Device | `/dev/v4l/by-id/usb-icSpring_icspring_camera_202404160005-video-index0`, currently `/dev/video2`; `/dev/video3` carries metadata |
| Format | MJPG from 320×240 to 1920×1080; YUYV only at 640×480. Configured at 640×480 MJPG to reduce USB bandwidth |
| Frame rate | MJPG offers only 30 fps at each resolution. Set 30: setting 20 fails with `failed to set fps=20 (actual_fps=30.0)`. Actual output is about 20 fps regardless of exposure. Both cameras can run together without affecting each other |
| Lens | Wide angle, with distortion near the image edges |

Joint IDs:

| ID | Joint | Function |
|---|---|---|
| 1 | shoulder_pan | Base rotation |
| 2 | shoulder_lift | Upper arm pitch |
| 3 | elbow_flex | Elbow bend |
| 4 | wrist_flex | Wrist pitch |
| 5 | wrist_roll | Wrist rotation |
| 6 | gripper | Gripper |

## 3. Installation and interpreters

### 3.1 System preparation

```bash
# Serial access: log out and back in after joining dialout.
sudo usermod -aG dialout $USER

# Dataset recording requires ffmpeg.
sudo apt install ffmpeg

# uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3.2 Project environment

The project dependencies are locked in `uv.lock`. For a fresh setup, synchronize that lock and explicitly install the local package:

```bash
cd ~/Projects/so101_test
uv sync --locked
uv pip install --python .venv/bin/python --no-deps -e .
```

Use `uv run --no-sync` for project commands after setup. It uses the existing environment without resolving or updating dependencies. Reinstall the editable project if its checkout location changes.

These were the original initialization commands, retained for reference:

```bash
uv init --python 3.12 --name so101-test --no-workspace
uv add "lerobot[feetech,viz]"
```

The interpreters have separate roles:

| Workflow | Environment |
|---|---|
| Calibration, teleoperation, project tools and tests | Project `.venv` |
| Recording, rollout and camera snapshots | `/data/work/venvs/so101-real-lerobot-061` |
| Voice agent | `/data/work/venvs/so101-voice-lerobot-061`; `voice_agent.sh` retains its `VENV` override |

The application must also be installed in each runtime environment. Build a wheel with `uv build --wheel --out-dir <wheel-directory>`, then install that exact wheel with `uv pip install --python <environment>/bin/python --no-deps <wheel>`. This installs the project without upgrading runtime dependencies. Keep runtime installations independent of temporary worktrees.

### 3.3 Verification

```bash
uv run --no-sync python -c "import torch, lerobot; print(torch.__version__, torch.cuda.is_available())"
ls -l /dev/serial/by-id/
```

The existing `so101-test` command still prints its greeting.

## 4. Source layout and configuration

| Path | Purpose |
|---|---|
| `src/so101_test/voice/` | Voice orchestration, intent, policy, ASR, verification and replay modules |
| `src/so101_test/camera/` | Camera capture, calibration targets, intrinsics, extrinsics and alignment |
| `src/so101_test/operations/` | Recording and teleoperation adapters, bus diagnostics and pose reading |
| `src/so101_test/config.py` | Configuration selection and literal env-file parsing |
| `config/arms.env` | Arm ports and IDs (`my_leader` / `my_follower`), wrist/side camera paths and frame rates |
| `config/camera.env` | Exposure and white-balance defaults |
| `scripts/` | Shell launcher implementations, sharing `scripts/lib/common.sh` |
| `calibrate_follower.sh`, `calibrate_leader.sh` | Follower and leader calibration |
| `teleop.sh` | Leader/follower teleoperation with wrist/side images and joint data in rerun |
| `teleop_viz.py` | Compatibility entry for the teleoperation adapter: sends images at camera rate (20 Hz), removing duplicates without changing control frequency; about 4 MB/s for both cameras instead of about 12 MB/s |
| `check_bus.py` | Read-only servo communication diagnostics, for example `uv run --no-sync check_bus.py leader 30` while moving the arm by hand |
| `read_pose.py` | Read-only comparison of both arms' joint angles, without enabling torque or moving the arms |
| [docs/guides/so101-lerobot.html](docs/guides/so101-lerobot.html) | Interactive explanation of servos, the bus protocol, calibration conversion, position control, the main loop, cameras and rerun; open directly in a browser |
| [docs/plans/voice-agent-plan.md](docs/plans/voice-agent-plan.md) | Historical voice-agent plan |

The seven root shell commands remain available: `voice_agent.sh`, `teleop.sh`, `record.sh`, `rollout.sh`, `calibrate_follower.sh`, `calibrate_leader.sh` and `camera_settings.sh`. They anchor cwd to the checkout root before running their implementations.

Root Python compatibility commands remain for `voice_agent.py`, `voice_latency_check.py`, `calib_capture.py`, `calib_intrinsics.py`, `calib_extrinsics.py`, `calib_targets.py`, `align_side.py`, `check_bus.py`, `read_pose.py`, `record_viz.py` and `teleop_viz.py`. Their implementation lives in the package. Internal voice helpers have no root copies. Package commands use `python -m so101_test.<group>.<module>`, for example:

```bash
uv run --no-sync python -m so101_test.operations.read_pose
./voice_agent.sh --help
```

Configuration stays outside the wheel. Root delegates supply the checkout's `config/` directory when `SO101_CONFIG_DIR` is unset. Installed commands outside a checkout need an explicit directory:

```bash
SO101_CONFIG_DIR=/home/matianyi/Projects/so101_test/config \
  /data/work/venvs/so101-real-lerobot-061/bin/python -m so101_test.camera.calib_intrinsics wrist
```

The Python loader selects an explicit directory first, then `SO101_CONFIG_DIR`, then cwd's `config/`. A selected missing directory fails. Existing CLI handling takes precedence over process environment, which takes precedence over checked-in defaults; explicitly empty environment values also override defaults. Bash launchers evaluate trusted shell defaults, including the viewer host derived from `SSH_CONNECTION`. The Python parser reads values literally: direct Python calibration needs an explicit `RERUN_VIEWER_HOST` if the default contains a shell expression.

Direct calibration commands preserve caller cwd for relative paths. The root `align_side.py` compatibility command retains its repository-root cwd; its package module uses caller cwd.

## 5. Workflow

Calibration and teleoperation require keyboard input. Run them in a separate terminal, without Claude Code's `!` prefix.

### 5.1 Identify serial ports after changing machines or cables

```bash
uv run --no-sync lerobot-find-port
```

Follow the prompt to unplug an arm's USB cable and identify its port. Update `config/arms.env`.

### 5.2 Calibrate

```bash
./calibrate_follower.sh
./calibrate_leader.sh
```

For each arm:

1. Place each joint roughly halfway through its range, then press Enter. Point the base forward, hold the upper arm vertically, bend the elbow about 90° forward, straighten the wrist and leave the gripper half open. See the official [SO101 calibration images](https://huggingface.co/docs/lerobot/so101), in the Calibrate section.
2. Slowly move each joint to both limits. The terminal shows each joint's MIN and MAX.
3. Press Enter again to save after moving all joints.

Use similar midpoint poses for the leader and follower.

On this machine, `HF_HOME=/data/models/huggingface`, so calibration files live at:

```text
/data/models/huggingface/lerobot/calibration/robots/so_follower/my_follower.json
/data/models/huggingface/lerobot/calibration/teleoperators/so_leader/my_leader.json
```

Without `HF_HOME`, the default is `~/.cache/huggingface/lerobot/calibration/`. Existing `TORCH_HOME=/data/models/torch`, model files, calibration caches, datasets, policies and evidence stay at their existing locations.

A normal calibration has joint 1 through 4 `range_min`/`range_max` values centered roughly on 2047 with spans of about 2000 to 2600. Joint 5, `wrist_roll`, is a continuous-rotation servo with the fixed range `0` to `4095`. The gripper range is about 1300 to 1500; different leader/follower ranges are fine because each maps to 0 to 100%.

### 5.3 Check calibration

Place both arms in the same pose, then run:

```bash
uv run --no-sync read_pose.py
```

A `diff` of about ±2° per joint indicates matching calibration. Recalibrate an arm if a joint differs substantially despite matching physical poses.

### 5.4 Teleoperate

```bash
./teleop.sh
```

The script shows wrist/side images and joint data in rerun (`--display_data=true`):

- On the local desktop, it opens a rerun window.
- Over SSH, it sends data to a native rerun viewer on your own computer, even if the workstation desktop is logged in and `DISPLAY` is available. It takes the initiating IP from the first field of `SSH_CONNECTION`. Override it with `RERUN_VIEWER_HOST=<ip> ./teleop.sh`; see `config/arms.env`.

Start that viewer before launching teleoperation. The viewer must be version 0.34 or later: 0.33.x hangs when loading JPEG images, fixed in 0.34.0. LeRobot constrains the sender to 0.33.1; viewer 0.40.0 has been verified with it:

```bash
uvx --from rerun-sdk==0.40.0 rerun --bind 0.0.0.0     # Or: pip install rerun-sdk==0.40.0 && rerun --bind 0.0.0.0
```

Then run `./teleop.sh` in the SSH session. The script reports a missing viewer and exits.

The original `lerobot-teleoperate` sends a JPEG on every 60 Hz control cycle, about 6 MB/s; two thirds are duplicates. A slow viewer can block the teleoperation loop in `rr.log`, stopping follower updates and logging `Sender has been blocked for over 5 seconds waiting for space in channel`. `teleop.sh` uses the camera-rate limiter in `teleop_viz.py`. Use the native viewer; the web viewer (`--serve-web`) cannot handle this volume.

Before starting, place both arms in similar poses: the follower moves directly to the leader's pose at startup. Stop with `Ctrl+C`. Exiting releases follower torque, so support the arm to prevent it from falling.

## 6. Troubleshooting

| Symptom | Cause or action |
|---|---|
| `EOFError: EOF when reading a line` | Calibration ran without interactive input, such as through `!`. Use a separate terminal |
| `Permission denied: /dev/ttyACM*` | Join `dialout` using section 3.1 and log in again |
| Startup `Full found motor list` omits a servo | A servo briefly failed to respond; LeRobot checks once at startup. Power-cycle both arms. If it recurs, run `uv run --no-sync check_bus.py leader 30`, move the arm by hand and inspect the affected servo's wiring |
| Missing serial port or unresponsive servo | Check arm power and USB cables; inspect `ls -l /dev/serial/by-id/` |
| `Failed to open connection to X server` | SSH lacks a graphical session. `teleop.sh` sends to the native viewer at `RERUN_VIEWER_HOST` |
| Viewer hangs as soon as an image appears | The rerun 0.33.x JPEG bug. Upgrade the viewer to 0.34 or later; 0.40.0 is the documented choice |
| Follower stops tracking and viewer freezes | Viewer backpressure can block teleoperation. Immediately press `Ctrl+C` while supporting the follower. Use `teleop.sh` with its `teleop_viz.py` limiter and the native viewer |
| `OpenCVCamera(...) failed to set fps=...` | Unsupported camera rate. Inspect `v4l2-ctl -d <设备> --list-formats-ext` and update `config/arms.env` |
| Camera unavailable or `Device or resource busy` | Another program holds the camera. Close it and retry; inspect `v4l2-ctl --list-devices` |
| Joint direction or angle is clearly wrong | Recalibrate that arm, checking its midpoint pose |

## 7. Data collection and camera calibration for real ACT

Root commands remain available in this directory. These workflows use `/data/work/venvs/so101-real-lerobot-061`, with LeRobot 0.6.1 and dataset components. The separate project `.venv` keeps its role.

### 7.1 Lock exposure and white balance

```bash
./camera_settings.sh show    # Show current values.
./camera_settings.sh lock    # Apply manual exposure and fixed white balance from config/camera.env.
./camera_settings.sh snap    # Capture both views; inspect brightness, clipping and color.
./camera_settings.sh auto    # Restore automatic settings.
```

Run `lock`, then `snap`. Adjust exposure and white balance in `config/camera.env`, repeating until the red and green cubes are clear without large overexposed areas. `record.sh` runs `lock` on every start. Reconnecting USB or restarting loses these camera settings.

### 7.2 Record

```bash
./record.sh real-cube-bowl-pilot-20261027 10          # Pilot: 10 episodes.
RESUME=1 ./record.sh real-cube-bowl-pilot-20261027 50  # Resume the same dataset.
```

Datasets stay at `/data/work/so101-datasets/<名字>` and are not uploaded to HF. Use the cube placement checklist at `/data/work/so101-evidence/real-robot/prep-20261026/layout/a4-placement-mat.pdf`.

### 7.3 Calibrate cameras for the digital twin

Print `/data/work/so101-evidence/real-robot/calib-20261027/calib-targets.pdf` on landscape A4 at 100% scale. Page 1 is a ChArUco board to mount on stiff card; page 2 is the ArUco positioning sheet.

```bash
P=/data/work/venvs/so101-real-lerobot-061/bin/python
$P calib_capture.py charuco wrist        # Move the ChArUco board through positions, angles and distances; saves 25 images.
$P calib_capture.py charuco side         # Repeat for the side camera.
$P calib_intrinsics.py wrist
$P calib_intrinsics.py side --rational   # Eight-parameter model for the wide-angle side camera.
# Align the ArUco sheet's edges and orientation with the A4 positioning sheet, then:
$P calib_capture.py aruco
$P calib_extrinsics.py /data/work/so101-evidence/real-robot/calib-20261027/aruco-sheet-layout.json
```

Results stay at `/data/work/so101-evidence/real-robot/calib-<日期>/`:

| File | Contents |
|---|---|
| `intrinsics-wrist.json`, `intrinsics-side.json` | Intrinsics; rms below 0.5 px is good |
| `extrinsics-side.json` | Side camera position and orientation relative to the follower's rotation axis |

Keep the side camera fixed after calibration. Recalibrate its extrinsics if it moves.
