from __future__ import annotations

import ctypes
import time
import winreg
from dataclasses import dataclass
from typing import Callable

TWINPLAY_BROWSER_ZOOM_PERCENT = 50.0
TWINPLAY_BROWSER_ZOOM_OUT_STEPS = 5
TWINPLAY_BROWSER_TITLE_PREFERENCES = ("設定檔", "Profile")
TWINPLAY_BROWSER_TITLE_EXCLUSIONS = ("個人", "Personal")
CRM_TWINPLAY_BROWSER_ZOOM_PERCENT = TWINPLAY_BROWSER_ZOOM_PERCENT
CRM_TWINPLAY_BROWSER_ZOOM_OUT_STEPS = TWINPLAY_BROWSER_ZOOM_OUT_STEPS
CRM_TWINPLAY_BROWSER_TITLE_PREFERENCES = TWINPLAY_BROWSER_TITLE_PREFERENCES
CRM_TWINPLAY_BROWSER_TITLE_EXCLUSIONS = TWINPLAY_BROWSER_TITLE_EXCLUSIONS


@dataclass(frozen=True)
class WindowRect:
    x: int
    y: int
    width: int
    height: int


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def primary_work_area() -> WindowRect:
    rect = _RECT()
    if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
        return WindowRect(
            x=int(rect.left),
            y=int(rect.top),
            width=max(1, int(rect.right - rect.left)),
            height=max(1, int(rect.bottom - rect.top)),
        )
    width = int(ctypes.windll.user32.GetSystemMetrics(0))
    height = int(ctypes.windll.user32.GetSystemMetrics(1))
    return WindowRect(x=0, y=0, width=max(1, width), height=max(1, height))


def half_screen_rect(role: str) -> WindowRect:
    area = primary_work_area()
    half_width = max(1, area.width // 2)
    normalized = role.strip().casefold()
    if normalized in {"worker", "console", "right"}:
        return WindowRect(
            x=area.x + half_width,
            y=area.y,
            width=max(1, area.width - half_width),
            height=area.height,
        )
    if normalized in {"crm", "browser", "left"}:
        return WindowRect(x=area.x, y=area.y, width=half_width, height=area.height)
    raise ValueError(f"Unsupported window role: {role}")


def _show_and_move_window(hwnd: int, rect: WindowRect) -> bool:
    ctypes.windll.user32.ShowWindow(hwnd, 9)
    return bool(ctypes.windll.user32.MoveWindow(hwnd, rect.x, rect.y, rect.width, rect.height, True))


def set_console_title(title_text: str) -> bool:
    if not title_text:
        return False
    return bool(ctypes.windll.kernel32.SetConsoleTitleW(title_text))


def minimize_window_by_title(title_text: str) -> bool:
    hwnd = find_visible_window_by_title(title_text)
    if not hwnd:
        return False
    ctypes.windll.user32.ShowWindow(hwnd, 6)
    return True


def minimize_visible_titled_windows(
    *,
    exclude_title_texts: tuple[str, ...] = (),
) -> int:
    exclusions = tuple(text.casefold() for text in exclude_title_texts if text)
    shell_hwnd = ctypes.windll.user32.GetShellWindow()
    minimized_count = 0
    enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd: int, _lparam: int) -> bool:
        nonlocal minimized_count
        if hwnd == shell_hwnd or not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
        title = _window_title(hwnd)
        if not title:
            return True
        folded = title.casefold()
        if exclusions and any(exclusion in folded for exclusion in exclusions):
            return True
        ctypes.windll.user32.ShowWindow(hwnd, 6)
        minimized_count += 1
        return True

    ctypes.windll.user32.EnumWindows(enum_windows_proc(callback), 0)
    return minimized_count


def _window_title(hwnd: int) -> str:
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def find_visible_window_by_title(
    title_text: str,
    *,
    prefer_title_texts: tuple[str, ...] = (),
    exclude_title_texts: tuple[str, ...] = (),
) -> int:
    needle = title_text.casefold()
    matched_hwnd = 0
    fallback_hwnd = 0
    preferences = tuple(text.casefold() for text in prefer_title_texts)
    exclusions = tuple(text.casefold() for text in exclude_title_texts)
    enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd: int, _lparam: int) -> bool:
        nonlocal matched_hwnd, fallback_hwnd
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
        title = _window_title(hwnd).casefold()
        if needle not in title:
            return True
        if exclusions and any(exclusion in title for exclusion in exclusions):
            return True
        if preferences and not any(preference in title for preference in preferences):
            if not fallback_hwnd:
                fallback_hwnd = hwnd
            return True
        if needle in title:
            matched_hwnd = hwnd
            return False
        return True

    ctypes.windll.user32.EnumWindows(enum_windows_proc(callback), 0)
    return matched_hwnd or fallback_hwnd


