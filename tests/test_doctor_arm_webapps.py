import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import doctor_arm_webapps as doctor


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", json_error=False):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("invalid json")
        return self._json_data


class FakeSession:
    def __init__(self, *, get_response=None, post_response=None):
        self.get_response = get_response
        self.post_response = post_response

    def get(self, url, timeout):
        return self.get_response

    def post(self, url, data, headers, timeout):
        return self.post_response


class DoctorArmWebappsTest(unittest.TestCase):
    def test_import_check_passes_on_expected_health_json(self):
        response = FakeResponse(
            status_code=200,
            json_data={
                "ok": True,
                "message": doctor.IMPORT_HEALTH_MESSAGE,
                "capabilities": [doctor.IMPORT_CAPABILITY],
            },
        )
        with mock.patch.dict(os.environ, {"ARM_IMPORT_WEBAPP_URL": "https://import.example/exec"}, clear=False):
            result = doctor.check_import_webapp(session=FakeSession(get_response=response))

        self.assertTrue(result.ok)
        self.assertEqual(result.classification, "ok")

    def test_import_check_fails_on_google_html_403(self):
        response = FakeResponse(status_code=403, text="<html><title>存取遭拒</title></html>", json_error=True)
        with mock.patch.dict(os.environ, {"ARM_IMPORT_WEBAPP_URL": "https://import.example/exec"}, clear=False):
            result = doctor.check_import_webapp(session=FakeSession(get_response=response))

        self.assertFalse(result.ok)
        self.assertEqual(result.classification, "http_403_html")

    def test_import_check_fails_on_wrong_json_payload(self):
        response = FakeResponse(status_code=200, json_data={"ok": True, "message": "wrong"})
        with mock.patch.dict(os.environ, {"ARM_IMPORT_WEBAPP_URL": "https://import.example/exec"}, clear=False):
            result = doctor.check_import_webapp(session=FakeSession(get_response=response))

        self.assertFalse(result.ok)
        self.assertEqual(result.classification, "wrong_health_message")

    def test_import_check_requires_declared_capability(self):
        response = FakeResponse(
            status_code=200,
            json_data={"ok": True, "message": doctor.IMPORT_HEALTH_MESSAGE},
        )
        with mock.patch.dict(os.environ, {"ARM_IMPORT_WEBAPP_URL": "https://import.example/exec"}, clear=False):
            result = doctor.check_import_webapp(session=FakeSession(get_response=response))

        self.assertFalse(result.ok)
        self.assertEqual(result.classification, "missing_import_capability")

    def test_remmiter_check_passes_on_ok_true(self):
        response = FakeResponse(status_code=200, json_data={"ok": True, "result": {"items": []}})
        with mock.patch.dict(
            os.environ,
            {
                "ARM_REMMITER_WEBAPP_URL": "https://remmiter.example/exec",
                "ARM_WEBAPP_TOKEN": "secret",
            },
            clear=False,
        ):
            result = doctor.check_remmiter_webapp(session=FakeSession(post_response=response))

        self.assertTrue(result.ok)
        self.assertEqual(result.classification, "ok")

    def test_remmiter_check_flags_import_only_contract(self):
        response = FakeResponse(
            status_code=200,
            json_data={"ok": False, "error": "payload.rows must be a non-empty 2D array."},
        )
        with mock.patch.dict(
            os.environ,
            {
                "ARM_REMMITER_WEBAPP_URL": "https://remmiter.example/exec",
                "ARM_WEBAPP_TOKEN": "secret",
            },
            clear=False,
        ):
            result = doctor.check_remmiter_webapp(session=FakeSession(post_response=response))

        self.assertFalse(result.ok)
        self.assertEqual(result.classification, "wrong_contract_import_endpoint")

    def test_missing_env_var_is_reported_clearly(self):
        with mock.patch.dict(
            os.environ,
            {
                "ARM_IMPORT_WEBAPP_URL": "",
                "ARM_WEBAPP_URL": "",
            },
            clear=False,
        ):
            result = doctor.check_import_webapp(session=FakeSession())

        self.assertFalse(result.ok)
        self.assertEqual(result.classification, "missing_url")
        self.assertIn("ARM_IMPORT_WEBAPP_URL", result.detail)

    def test_arm_output_run_cmd_warns_and_continues_after_doctor_failure(self):
        repo_root = Path(__file__).resolve().parents[1]
        run_cmd = repo_root / "automations" / "10_ARM_Output" / "run.cmd"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            doctor_script = temp_path / "fake_doctor.py"
            main_script = temp_path / "fake_main.py"
            doctor_script.write_text("print('doctor fail')\nraise SystemExit(1)\n", encoding="utf-8")
            main_script.write_text("print('main ran')\nraise SystemExit(0)\n", encoding="utf-8")

            env = os.environ.copy()
            env["ARM_DOCTOR_SCRIPT"] = str(doctor_script)
            env["ARM_IMPORT_SCRIPT"] = str(main_script)
            env["ARM_POST_RUN_SLEEP_SECONDS"] = "0"

            result = subprocess.run(
                ["cmd.exe", "/c", str(run_cmd)],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

        combined_output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0)
        self.assertIn("[WARN] ARM import preflight failed; continuing with live ARM output.", combined_output)
        self.assertIn("main ran", combined_output)


if __name__ == "__main__":
    unittest.main()
