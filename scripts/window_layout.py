from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.window_layout import (
    half_screen_rect,
    minimize_visible_titled_windows,
    minimize_window_by_title,
    move_console_to_half_screen,
    send_zoom_out_to_window,
    switch_to_virtual_desktop_2,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Arrange CRM automation windows on the active desktop.")
    parser.add_argument("--role", choices=["crm", "browser", "left", "worker", "console", "right"], required=True)
    parser.add_argument("--console", action="store_true", help="Move this process console window.")
    parser.add_argument("--desktop2", action="store_true", help="Switch to Windows virtual desktop 2 first.")
    parser.add_argument("--json", action="store_true", help="Print the target rectangle as JSON.")
    parser.add_argument("--window-title", default="", help="Prefer moving a visible top-level window with this title.")
    parser.add_argument("--wait-seconds", type=float, default=0.0, help="Wait before moving the window.")
    parser.add_argument(
        "--minimize-active-windows",
        action="store_true",
        help="Minimize visible desktop windows before placing the target window.",
    )
    parser.add_argument("--minimize-window", action="store_true", help="Minimize the window-title target.")
    parser.add_argument(
        "--zoom-out-steps",
        type=int,
        default=0,
        help="Send Ctrl+Minus this many times to the window-title target.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.desktop2:
        switch_to_virtual_desktop_2()
    if args.wait_seconds > 0:
        import time

        time.sleep(args.wait_seconds)
    if args.minimize_active_windows:
        minimize_visible_titled_windows()
    rect = half_screen_rect(args.role)
    if args.console:
        move_console_to_half_screen(args.role, title_text=args.window_title)
    if args.window_title and args.zoom_out_steps > 0:
        send_zoom_out_to_window(args.window_title, steps=args.zoom_out_steps)
    if args.window_title and args.minimize_window:
        minimize_window_by_title(args.window_title)
    if args.json:
        print(json.dumps(rect.__dict__), flush=True)


if __name__ == "__main__":
    main()