def move_console_to_half_screen(
    role: str = "worker",
    *,
    title_text: str = "",
    fallback_to_console_window: bool = True,
) -> bool:
    rect = half_screen_rect(role)
    if title_text:
        hwnd = find_visible_window_by_title(title_text)
        if hwnd and _show_and_move_window(hwnd, rect):
            return True
        if not fallback_to_console_window:
            return False
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd and _show_and_move_window(hwnd, rect):
        return True
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if hwnd:
        return _show_and_move_window(hwnd, rect)
    return False


def _send_key_chord(keys: list[int]) -> None:
    for key in keys:
        ctypes.windll.user32.keybd_event(key, 0, 0, 0)
    for key in reversed(keys):
        ctypes.windll.user32.keybd_event(key, 0, 2, 0)


def send_zoom_out_to_window(
    title_text: str,
    steps: int = 4,
    *,
    prefer_title_texts: tuple[str, ...] = (),
    exclude_title_texts: tuple[str, ...] = (),
    reset_first: bool = False,
    step_delay_seconds: float = 0.55,
) -> bool:
    if steps <= 0 and not reset_first:
        return True
    hwnd = find_visible_window_by_title(
        title_text,
        prefer_title_texts=prefer_title_texts,
        exclude_title_texts=exclude_title_texts,
    )
    if not hwnd:
        return False
    ctypes.windll.user32.ShowWindow(hwnd, 9)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)
    if reset_first:
        _send_key_chord([0x11, 0x30])
        time.sleep(step_delay_seconds)
    for _ in range(steps):
        _send_key_chord([0x11, 0xBD])
        time.sleep(step_delay_seconds)
    return True


def send_twinplay_browser_zoom_to_window(title_text: str) -> bool:
    return send_zoom_out_to_window(
        title_text,
        steps=TWINPLAY_BROWSER_ZOOM_OUT_STEPS,
        prefer_title_texts=TWINPLAY_BROWSER_TITLE_PREFERENCES,
        exclude_title_texts=TWINPLAY_BROWSER_TITLE_EXCLUSIONS,
        reset_first=True,
    )


def send_crm_twinplay_browser_zoom_to_window(title_text: str = "CRM") -> bool:
    return send_twinplay_browser_zoom_to_window(title_text)


def _send_virtual_desktop_shortcut(action: str) -> None:
    if action == "new":
        _send_key_chord([0x5B, 0x11, 0x44])
    elif action == "left":
        _send_key_chord([0x5B, 0x11, 0x25])
    elif action == "right":
        _send_key_chord([0x5B, 0x11, 0x27])
    else:
        raise ValueError(f"Unsupported virtual desktop action: {action}")
    time.sleep(0.7)


def _read_registry_binary(path: str, name: str) -> bytes:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
        value, _value_type = winreg.QueryValueEx(key, name)
    return bytes(value)


def virtual_desktop_state() -> tuple[int, int] | None:
    try:
        desktop_ids = _read_registry_binary(
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops",
            "VirtualDesktopIDs",
        )
    except OSError:
        return None
    desktops = [desktop_ids[index : index + 16] for index in range(0, len(desktop_ids), 16)]
    desktops = [desktop for desktop in desktops if len(desktop) == 16]
    if not desktops:
        return None

    current = b""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\SessionInfo",
        ) as session_root:
            session_count = winreg.QueryInfoKey(session_root)[0]
            for index in range(session_count):
                session_name = winreg.EnumKey(session_root, index)
                try:
                    current = _read_registry_binary(
                        rf"Software\Microsoft\Windows\CurrentVersion\Explorer\SessionInfo\{session_name}\VirtualDesktops",
                        "CurrentVirtualDesktop",
                    )
                except OSError:
                    continue
                if current:
                    break
    except OSError:
        current = b""

    current_index = 0
    if current:
        for index, desktop in enumerate(desktops, start=1):
            if desktop == current:
                current_index = index
                break
    return len(desktops), current_index


def switch_to_virtual_desktop_2(
    *,
    sleep: Callable[[float], None] = time.sleep,
    send_shortcut: Callable[[str], None] = _send_virtual_desktop_shortcut,
) -> None:
    target_index = 2
    sleep(0.15)
    state = virtual_desktop_state()
    if not state:
        send_shortcut("right")
        return

    desktop_count, current_index = state
    if desktop_count < target_index:
        for _ in range(target_index - desktop_count):
            send_shortcut("new")
        return

    if current_index <= 0:
        send_shortcut("right")
        return

    steps = target_index - current_index
    while steps > 0:
        send_shortcut("right")
        steps -= 1
    while steps < 0:
        send_shortcut("left")
        steps += 1
