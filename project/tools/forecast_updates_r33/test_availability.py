"""P2 regression: source availability must be checked at the run's own clock."""
import copy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest

from tools.forecast_updates_r33 import workflow as w
from tools.forecast_updates_r33.test_workflow import adapter, NOW, CLOCK, OLD, TARGET


class AvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.bundle=self.root/"bundle"
        self.bundle.mkdir()
        self.calls=0

    def prepared(self, snapshot=None, manual=None):
        provenance={"prepared_at":NOW.isoformat(),"as_of":CLOCK,"target":TARGET,
                    "feature_function":"unchanged cz_struct.assemble_feature_frames",
                    "snapshot":{"completed_at":snapshot or (NOW-timedelta(seconds=120)).isoformat()},
                    "manual_rows":[{"series":"core","observation_month":TARGET,"value":.3,
                                    "units":"mm_pct","source":"official unit-test evidence",
                                    "available_from":manual or (NOW-timedelta(seconds=120)).isoformat()}]}
        raw=w.encoded(provenance)
        (self.bundle/"provenance.json").write_bytes(raw)
        (self.bundle/"MANIFEST.json").write_bytes(w.encoded({"files":{"provenance.json":w.sha(raw)}}))

    def record(self, as_of=CLOCK, mode="prospective"):
        def invoke(*args, **kw):
            self.calls+=1
            report=adapter(as_of=as_of)
            report["provenance"]["bundle_manifest_sha256"]=w.sha((self.bundle/"MANIFEST.json").read_bytes())
            return report
        return w.record(self.bundle,TARGET,as_of,mode,store=self.root/"archive",invoke=invoke)

    def reseal(self, folder):
        manifest=w.read_json(folder/"MANIFEST.json")
        manifest["files"]={name:w.sha((folder/name).read_bytes()) for name in manifest["files"]}
        (folder/"MANIFEST.json").write_bytes(w.encoded(manifest))

    def earlier_clock(self, folder):
        for name in ("request.json","result.json","adapter.json"):
            data=w.read_json(folder/name)
            data["as_of"]=OLD
            if name=="adapter.json":
                data["forecast"]["as_of"]=OLD
            (folder/name).write_bytes(w.encoded(data))
        self.reseal(folder)

    def legacy(self, folder):
        inputs=w.read_json(folder/"inputs.json")
        inputs.pop("bundle_evidence_version",None)
        (folder/"inputs.json").write_bytes(w.encoded(inputs))
        manifest=w.read_json(folder/"MANIFEST.json")
        for name in ("bundle_manifest.json","bundle_provenance.json"):
            manifest["files"].pop(name,None)
            (folder/name).unlink(missing_ok=True)
        (folder/"MANIFEST.json").write_bytes(w.encoded(manifest))
        self.reseal(folder)

    def test_later_manual_within_fresh_clock_window_blocks_before_invoke_preserves_pointer(self):
        self.prepared()
        good=self.record(as_of=OLD)
        self.assertEqual("successful",good["status"])
        pointer=self.root/"archive/latest_successful.json"
        before=pointer.read_bytes()
        self.prepared(manual=(NOW-timedelta(seconds=10)).isoformat())
        bad=self.record()
        self.assertEqual("blocked",bad["status"])
        self.assertIn("manual availability",bad["reason"])
        self.assertEqual(1,self.calls)
        self.assertEqual(before,pointer.read_bytes())

    def test_later_snapshot_completion_blocks_before_invoke(self):
        self.prepared(snapshot=(NOW-timedelta(seconds=10)).isoformat())
        bad=self.record()
        self.assertEqual("blocked",bad["status"])
        self.assertIn("snapshot completion",bad["reason"])
        self.assertEqual(0,self.calls)

    def test_archive_reload_rechecks_manual_at_earlier_run_clock(self):
        self.prepared(manual=(NOW-timedelta(seconds=45)).isoformat())
        folder=Path(self.record()["run_directory"])
        self.earlier_clock(folder)
        with self.assertRaisesRegex(ValueError,"manual availability"):
            w.load_run(folder)

    def test_archive_reload_rechecks_snapshot_at_earlier_run_clock(self):
        self.prepared(snapshot=(NOW-timedelta(seconds=45)).isoformat())
        folder=Path(self.record()["run_directory"])
        self.earlier_clock(folder)
        with self.assertRaisesRegex(ValueError,"snapshot completion"):
            w.load_run(folder)

    def test_new_archive_keeps_hash_bound_provenance_without_original_bundle(self):
        self.prepared()
        folder=Path(self.record()["run_directory"])
        self.assertTrue((folder/"bundle_manifest.json").is_file())
        self.assertTrue((folder/"bundle_provenance.json").is_file())
        (self.bundle/"MANIFEST.json").unlink()
        (self.bundle/"provenance.json").unlink()
        self.assertEqual("successful",w.load_run(folder)["status"])

    def test_legacy_prospective_archive_uses_pinned_bundle_and_rechecks_clock(self):
        self.prepared(manual=(NOW-timedelta(seconds=45)).isoformat())
        folder=Path(self.record()["run_directory"])
        self.legacy(folder)
        self.assertEqual("successful",w.load_run(folder)["status"])
        self.earlier_clock(folder)
        with self.assertRaisesRegex(ValueError,"manual availability"):
            w.load_run(folder)

    def test_unverified_provenance_cannot_enter_a_run(self):
        self.prepared()
        p=self.bundle/"provenance.json"
        p.write_bytes(p.read_bytes()+b" ")
        bad=self.record()
        self.assertEqual("blocked",bad["status"])
        self.assertIn("hash",bad["reason"])
        self.assertEqual(0,self.calls)

    def test_replay_keeps_explicit_latest_vintage_policy(self):
        self.prepared(snapshot=CLOCK,manual=CLOCK)
        result=self.record(as_of=OLD,mode="replay")
        self.assertEqual("successful",result["status"])
        self.assertEqual("replay",w.load_run(result["run_directory"])["mode"])

    def test_existing_september_record_remains_byte_exact_and_valid(self):
        folder=w.OUTPUT/"runs/20260922T175001527361Z_7c5389d7016a"
        before={p.relative_to(folder).as_posix():w.sha(p.read_bytes())
                for p in folder.rglob("*") if p.is_file()}
        result=w.load_run(folder)
        self.assertEqual(-0.2042311894134946,result["forecast"]["point"])
        self.assertEqual("875bfacfa4355febadfbe80423967d84b651227e9efc264ed8397653e3dea782",result["model_identity"])
        self.assertEqual(before,{p.relative_to(folder).as_posix():w.sha(p.read_bytes())
                                 for p in folder.rglob("*") if p.is_file()})


if __name__=="__main__":
    unittest.main()
