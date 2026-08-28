from __future__ import annotations

import unittest
from unittest.mock import patch

from app import window_layout


class WindowLayoutTests(unittest.TestCase):
    def test_crm_uses_left_half_of_work_area(self) -> None:
        with patch.object(
            window_layout,
            "primary_work_area",
            return_value=window_layout.WindowRect(x=10, y=20, width=1000, height=700),
        ):
            self.assertEqual(
                window_layout.half_screen_rect("crm"),
                window_layout.WindowRect(x=10, y=20, width=500, height=700),
            )

    def test_worker_uses_right_half_of_work_area(self) -> None:
        with patch.object(
            window_layout,
            "primary_work_area",
            return_value=window_layout.WindowRect(x=10, y=20, width=1001, height=700),
        ):
            self.assertEqual(
                window_layout.half_screen_rect("worker"),
                window_layout.WindowRect(x=510, y=20, width=501, height=700),
            )

    def test_desktop2_switch_moves_right_from_desktop1(self) -> None:
        shortcuts: list[str] = []
        with patch.object(window_layout, "virtual_desktop_state", return_value=(2, 1)):
            window_layout.switch_to_virtual_desktop_2(
                sleep=lambda _seconds: None,
                send_shortcut=shortcuts.append,
            )

        self.assertEqual(shortcuts, ["right"])

    def test_zoom_out_returns_false_when_target_window_is_missing(self) -> None:
        with patch.object(window_layout, "find_visible_window_by_title", return_value=0):
            self.assertFalse(window_layout.send_zoom_out_to_window("missing", steps=4))

    def test_minimize_window_returns_false_when_target_window_is_missing(self) -> None:
        with patch.object(window_layout, "find_visible_window_by_title", return_value=0):
            self.assertFalse(window_layout.minimize_window_by_title("missing"))

    def test_minimize_visible_titled_windows_skips_excluded_titles(self) -> None:
        titles = {
            101: "Background workbook",
            202: "CRM Work Record Watch",
            303: "",
        }

        def fake_enum(callback, _lparam):
            for hwnd in titles:
                callback(hwnd, 0)
            return True

        with (
            patch.object(window_layout.ctypes.windll.user32, "GetShellWindow", return_value=404),
            patch.object(window_layout.ctypes.windll.user32, "EnumWindows", side_effect=fake_enum),
            patch.object(window_layout.ctypes.windll.user32, "IsWindowVisible", return_value=True),
            patch.object(window_layout, "_window_title", side_effect=lambda hwnd: titles[int(hwnd)]),
            patch.object(window_layout.ctypes.windll.user32, "ShowWindow") as show_window,
        ):
            count = window_layout.minimize_visible_titled_windows(
                exclude_title_texts=("CRM Work Record Watch",)
            )

        self.assertEqual(count, 1)
        show_window.assert_called_once_with(101, 6)

    def test_console_move_can_require_visible_title_match(self) -> None:
        with patch.object(window_layout, "find_visible_window_by_title", return_value=0):
            with patch.object(window_layout.ctypes.windll.kernel32, "GetConsoleWindow", return_value=123) as get_console:
                self.assertFalse(
                    window_layout.move_console_to_half_screen(
                        "worker",
                        title_text="ARM Export CLI",
                        fallback_to_console_window=False,
                    )
                )

        get_console.assert_not_called()

    def test_crm_twinplay_browser_zoom_uses_verified_ratio_steps(self) -> None:
        with patch.object(window_layout, "send_zoom_out_to_window", return_value=True) as send_zoom:
            self.assertTrue(window_layout.send_crm_twinplay_browser_zoom_to_window("CRM"))

        send_zoom.assert_called_once_with(
            "CRM",
            steps=window_layout.CRM_TWINPLAY_BROWSER_ZOOM_OUT_STEPS,
            prefer_title_texts=window_layout.CRM_TWINPLAY_BROWSER_TITLE_PREFERENCES,
            exclude_title_texts=window_layout.CRM_TWINPLAY_BROWSER_TITLE_EXCLUSIONS,
            reset_first=True,
        )
        self.assertEqual(window_layout.CRM_TWINPLAY_BROWSER_ZOOM_PERCENT, 50.0)

    def test_generic_twinplay_browser_zoom_uses_verified_ratio_steps(self) -> None:
        with patch.object(window_layout, "send_zoom_out_to_window", return_value=True) as send_zoom:
            self.assertTrue(window_layout.send_twinplay_browser_zoom_to_window("ARM"))

        send_zoom.assert_called_once_with(
            "ARM",
            steps=window_layout.TWINPLAY_BROWSER_ZOOM_OUT_STEPS,
            prefer_title_texts=window_layout.TWINPLAY_BROWSER_TITLE_PREFERENCES,
            exclude_title_texts=window_layout.TWINPLAY_BROWSER_TITLE_EXCLUSIONS,
            reset_first=True,
        )
        self.assertEqual(window_layout.TWINPLAY_BROWSER_ZOOM_PERCENT, 50.0)


if __name__ == "__main__":
    unittest.main()
