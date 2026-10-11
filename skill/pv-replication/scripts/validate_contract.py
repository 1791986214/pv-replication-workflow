#!/usr/bin/env python3
"""Validate a source-timed PV contract, not the visual quality of its drawings.

Standard library only. Does not render, change files, fetch URLs, or delete files.
Exit 0: declarations pass; 1: contract errors; 2: unreadable JSON/input.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

HASH = re.compile(r"[0-9a-f]{64}\Z")
MASKS = {"explicit-alpha", "semantic-tracked", "source-explicit", "none"}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def validate(data, stage="preflight", root=None):
    errors = []

    def need(ok, msg):
        if not ok:
            errors.append(msg)
        return bool(ok)

    def integer(value):
        return type(value) is int

    def span(value, label, outer=None):
        if not need(isinstance(value, list) and len(value) == 2
                    and all(integer(x) for x in value), f"{label}: integer [start,end) required"):
            return None
        if not need(0 <= value[0] < value[1], f"{label}: empty/reversed/negative interval"):
            return None
        if outer:
            need(outer[0] <= value[0] < value[1] <= outer[1], f"{label}: outside scope {outer}")
        return value

    def strings(value, label, allow_empty=False):
        ok = isinstance(value, list) and (allow_empty or bool(value))
        ok = ok and all(isinstance(x, str) and x.strip() for x in value)
        ok = ok and len(value) == len(set(value))
        return need(ok, f"{label}: unique nonempty strings required")

    def index(value, label):
        result = {}
        if not need(isinstance(value, list), f"{label}: list required"):
            return result
        for item in value:
            if not need(isinstance(item, dict), f"{label}: object entries required"):
                continue
            ident = item.get("id")
            if not need(isinstance(ident, str) and bool(ident.strip()), f"{label}: nonempty id required"):
                continue
            if need(ident not in result, f"{label}: duplicate id {ident}"):
                result[ident] = item
        return result

    def coverage(intervals, expected, label):
        if not expected:
            return
        pos = expected[0]
        for interval in sorted(intervals):
            need(interval[0] == pos, f"{label}: gap/overlap at frame {pos}, next starts {interval[0]}")
            pos = max(pos, interval[1])
        need(pos == expected[1], f"{label}: coverage ends {pos}, expected {expected[1]}")

    def verify_file(path_value, expected, label):
        if not need(isinstance(path_value, str) and bool(path_value), f"{label}: path required"):
            return
        path = Path(path_value)
        if not need(not path.is_absolute() and ".." not in path.parts,
                    f"{label}: project-relative path without .. required"):
            return
        if root is None:
            return
        resolved = (root / path).resolve()
        if not need(resolved.is_relative_to(root.resolve()), f"{label}: path/symlink escapes root"):
            return
        if need(resolved.is_file(), f"{label}: file missing {path_value}") and expected:
            need(digest(resolved) == expected, f"{label}: SHA256 mismatch")

    if not need(isinstance(data, dict), "contract: JSON object required"):
        return errors
    need(data.get("schema") == "pv-replication-contract-v1", "schema: unsupported/missing")
    source = data.get("source", {})
    if not isinstance(source, dict):
        source = {}
    for key in ("fps_num", "fps_den", "total_frames"):
        need(integer(source.get(key)) and source.get(key) > 0, f"source.{key}: positive integer required")
    total = source.get("total_frames")
    scope = span(data.get("interval"), "interval", [0, total] if integer(total) and total > 0 else None)
    need(bool(HASH.fullmatch(str(source.get("sha256", "")))), "source.sha256: lowercase 64-hex required")
    verify_file(source.get("path"), source.get("sha256"), "source")

    owners = index(data.get("owners"), "owners")
    regions = {}
    for ident, owner in owners.items():
        if strings(owner.get("regions"), f"owner {ident}.regions"):
            for region in owner["regions"]:
                need(region not in regions, f"owner: region {region} has multiple owners")
                regions[region] = ident
                if region.endswith((".head", ".face")):
                    need(owner.get("method") == "whole-head", f"owner {ident}: head must have whole-head owner")
                    need(owner.get("deformation") == "none", f"owner {ident}: face/head deformation prohibited")
        need(owner.get("mask") in MASKS, f"owner {ident}: explicit/semantic mask declaration required")
    assets = index(data.get("assets"), "assets")
    for ident, asset in assets.items():
        strings(asset.get("owners"), f"asset {ident}.owners")
        for owner in asset.get("owners", []) if isinstance(asset.get("owners"), list) else []:
            need(owner in owners, f"asset {ident}: unknown owner {owner}")
        need(bool(HASH.fullmatch(str(asset.get("sha256", "")))), f"asset {ident}: SHA256 required")
        verify_file(asset.get("path"), asset.get("sha256"), f"asset {ident}")
        need(isinstance(asset.get("object"), str) and bool(asset["object"]), f"asset {ident}: object required")
        need(isinstance(asset.get("geometry_lock"), str) and bool(asset["geometry_lock"].strip()),
             f"asset {ident}: geometry_lock declaration required")
        if stage == "delivery":
            need(asset.get("approved") is True, f"asset {ident}: not approved")

    events = index(data.get("source_events"), "source_events")
    event_spans = {}
    event_requirements = {}
    for ident, event in events.items():
        event_spans[ident] = span(event.get("interval"), f"event {ident}", scope)
        requirements = event.get("requirements")
        if not need(isinstance(requirements, list) and bool(requirements), f"event {ident}: requirements required"):
            requirements = []
        lookup = {}
        for req in requirements:
            if not need(isinstance(req, dict), f"event {ident}: requirement object required"):
                continue
            obj = req.get("object")
            if not need(isinstance(obj, str) and bool(obj), f"event {ident}: object required"):
                continue
            need(obj not in lookup, f"event {ident}: duplicate requirement for {obj}")
            lookup[obj] = req
            for field in ("pose", "expression"):
                need(isinstance(req.get(field), str) and bool(req[field].strip()), f"event {ident}/{obj}: {field} required")
            strings(req.get("motion_parts"), f"event {ident}/{obj}.motion_parts", allow_empty=True)
            strings(req.get("phases"), f"event {ident}/{obj}.phases")
        event_requirements[ident] = lookup
    need(bool(events), "source_events: at least one event required")

    states = index(data.get("states"), "states")
    order = data.get("expected_state_order")
    strings(order, "expected_state_order")
    need(list(states) == order, "states: state sequence differs from expected_state_order")
    spans, used_assets = [], set()
    event_coverage = {ident: [] for ident in events}
    for ident, state in states.items():
        st = span(state.get("interval"), f"state {ident}", scope)
        if st:
            spans.append(st)
        event_id = state.get("source_event_id")
        if not need(event_id in events, f"state {ident}: unknown source event {event_id}"):
            continue
        if st and event_spans[event_id]:
            need(event_spans[event_id][0] <= st[0] < st[1] <= event_spans[event_id][1],
                 f"state {ident}: outside its source event")
            event_coverage[event_id].append(st)
        drawings = state.get("drawings", [])
        if not need(isinstance(drawings, list) and bool(drawings), f"state {ident}: drawings required"):
            drawings = []
        cells, phases = {}, {}
        requirements = event_requirements[event_id]
        for cel in drawings:
            if not need(isinstance(cel, dict), f"state {ident}: drawing object required"):
                continue
            asset_id, obj = cel.get("asset_id"), cel.get("object")
            if not need(asset_id in assets, f"state {ident}: unknown drawing asset {asset_id}"):
                continue
            need(asset_id not in cells, f"state {ident}: duplicate drawing asset {asset_id}")
            cells[asset_id] = cel
            used_assets.add(asset_id)
            need(assets[asset_id].get("object") == obj, f"state {ident}/{asset_id}: object mismatch")
            if not need(obj in requirements, f"state {ident}/{asset_id}: no source requirement for object {obj}"):
                continue
            req = requirements[obj]
            for field in ("pose", "expression"):
                need(cel.get(field) == req.get(field), f"state {ident}/{asset_id}: missing/wrong {field}")
            motion = cel.get("motion_parts")
            if strings(motion, f"state {ident}/{asset_id}.motion_parts", allow_empty=True):
                need(set(req.get("motion_parts", [])) <= set(motion), f"state {ident}/{asset_id}: missing local motion parts")
            phase = cel.get("phase")
            need(phase in req.get("phases", []), f"state {ident}/{asset_id}: unexpected phase {phase}")
            phases.setdefault(obj, set()).add(phase)
        for obj, req in requirements.items():
            need(set(req.get("phases", [])) <= phases.get(obj, set()), f"state {ident}/{obj}: missing pose/phase drawing")
        schedule = state.get("schedule", [])
        if not need(isinstance(schedule, list) and bool(schedule), f"state {ident}: schedule required"):
            schedule = []
        scheduled = set()
        object_spans = {obj: [] for obj in requirements}
        for entry in schedule:
            if not need(isinstance(entry, dict), f"state {ident}: schedule entry object required"):
                continue
            cs = span(entry.get("interval"), f"state {ident} schedule", st)
            asset_id = entry.get("asset_id")
            if not need(asset_id in cells, f"state {ident}: schedule asset lacks drawing declaration"):
                continue
            scheduled.add(asset_id)
            obj = cells[asset_id].get("object")
            if cs and obj in object_spans:
                object_spans[obj].append(cs)
        need(set(cells) <= scheduled, f"state {ident}: declared drawing never scheduled")
        for obj, intervals in object_spans.items():
            coverage(intervals, st, f"state {ident}/{obj}")
    need(spans == sorted(spans), "states: intervals are not in chronological order")
    coverage(spans, scope, "states")
    for ident in events:
        coverage(event_coverage[ident], event_spans[ident], f"source event {ident}")
    need(set(assets) <= used_assets, "assets: unconsumed asset; remove reference-only candidates from adopted contract")

    layer_order = data.get("layer_order")
    strings(layer_order, "layer_order")
    need(layer_order == data.get("required_layer_order"), "layer_order: differs from declared contact/occlusion order")
    transitions = index(data.get("transitions", []), "transitions")
    for ident, tr in transitions.items():
        interval = span(tr.get("interval"), f"transition {ident}", scope)
        opaque = span(tr.get("opaque_interval"), f"transition {ident}.opaque_interval", interval)
        switch = tr.get("switch_frame")
        need(integer(switch) and opaque is not None and opaque[0] <= switch < opaque[1],
             f"transition {ident}: switch outside opaque interval")
        covers, changing = tr.get("covers"), tr.get("changing_regions")
        if strings(covers, f"transition {ident}.covers") and strings(changing, f"transition {ident}.changing_regions"):
            need(set(changing) <= set(covers), f"transition {ident}: uncovered changing region")
            need(set(changing) <= set(regions), f"transition {ident}: undeclared changing owner region")
        cels = tr.get("cels", [])
        if not need(isinstance(cels, list) and bool(cels), f"transition {ident}: effect cels required"):
            cels = []
        effect_spans = []
        for cel in cels:
            if not need(isinstance(cel, dict), f"transition {ident}: effect cel object required"):
                continue
            cs = span(cel.get("interval"), f"transition {ident} cel", interval)
            if cs:
                effect_spans.append(cs)
            need(cel.get("full_canvas") is True and cel.get("clip_to_actor") is False,
                 f"transition {ident}: effect clipped/not full canvas")
        need(effect_spans == sorted(effect_spans), f"transition {ident}: cels not in chronological order")
        coverage(effect_spans, interval, f"transition {ident} cels")
        expected = tr.get("expected_cel_durations")
        if need(isinstance(expected, list) and bool(expected)
                and all(integer(x) and x > 0 for x in expected),
                f"transition {ident}: measured expected_cel_durations required"):
            need([b-a for a, b in effect_spans] == expected,
                 f"transition {ident}: effect cel count/hold durations differ from source plan")

    if stage == "delivery":
        need(root is not None, "delivery: --root required to verify files and evidence")
        output = data.get("output", {})
        if not isinstance(output, dict):
            output = {}
        out_hash = output.get("sha256")
        need(bool(HASH.fullmatch(str(out_hash))), "output.sha256: required")
        verify_file(output.get("path"), out_hash, "output")
        reviews = data.get("reviews", [])
        if not isinstance(reviews, list):
            reviews = []
        for kind in ("original-speed", "half-speed", "independent"):
            candidates = [r for r in reviews if isinstance(r, dict) and r.get("kind") == kind]
            need(bool(candidates), f"review {kind}: missing")
            successful = []
            for review in candidates:
                rs = span(review.get("interval"), f"review {kind}", scope)
                need(review.get("result") == "pass", f"review {kind}: not pass")
                need(review.get("output_sha256") == out_hash, f"review {kind}: stale/wrong output hash")
                need(isinstance(review.get("reviewer"), str) and bool(review["reviewer"].strip()), f"review {kind}: reviewer missing")
                need(isinstance(review.get("observations"), list) and bool(review["observations"]), f"review {kind}: observations missing")
                verify_file(review.get("evidence_path"), None, f"review {kind} evidence")
                need(review.get("actual_playback") is True, f"review {kind}: no actual playback")
                if kind == "independent":
                    need(review.get("independent_of_author") is True, "review independent: not independent of author")
                    need(review.get("source_continuity_checked") is True,
                         "review independent: source continuity not checked")
                if rs:
                    successful.append(rs)
            # Records may overlap (e.g. two reviewers). Union coverage avoids counting repetitions as gaps.
            merged = []
            for rs in sorted(successful):
                if merged and rs[0] <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], rs[1])
                else:
                    merged.append(list(rs))
            coverage(merged, scope, f"review {kind}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("--stage", choices=("preflight", "delivery"), default="preflight")
    parser.add_argument("--root", type=Path, help="Verify project-relative paths, files and SHA256")
    args = parser.parse_args()
    try:
        data = json.loads(args.contract.read_text(encoding="utf-8"))
        errors = validate(data, args.stage, args.root)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "input_error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": not errors, "stage": args.stage, "errors": errors,
                      "visual_quality_verified": False,
                      "actual_playback_claims": "declarations plus evidence existence; not proof of watching"},
                     ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
