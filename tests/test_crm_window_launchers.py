from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CrmWindowLauncherTests(unittest.TestCase):
    def test_ai_worker_today_switches_desktop_before_starting_core_worker(self) -> None:
        launcher = (ROOT / "scripts" / "AI_worker_record today.bat").read_text(encoding="utf-8")
        core = (ROOT / "scripts" / "AI_worker_record today_core.bat").read_text(encoding="utf-8")

        self.assertIn("scripts\\window_layout.py", launcher)
        self.assertIn("--desktop2 --role worker", launcher)
        self.assertIn("--minimize-active-windows", launcher)
        self.assertIn('"AI_worker_record today_core.bat" %*', launcher.replace("%CD%\\scripts\\", ""))
        self.assertIn("AI_worker_record launcher", launcher)
        self.assertIn("--minimize-window", launcher)
        self.assertIn("--role worker --console", core)
        self.assertIn("--minimize-active-windows", core)
        self.assertNotIn("--zoom-out-steps", core)
        self.assertIn('"crm_work_record_lookup.py" %*', core.replace("%CD%\\scripts\\", ""))
        self.assertIn("set MAIN_EXIT=%ERRORLEVEL%", core)
        self.assertIn("exit /b %MAIN_EXIT%", core)

    def test_lookup_launcher_switches_desktop_before_starting_core_worker(self) -> None:
        launcher = (ROOT / "scripts" / "crm_work_record_lookup.bat").read_text(encoding="utf-8")
        core = (ROOT / "scripts" / "crm_work_record_lookup_core.bat").read_text(encoding="utf-8")

        self.assertIn("--desktop2 --role worker", launcher)
        self.assertIn("--minimize-active-windows", launcher)
        self.assertIn('"crm_work_record_lookup_core.bat" %*', launcher.replace("%CD%\\scripts\\", ""))
        self.assertIn("AI_worker_record launcher", launcher)
        self.assertIn("--minimize-window", launcher)
        self.assertIn("--role worker --console", core)
        self.assertIn("--minimize-active-windows", core)
        self.assertNotIn("--zoom-out-steps", core)
        self.assertIn('"crm_work_record_lookup.py" %*', core.replace("%CD%\\scripts\\", ""))
        self.assertIn("set MAIN_EXIT=%ERRORLEVEL%", core)
        self.assertIn("exit /b %MAIN_EXIT%", core)

    def test_crm_browser_placement_is_reapplied_after_startup_steps(self) -> None:
        lookup = (ROOT / "scripts" / "crm_work_record_lookup.py").read_text(encoding="utf-8")

        self.assertIn("def place_driver_window", lookup)
        self.assertGreaterEqual(lookup.count("place_driver_window(driver)"), 5)


if __name__ == "__main__":
    unittest.main()
