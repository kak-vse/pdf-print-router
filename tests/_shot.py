# -*- coding: utf-8 -*-
"""Скриншот главного окна PDF Print Router (pywin32 + pymupdf)."""
import os
import time

import numpy as np
import pymupdf
import win32gui
import win32ui


def main():
    found = []

    def _cb(h, _):
        if win32gui.IsWindowVisible(h) and "PDF Print Router" in win32gui.GetWindowText(h):
            found.append(h)
    win32gui.EnumWindows(_cb, None)
    if not found:
        raise RuntimeError("окно не найдено")
    hwnd = found[0]
    print("заголовок:", win32gui.GetWindowText(hwnd))

    win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass  # фоновым процессам нельзя выводить окно на передний план
    time.sleep(1.0)

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    w, h = right - left, bottom - top
    print(f"окно: {left},{top} {w}x{h}")

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc_dc, w, h)
    save_dc.SelectObject(bmp)
    save_dc.BitBlt((0, 0), (w, h), mfc_dc, (0, 0), win32con_srccopy())

    raw = bmp.GetBitmapBits(True)
    arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 4)
    rgb = np.ascontiguousarray(arr[:, :, :3][:, :, ::-1])  # BGRA→RGB

    os.makedirs(r"C:\KIMI\pdf-printer-app\docs", exist_ok=True)
    pix = pymupdf.Pixmap(pymupdf.csRGB, w, h, rgb.tobytes(), False)
    out = r"C:\KIMI\pdf-printer-app\docs\main-window.png"
    pix.save(out)
    print("сохранено:", out)

    win32gui.DeleteObject(bmp.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)


def win32con_srccopy():
    return 0x00CC0020


if __name__ == "__main__":
    main()
