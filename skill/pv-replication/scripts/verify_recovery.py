#!/usr/bin/env python3
"""Read-only minimum recovery inventory checker; standard library only.

Does not decode media, restore a film, invoke FFmpeg, render, or delete files.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify(manifest, root):
    errors, checked, frame_count = [], 0, 0

    def need(ok, message):
        if not ok:
            errors.append(message)
        return ok

    def file_check(record, label):
        nonlocal checked
        if not need(isinstance(record, dict), f"{label}: file record required"):
            return
        name, expected = record.get("path"), record.get("sha256")
        if not need(isinstance(name, str) and bool(name), f"{label}: path required"):
            return
        path = Path(name)
        if not need(not path.is_absolute() and ".." not in path.parts, f"{label}: safe relative path required"):
            return
        path = (root / path).resolve()
        if not need(path.is_relative_to(root.resolve()), f"{label}: path escapes project"):
            return
        if not need(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected), f"{label}: SHA256 required"):
            return
        if need(path.is_file(), f"{label}: file missing"):
            checked += 1
            need(sha(path) == expected, f"{label}: hash mismatch")

    if not isinstance(manifest, dict):
        return {"ok": False, "errors": ["manifest must be an object"]}
    need(manifest.get("schema") == "pv-minimal-recovery-v1", "unsupported schema")
    file_check(manifest.get("base"), "base")
    media = manifest.get("media", {})
    if not isinstance(media, dict):
        media = {}
    for name in ("fps_num", "fps_den", "total_frames", "width", "height"):
        value = media.get(name)
        need(type(value) is int and value > 0, f"media.{name}: positive integer required")
    total = media.get("total_frames")
    sets = manifest.get("patch_sets")
    if not need(isinstance(sets, list) and bool(sets), "patch_sets required"):
        sets = []
    intervals, ids = [], set()
    for patch_set in sets:
        if not need(isinstance(patch_set, dict), "patch set must be an object"):
            continue
        ident = patch_set.get("id")
        if not need(isinstance(ident, str) and bool(ident) and ident not in ids, "unique patch set id required"):
            continue
        ids.add(ident)
        interval = patch_set.get("interval")
        if not need(isinstance(interval, list) and len(interval) == 2 and all(type(n) is int for n in interval)
                    and type(total) is int and 0 <= interval[0] < interval[1] <= total,
                    f"{ident}: valid integer half-open interval required"):
            continue
        intervals.append((interval[0], interval[1], ident))
        records = patch_set.get("frames")
        if not need(isinstance(records, list) and bool(records), f"{ident}: complete frame records required"):
            continue
        seen = []
        for record in records:
            if not need(isinstance(record, dict) and type(record.get("frame")) is int,
                        f"{ident}: integer frame record required"):
                continue
            n = record["frame"]
            seen.append(n)
            file_check(record, f"{ident}/f{n}")
        ordered = sorted(seen)
        need(len(ordered) == interval[1]-interval[0]
             and all(n == interval[0]+offset for offset, n in enumerate(ordered)),
             f"{ident}: missing/duplicate/out-of-range patch frame")
        frame_count += len(ordered)
    last = -1
    for start, end, ident in sorted(intervals):
        need(start >= last, f"{ident}: overlapping/conflicting patch intervals")
        last = max(last, end)
    return {"ok": not errors, "errors": errors, "hashed_files": checked, "declared_patch_frames": frame_count,
            "media_parameters_probed": False, "visual_quality_verified": False,
            "restoration_executed": False, "files_changed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = verify(json.loads(args.manifest.read_text(encoding="utf-8")), args.root)
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({"ok": False, "input_error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
