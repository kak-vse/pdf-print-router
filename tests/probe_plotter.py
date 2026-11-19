# -*- coding: utf-8 -*-
"""Зонд: как драйвер плоттера принимает DEVMODE (без печати, только DC)."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.gdi_print as g
import win32print

names = [p[2] for p in win32print.EnumPrinters(2)]
plotter = next((n for n in names if "T520" in n or "DJ" in n.upper()), None)
print("принтеры:", names)
print("плоттер:", plotter)
if not plotter:
    sys.exit(1)

print("\nформы драйвера:")
for pid, name, w, h in g.get_printer_forms(plotter):
    print(f"  id={pid:4d}  {name:<40s} {w} x {h} мм")

def probe(title, form_id, paper_mm, orient):
    h = g._open_printer(plotter)
    try:
        buf = g._get_devmode(h, plotter)
        g._patch_devmode(buf, form_id, paper_mm, 1, None, None)
        struct.pack_into("<h", buf, g._OFF_ORIENTATION, orient)
        hdc = g._gdi32.CreateDCW("WINSPOOL", plotter, None, buf)
        if not hdc:
            print(f"{title}: CreateDCW ОТКАЗ")
            return
        try:
            dpi = g._gdi32.GetDeviceCaps(hdc, g._LOGPIXELSX)
            pw = g._gdi32.GetDeviceCaps(hdc, g._HORZRES)
            ph = g._gdi32.GetDeviceCaps(hdc, g._VERTRES)
            print(f"{title}: HORZRES x VERTRES = {pw} x {ph} px @ {dpi} dpi "
                  f"= {pw / dpi * 25.4:.1f} x {ph / dpi * 25.4:.1f} мм")
        finally:
            g._gdi32.DeleteDC(hdc)
    finally:
        g._winspool.ClosePrinter(h)

forms = g.get_printer_forms(plotter)
a3_id = g._find_form_id(forms, 297.0, 420.0)
a2_id = g._find_form_id(forms, 420.0, 594.0)
print(f"\nA3 (297x420) form id: {a3_id},  A2 (420x594) form id: {a2_id}")

probe("USER 4200x2970 portrait", None, (420.0, 297.0), 1)
probe("USER 4200x2970 landscape", None, (420.0, 297.0), 2)
probe("USER 5940x4200 portrait", None, (594.0, 420.0), 1)
if a3_id:
    probe("форма A3 + portrait", a3_id, (297.0, 420.0), 1)
    probe("форма A3 + landscape", a3_id, (297.0, 420.0), 2)
