"""Постоянные настройки приложения (JSON в профиле пользователя)."""

import json
import os
import sys

DEFAULTS = {
    "sumatra_path": "",
    "last_pdf_dir": "",
    # Язык интерфейса: "ru" | "en"
    "language": "ru",
    # Привязка формата бумаги к принтеру, напр. {"A4": "HP LaserJet", "A1": "Plotter"}
    "printer_map": {},
    # Пользовательские форматы бумаги, напр. {"Рулон 610": [610.0, 914.0]}
    "custom_papers": {},
}


def _settings_path():
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        folder = os.path.join(base, "PDFPrintRouter")
    else:
        folder = os.path.join(os.path.expanduser("~"), ".config", "PDFPrintRouter")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "settings.json")


class Settings:
    def __init__(self):
        self._path = _settings_path()
        self._data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self._path, encoding="utf-8") as f:
                self._data.update(json.load(f))
        except (OSError, json.JSONDecodeError):
            pass

    def save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def get(self, key, default=None):
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self._data[key] = value
        self.save()

    @property
    def printer_map(self):
        return self._data.get("printer_map", {})

    def set_printer_map(self, mapping):
        self._data["printer_map"] = mapping
        self.save()

    @property
    def custom_papers(self):
        """{имя: [w_mm, h_mm]} → {имя: (w_mm, h_mm)}."""
        return {k: tuple(v) for k, v in self._data.get("custom_papers", {}).items()}

    def set_custom_papers(self, papers):
        self._data["custom_papers"] = {k: list(v) for k, v in papers.items()}
        self.save()
