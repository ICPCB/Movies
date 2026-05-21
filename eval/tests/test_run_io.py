import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from eval.tests import conftest as _conftest
from eval.scripts import _run_io


class RunIOTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self._tmp.name)
        self.old_project_root = _run_io.PROJECT_ROOT
        self.old_eval_dir = _run_io.EVAL_DIR
        self.old_runs_dir = _run_io.RUNS_DIR
        _run_io.PROJECT_ROOT = self.project_root
        _run_io.EVAL_DIR = self.project_root / "eval"
        _run_io.RUNS_DIR = _run_io.EVAL_DIR / "runs"

    def tearDown(self):
        _run_io.PROJECT_ROOT = self.old_project_root
        _run_io.EVAL_DIR = self.old_eval_dir
        _run_io.RUNS_DIR = self.old_runs_dir
        self._tmp.cleanup()

    def test_new_run_id_uses_utc_minute_precision(self):
        now = datetime(2026, 5, 19, 15, 30, 42, 123456, tzinfo=timezone.utc)
        self.assertEqual(_run_io.new_run_id(now=now), "2026-05-19-1530-nogit")
        self.assertRegex(_run_io.new_run_id(now=now), r"^\d{4}-\d{2}-\d{2}-\d{4}-nogit$")

    def test_new_run_id_converts_aware_datetime_to_utc(self):
        tz_plus_7 = timezone(timedelta(hours=7))
        now = datetime(2026, 5, 19, 22, 30, 0, tzinfo=tz_plus_7)
        self.assertEqual(_run_io.new_run_id(now=now), "2026-05-19-1530-nogit")

    def test_run_dir_is_absolute_and_cwd_independent(self):
        run_id = "2026-05-19-1530-nogit"
        child = self.project_root / "other"
        child.mkdir()
        old_cwd = Path.cwd()
        try:
            os.chdir(child)
            path = _run_io.run_dir(run_id)
        finally:
            os.chdir(old_cwd)
        self.assertTrue(path.is_absolute())
        self.assertEqual(path.name, run_id)
        self.assertEqual(path.parent, _run_io.RUNS_DIR)

    def test_ensure_run_dir_is_idempotent(self):
        run_id = "2026-05-19-1530-nogit"
        first = _run_io.ensure_run_dir(run_id)
        second = _run_io.ensure_run_dir(run_id)
        self.assertEqual(first, second)
        self.assertTrue(first.is_dir())

    def test_write_manifest_records_no_git_fields_and_extras(self):
        run_id = "2026-05-19-1530-nogit"
        manifest = _run_io.write_manifest(
            run_id,
            rng_seed=7,
            extras={"extra_note": "ok", "timestamps": {"candidates_done": "later"}},
        )
        path = _run_io.run_dir(run_id) / "run_manifest.json"
        with open(path, "r", encoding="utf-8") as handle:
            on_disk = json.load(handle)
        self.assertEqual(on_disk, manifest)
        self.assertIsNone(manifest["git_sha"])
        self.assertIsNone(manifest["git_dirty"])
        self.assertEqual(manifest["git_mode"], "no_git")
        self.assertEqual(manifest["rng_seed"], 7)
        self.assertEqual(manifest["extra_note"], "ok")
        self.assertEqual(manifest["timestamps"]["candidates_done"], "later")
        self.assertRegex(manifest["timestamps"]["start"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_append_warning_and_update_timestamp_modify_manifest(self):
        run_id = "2026-05-19-1530-nogit"
        _run_io.write_manifest(run_id)
        warned = _run_io.append_warning(run_id, "dedup_bug: sample")
        self.assertEqual(warned["warnings"], ["dedup_bug: sample"])
        stamped = _run_io.update_timestamp(run_id, "silver_done")
        self.assertRegex(stamped["timestamps"]["silver_done"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_snapshot_config_coerces_path_and_skips_bad_values(self):
        from src import config

        config.TEST_EVAL_PATH = Path("data/example")
        config.TEST_EVAL_BAD = object()
        config.TEST_EVAL_CALLABLE = lambda: None
        try:
            snapshot = _run_io.snapshot_config()
        finally:
            delattr(config, "TEST_EVAL_PATH")
            delattr(config, "TEST_EVAL_BAD")
            delattr(config, "TEST_EVAL_CALLABLE")
        self.assertEqual(snapshot["TEST_EVAL_PATH"], "data\\example" if os.name == "nt" else "data/example")
        self.assertNotIn("TEST_EVAL_CALLABLE", snapshot)
        self.assertTrue(any(item.startswith("TEST_EVAL_BAD:") for item in snapshot["_skipped"]))

    def test_write_config_snapshot_and_latest_run(self):
        first = "2026-05-19-1530-nogit"
        second = "2026-05-19-1531-nogit"
        _run_io.ensure_run_dir(first)
        _run_io.ensure_run_dir(second)
        snapshot = _run_io.write_config_snapshot(second)
        path = _run_io.run_dir(second) / "config_snapshot.json"
        with open(path, "r", encoding="utf-8") as handle:
            on_disk = json.load(handle)
        self.assertEqual(on_disk, snapshot)
        self.assertEqual(_run_io.latest_run(), second)

    def test_latest_run_prefers_current_run_pointer(self):
        _run_io.ensure_run_dir("2026-05-19-1530-nogit")
        pointer = _run_io.RUNS_DIR / "current_run.txt"
        pointer.write_text("2026-05-19-1200-nogit\n", encoding="utf-8")
        self.assertEqual(_run_io.latest_run(), "2026-05-19-1200-nogit")

    def test_latest_run_ignores_non_canonical_dirs(self):
        timestamped = "2026-05-19-1846-nogit"
        _run_io.ensure_run_dir(timestamped)
        (_run_io.RUNS_DIR / "cx03-smoke-debug").mkdir(parents=True)
        self.assertEqual(_run_io.latest_run(), timestamped)

    def test_latest_run_picks_newest_timestamped_dir(self):
        first = "2026-05-19-1530-nogit"
        second = "2026-05-19-1531-nogit"
        _run_io.ensure_run_dir(first)
        _run_io.ensure_run_dir(second)
        self.assertEqual(_run_io.latest_run(), second)

    def test_latest_run_raises_when_no_canonical_dirs(self):
        (_run_io.RUNS_DIR / "cx03-smoke-debug").mkdir(parents=True)
        expected = (
            "no canonical eval runs found in eval/runs/ "
            "(expected directory names like YYYY-MM-DD-HHMM-*)"
        )
        with self.assertRaisesRegex(FileNotFoundError, re.escape(expected)):
            _run_io.latest_run()


if __name__ == "__main__":
    unittest.main()
