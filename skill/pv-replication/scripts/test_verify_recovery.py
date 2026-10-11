import copy
import tempfile
import unittest
from pathlib import Path
from verify_recovery import sha, verify


class RecoveryInventoryFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ("base.mp4", "f2.png", "f3.png", "f7.png"):
            (self.root/name).write_bytes(("synthetic " + name).encode())
        def record(name):
            return {"path": name, "sha256": sha(self.root/name)}
        self.manifest = {"schema": "pv-minimal-recovery-v1", "base": record("base.mp4"),
            "media": {"fps_num": 30000, "fps_den": 1001, "width": 64, "height": 64, "total_frames": 10},
            "patch_sets": [{"id":"C", "interval":[2,4], "frames":[{"frame":n, **record(f"f{n}.png")} for n in (2,3)]},
                           {"id":"R3", "interval":[7,8], "frames":[{"frame":7, **record("f7.png")}]}]}

    def tearDown(self):
        self.temp.cleanup()

    def errors(self):
        return verify(self.manifest,self.root)["errors"]

    def test_complete(self):
        result = verify(self.manifest,self.root)
        self.assertTrue(result["ok"],result)
        self.assertEqual(result["hashed_files"],4)
        self.assertEqual(result["declared_patch_frames"],3)
        self.assertFalse(result["restoration_executed"])
        self.assertFalse(result["media_parameters_probed"])

    def test_missing_frame(self):
        self.manifest["patch_sets"][0]["frames"].pop()
        self.assertTrue(any("missing/duplicate" in x for x in self.errors()))

    def test_hash_changed(self):
        (self.root/"f3.png").write_bytes(b"changed")
        self.assertTrue(any("hash mismatch" in x for x in self.errors()))

    def test_conflicting_sets(self):
        duplicate=copy.deepcopy(self.manifest["patch_sets"][0]);duplicate["id"]="conflict"
        self.manifest["patch_sets"].append(duplicate)
        self.assertTrue(any("overlapping" in x for x in self.errors()))

    def test_float_frame(self):
        self.manifest["patch_sets"][0]["frames"][0]["frame"]=2.0
        self.assertTrue(any("integer frame" in x for x in self.errors()))

    def test_path_escape(self):
        self.manifest["base"]["path"]="../base.mp4"
        self.assertTrue(any("safe relative" in x for x in self.errors()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
