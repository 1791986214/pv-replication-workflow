#!/usr/bin/env python3
"""Behavioral fixtures: do not use the bundled draft as a passed delivery."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from validate_contract import digest, validate


def example(root):
    for name in ("source.mp4", "cel-A.png", "cel-B.png", "output.mp4", "playback.json"):
        (root / name).write_bytes(("synthetic fixture " + name).encode())
    # File contents are deliberately synthetic. This checker does not decode media.
    assets = [{"id": f"actor-{phase}", "path": f"cel-{phase}.png", "sha256": digest(root / f"cel-{phase}.png"),
               "object": "actor", "owners": ["actor"], "approved": True,
               "geometry_lock": "shared knees/ankles/shoe-tip anchors and whole-head transform"}
              for phase in ("A", "B")]
    requirement = {"object": "actor", "pose": "hold-cup", "expression": "worried-closed-mouth",
                   "motion_parts": ["hair", "sleeve"], "phases": ["A", "B"]}
    events, states = [], []
    for name, first, last in (("before", 0, 12), ("effect", 12, 36)):
        events.append({"id": name, "interval": [first, last], "requirements": [copy.deepcopy(requirement)]})
        states.append({"id": name, "interval": [first, last], "source_event_id": name,
                       "drawings": [{"asset_id": f"actor-{phase}", "phase": phase, **{k: v for k, v in requirement.items() if k != "phases"}}
                                    for phase in ("A", "B")],
                       "schedule": [{"interval": [n, n + 6], "asset_id": f"actor-{'A' if (n-first)//6%2 == 0 else 'B'}"}
                                    for n in range(first, last, 6)]})
    return {"schema": "pv-replication-contract-v1",
            "source": {"path": "source.mp4", "sha256": digest(root / "source.mp4"), "fps_num": 24, "fps_den": 1, "total_frames": 36},
            "interval": [0, 36], "owners": [{"id": "actor", "regions": ["actor.head", "actor.body"],
                "method": "whole-head", "deformation": "none", "mask": "explicit-alpha"}],
            "assets": assets, "source_events": events, "states": states,
            "expected_state_order": ["before", "effect"],
            "layer_order": ["background", "actor", "smoke", "lyrics"],
            "required_layer_order": ["background", "actor", "smoke", "lyrics"],
            "transitions": [{"id": "recover", "interval": [12, 36], "switch_frame": 24,
                "opaque_interval": [24, 30], "expected_cel_durations": [6, 6, 6, 6], "covers": ["actor.head", "actor.body"],
                "changing_regions": ["actor.head", "actor.body"],
                "cels": [{"interval": [n, n+6], "full_canvas": True, "clip_to_actor": False}
                         for n in range(12, 36, 6)]}],
            "output": {"path": "output.mp4", "sha256": digest(root / "output.mp4")},
            "reviews": [{"kind": kind, "interval": [0, 36], "actual_playback": True,
                "independent_of_author": kind == "independent", "source_continuity_checked": True, "reviewer": kind+" reviewer",
                "result": "pass", "evidence_path": "playback.json", "output_sha256": digest(root / "output.mp4"),
                "observations": ["Fixture declarations only; these bytes are not a real PV."]}
                for kind in ("original-speed", "half-speed", "independent")]}


class ContractFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = example(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def rejected(self, fragment):
        errors = validate(self.data, "delivery", self.root)
        self.assertTrue(any(fragment in error for error in errors), errors)

    def test_complete_fixture(self):
        self.assertEqual(validate(self.data, "delivery", self.root), [])

    def test_missing_pose_drawing(self):
        self.data["states"][0]["drawings"].pop()
        self.rejected("missing pose/phase drawing")

    def test_wrong_expression(self):
        self.data["states"][0]["drawings"][0]["expression"] = "smile"
        self.rejected("missing/wrong expression")

    def test_missing_local_motion(self):
        self.data["states"][0]["drawings"][0]["motion_parts"] = ["hair"]
        self.rejected("missing local motion")

    def test_schedule_gap(self):
        self.data["states"][0]["schedule"][0]["interval"][1] = 5
        self.rejected("gap/overlap")

    def test_scope_boundary_overrun(self):
        self.data["states"][1]["interval"][1] = 37
        self.rejected("outside scope")

    def test_state_order(self):
        self.data["states"].reverse()
        self.rejected("state sequence")

    def test_uncovered_source_event(self):
        event = copy.deepcopy(self.data["source_events"][0])
        event["id"] = "missing-event"
        self.data["source_events"].append(event)
        self.rejected("source event missing-event")

    def test_unconsumed_target_drawing(self):
        asset = copy.deepcopy(self.data["assets"][0])
        asset["id"] = "orphan"
        self.data["assets"].append(asset)
        self.rejected("unconsumed asset")

    def test_owner_missing(self):
        self.data["owners"] = []
        self.rejected("unknown owner")

    def test_multiple_region_owners(self):
        duplicate = copy.deepcopy(self.data["owners"][0])
        duplicate["id"] = "old-face"
        self.data["owners"].append(duplicate)
        self.rejected("multiple owners")

    def test_face_optical_flow(self):
        self.data["owners"][0]["deformation"] = "optical-flow"
        self.rejected("deformation prohibited")

    def test_color_is_not_semantic_owner(self):
        self.data["owners"][0]["mask"] = "largest-component"
        self.rejected("semantic mask declaration")

    def test_switch_exposed(self):
        self.data["transitions"][0]["switch_frame"] = 23
        self.rejected("switch outside opaque")

    def test_effect_rectangular_crop(self):
        self.data["transitions"][0]["cels"][2]["clip_to_actor"] = True
        self.rejected("clipped/not full canvas")

    def test_effect_count_and_holds(self):
        self.data["transitions"][0]["cels"][0]["interval"][1] = 17
        self.data["transitions"][0]["cels"][1]["interval"][0] = 17
        self.rejected("effect cel count/hold durations")

    def test_effect_cel_order(self):
        self.data["transitions"][0]["cels"].reverse()
        self.rejected("cels not in chronological order")

    def test_state_chronology_not_just_label_order(self):
        self.data["states"].reverse()
        self.data["expected_state_order"].reverse()
        self.rejected("intervals are not in chronological order")

    def test_effect_missing_changing_region(self):
        self.data["transitions"][0]["covers"].pop()
        self.rejected("uncovered changing region")

    def test_playback_not_done(self):
        self.data["reviews"][1]["actual_playback"] = False
        self.rejected("no actual playback")

    def test_independent_static_only(self):
        self.data["reviews"][2]["actual_playback"] = False
        self.rejected("review independent: no actual playback")

    def test_independent_source_continuity_missing(self):
        self.data["reviews"][2]["source_continuity_checked"] = False
        self.rejected("source continuity not checked")

    def test_stale_review(self):
        self.data["reviews"][0]["output_sha256"] = "0" * 64
        self.rejected("stale/wrong output hash")

    def test_review_partial_only(self):
        self.data["reviews"][0]["interval"] = [0, 35]
        self.rejected("review original-speed: coverage")

    def test_review_evidence_missing(self):
        (self.root / "playback.json").unlink()
        self.rejected("evidence: file missing")

    def test_asset_changed_after_review(self):
        (self.root / "cel-A.png").write_bytes(b"mutated")
        self.rejected("SHA256 mismatch")

    def test_path_traversal(self):
        self.data["assets"][0]["path"] = "../cel-A.png"
        self.rejected("project-relative path")

    def test_delivery_needs_root(self):
        self.assertIn("delivery: --root required to verify files and evidence", validate(self.data, "delivery"))

    def test_different_frame_rate_supported(self):
        self.data["source"]["fps_num"], self.data["source"]["fps_den"] = 30000, 1001
        self.assertEqual(validate(self.data, "delivery", self.root), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
