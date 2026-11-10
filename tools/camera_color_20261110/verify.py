"""Read-only verification of the archived 2026-11-10 camera experiments.

Default: checked-in snapshots and original-script hashes, no third-party imports.
--raw-root: additionally hash retained streams/metrics and reproduce every PNG.
No camera access, subprocess execution, evidence writes, or hardware imports.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ARCHIVE = REPO / "docs/experiments/camera-color-20261110"
SEQUENCES = {"exposure": [40, 60, 80, 40], "gamma-coarse": [67, 90, 120, 67],
             "gamma-refine": [67, 100, 110, 67]}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text())


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_hash(path, record):
    require(path.stat().st_size == record["bytes"], f"Size mismatch: {path}")
    require(sha256(path) == record["sha256"], f"SHA-256 mismatch: {path}")


def check_roi(roi):
    require(len(roi["median_rgb"]) == 3, "RGB must have three channels")
    require(all(math.isfinite(x) and 0 <= x <= 255 for x in roi["median_rgb"]), "Invalid RGB")
    for key in ["zero_fraction", "le2_fraction", "ge253_fraction"]:
        require(all(math.isfinite(x) and 0 <= x <= 1 for x in roi[key]), f"Invalid {key}")
    for key in ["max_channel_lt32_fraction", "max_channel_lt16_fraction"]:
        require(0 <= roi[key] <= 1, f"Invalid {key}")


def verify_snapshot(root, phase):
    manifest, stats, verification = [read_json(root / name) for name in
                                    ["manifest.json", "statistics.json", "verification.json"]]
    baseline = phase == "baseline"
    if not baseline:
        require(manifest["sequence"] == SEQUENCES[phase], f"Sequence mismatch: {phase}")
        require(manifest["error"] is None and manifest["restore_error"] is None, "Trial failed")
        require(all(manifest["final_state_matches"].values()), "Recorded restoration failed")
        control = "exposure" if phase == "exposure" else "gamma"
        require([c[control] for c in manifest["conditions"]] == SEQUENCES[phase], "Condition mismatch")
        for c in manifest["conditions"]:
            require(abs(c["end"] - c["start"] - 15) < .1, "Unexpected record duration")
        warnings = read_json(root / "jpeg-warning-frames.json")
        require(warnings == stats["decode_quality"]["excluded_warning_frames"], "JPEG audit mismatch")
    output = {}
    for camera in ["wrist", "side"]:
        recorded = next(x for x in manifest["results"] if x["camera"] == camera)
        require(recorded["error"] is None, f"Capture error: {phase}/{camera}")
        require((recorded["width"], recorded["height"]) == (640, 480), "Unexpected dimensions")
        require(recorded["controls_format_and_device_unchanged"], "Capture worker changed device")
        before = root / camera / "before.txt" if baseline else root / f"{camera}-before.txt"
        after = root / camera / "after.txt" if baseline else root / f"{camera}-after.txt"
        require(before.read_bytes() == after.read_bytes(), f"Recorded state mismatch: {camera}")
        if not baseline:
            require(before.read_bytes() == (root / f"{camera}-final-live-verification.txt").read_bytes(),
                    "Historical final readback differs")
        cs = stats[camera]
        require(recorded["frames"] == cs["frames" if baseline else "total_complete_frames"], "Total frame count mismatch")
        pv = verification[camera]
        png_count = pv.get("png_lossless_roundtrip_checked", pv.get("saved_png_lossless_roundtrips_verified"))
        require(png_count == recorded["saved_png"], "Recorded PNG verification count mismatch")
        if baseline:
            conditions = {"baseline": cs}
        else:
            conditions = cs["conditions"]
        counts = {}
        for name, condition in conditions.items():
            usable = condition["analysis_frames"] if baseline else condition["frames"]
            require(usable > 200, f"Insufficient condition frames: {name}")
            require(len(condition["rois"]) == (26 if baseline else 27), "ROI count mismatch")
            for roi in condition["rois"].values():
                check_roi(roi)
            separation = condition["cube_separation"]
            red_key = "red_frames_without_R_over_G" if baseline else "red_dominance_reversal_frames"
            green_key = "green_frames_without_G_over_R" if baseline else "green_dominance_reversal_frames"
            require(separation[red_key] == 0 and separation[green_key] == 0,
                    "Unexpected dominance reversal")
            if not baseline:
                require(usable == pv["usable_condition_frames"][name], "Usable frame count mismatch")
                excluded = sum(w["condition"] == name for w in warnings) if camera == "side" else 0
                require(condition["captured_condition_frames"] - excluded == usable, "JPEG exclusion count mismatch")
            counts[name] = usable
        output[camera] = {"complete_frames": recorded["frames"], "png_checked_historically": png_count,
                          "usable_condition_frames": counts, "recorded_state_equal": True}
    if not baseline:
        yuv = read_json(root / "followup/yuyv-diagnostics.json")
        require(yuv["validation"]["mismatched_channel_samples"] == 0, "Historical YUYV mismatch")
        require(sum(yuv[c["name"]]["frames"] for c in manifest["conditions"]) ==
                sum(c["frames"] for c in stats["wrist"]["conditions"].values()), "YUYV frame count mismatch")
    if phase == "gamma-refine":
        pink = read_json(root / "followup/pink-highlight-audit.json")["conditions"]
        for name, row in pink.items():
            require(abs(row["R_ge253_fraction"] - stats["wrist"]["conditions"][name]["rois"]["chart_r1_c3"]["ge253_fraction"][0]) < 1e-12,
                    "Pink highlight audit mismatch")
            require(0 <= row["pre_clamp_R_gt255_fraction"] <= row["R_eq255_fraction"] <= row["R_ge253_fraction"] <= 1,
                    "Invalid highlight endpoint fractions")
    return output


def verify_raw(root, snapshot, phase):
    import cv2
    import numpy as np
    from PIL import Image

    manifest = read_json(snapshot / "manifest.json")
    stats = read_json(snapshot / "statistics.json")
    baseline = phase == "baseline"
    checked = {}
    for camera in ["wrist", "side"]:
        rows = [json.loads(line) for line in (root / camera / "frames.jsonl").read_text().splitlines()]
        capture = next(x for x in manifest["results"] if x["camera"] == camera)
        require(len(rows) == capture["frames"], "Raw frame count mismatch")
        require([r["index"] for r in rows] == list(range(len(rows))), "Non-contiguous frame indices")
        require(all(a["host_monotonic"] < b["host_monotonic"] for a, b in zip(rows, rows[1:])), "Non-monotonic times")
        png_count, offset = 0, 0
        with (root / camera / "stream.bin").open("rb") as stream:
            for row in rows:
                start, length = row["offset"], row["bytes"]
                require(start >= offset and length > 0, "Invalid frame byte range")
                if camera == "wrist":
                    require(start == offset and length == 640 * 480 * 2, "Invalid YUYV frame range")
                elif start > offset:
                    # UVC MJPEG includes zero padding after EOI, outside JPEG ranges.
                    stream.seek(offset)
                    padding = stream.read(start - offset)
                    require(len(padding) == start - offset and not any(padding), "Nonzero MJPEG padding")
                offset = start + length
                if "png" not in row:
                    continue
                stream.seek(row["offset"])
                raw = stream.read(row["bytes"])
                if camera == "wrist":
                    decoded = cv2.cvtColor(np.frombuffer(raw, np.uint8).reshape(480, 640, 2), cv2.COLOR_YUV2BGR_YUY2)
                else:
                    decoded = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
                image_path = (root / camera / row["png"]).resolve()
                require(image_path.is_relative_to((root / camera).resolve()), "PNG escapes evidence directory")
                with Image.open(image_path) as header:
                    require(header.size == (640, 480), "Unexpected saved image dimensions")
                saved = cv2.imread(str(image_path))
                require(decoded is not None and saved is not None and decoded.shape == saved.shape == (480, 640, 3), "Decode failure")
                require(np.array_equal(decoded, saved), f"PNG roundtrip mismatch: {image_path}")
                png_count += 1
            # The parser can consume final EOI padding before a partial next frame.
            complete_end = capture["full_frame_bytes"]
            if camera == "side" and complete_end > offset:
                stream.seek(offset)
                padding = stream.read(complete_end - offset)
                require(len(padding) == complete_end - offset and not any(padding), "Nonzero final MJPEG padding")
                offset = complete_end
        require(offset == capture["full_frame_bytes"], "Complete stream byte count mismatch")
        require((root / camera / "stream.bin").stat().st_size == offset + capture["trailing_incomplete_bytes"], "Trailing byte count mismatch")
        require(png_count == capture["saved_png"], "PNG count mismatch")
        if baseline:
            require(sum(30 <= r["elapsed"] < 45 for r in rows) == stats[camera]["analysis_frames"], "Baseline window mismatch")
        else:
            arrays = np.load(root / camera / "all-frame-metrics.npz", allow_pickle=False)
            require(arrays["median_rgb"].shape == (len(rows), 27, 3), "Metric array shape mismatch")
            for key in arrays.files:
                if key != "keys":
                    require(np.isfinite(arrays[key]).all(), f"Nonfinite metric: {key}")
            require(np.array_equal(arrays["times"], [r["host_monotonic"] for r in rows]), "Metric timestamps mismatch")
            for condition in manifest["conditions"]:
                count = sum(condition["start"] <= r["host_monotonic"] < condition["end"] for r in rows)
                require(count == stats[camera]["conditions"][condition["name"]]["captured_condition_frames"], "Raw window count mismatch")
        checked[camera] = png_count
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ARCHIVE, help="Checked-in snapshot directory")
    parser.add_argument("--raw-root", type=Path, help="Original evidence parent; also hash raw files and repeat PNG roundtrips")
    args = parser.parse_args()
    index = read_json(args.archive / "source-provenance.json")
    for record in index["copied_files"]:
        path = REPO / record["path"]
        require(path.resolve().is_relative_to(REPO), "Archive path escapes repository")
        verify_hash(path, record)
    result = {"mode": "raw_and_snapshots" if args.raw_root else "snapshots_only",
              "archived_files_sha256_checked": len(index["copied_files"]),
              "hardware_access": False, "phases": {}}
    for phase in ["baseline", *SEQUENCES]:
        result["phases"][phase] = verify_snapshot(args.archive / "snapshots" / phase, phase)
    if args.raw_root:
        for record in index["external_raw_files"]:
            verify_hash(args.raw_root / record["path"], record)
        result["external_raw_files_sha256_checked"] = len(index["external_raw_files"])
        result["fresh_png_roundtrips"] = {}
        for phase, folder in index["phases"].items():
            if phase != "historical":
                result["fresh_png_roundtrips"][phase] = verify_raw(args.raw_root / folder, args.archive / "snapshots" / phase, phase)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        raise SystemExit(f"Verification failed: {error}") from error
