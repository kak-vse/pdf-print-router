# -*- coding: utf-8 -*-
"""Простая интернационализация: RU (исходные строки) → EN.

Использование:
    from .i18n import tr
    tr("Открыть PDF…")                       # статичная строка
    tr("Всего страниц: {n}").format(n=5)     # строка с параметрами

Язык переключается на лету через set_language(); выбор хранится
в настройках приложения (ключ "language": "ru" | "en").
"""

LANGUAGES = [("ru", "Русский"), ("en", "English")]

_lang = "ru"


def set_language(lang):
    global _lang
    _lang = lang if lang in dict(LANGUAGES) else "ru"


def get_language():
    return _lang


def tr(text):
    if _lang == "ru":
        return text
    return _EN.get(text, text)


_EN = {
    # ---- панель инструментов ----
    "Открыть PDF…": "Open PDF…",
    "Авторазбивка по форматам": "Auto-split by paper size",
    "Привязка принтеров…": "Printer mapping…",
    "Печать всех заданий": "Print all jobs",
    "Печать выбранного": "Print selected",
    "Экспорт заданий…": "Export jobs…",
    "Удалить задание": "Delete job",
    "Очистить всё": "Clear all",
    "Язык:": "Language:",

    # ---- редактор задания ----
    "Задание печати": "Print job",
    "Просмотр размещения": "Placement preview",
    "Масштаб: —": "Scale: —",
    "Документ: —": "Document: —",
    "Бумага: —": "Paper: —",
    "Страница —": "Page —",
    "Принтер:": "Printer:",
    "Копии:": "Copies:",
    "Бумага:": "Paper:",
    "Ориентация:": "Orientation:",
    "Дуплекс:": "Duplex:",
    "Цвет:": "Color:",
    "Масштаб:": "Scale:",
    "Поля:": "Margins:",
    "Название:": "Name:",
    "Страницы:": "Pages:",
    "Свойства…": "Properties…",
    "Открыть диалог свойств драйвера принтера (как в Foxit Reader): "
    "выбранные там формат, ориентация, копии, дуплекс и цвет "
    "подставятся в задание":
        "Open the printer driver properties dialog (like in Foxit Reader): "
        "the paper size, orientation, copies, duplex and color chosen "
        "there will be applied to the job",
    "Автоповорот": "Auto-rotate",
    "Поворачивать альбомные страницы на 90°, чтобы они заняли "
    "весь книжный лист (как «Автоповорот» в Foxit Reader). "
    "Снимите галочку, чтобы вписывать их без поворота":
        "Rotate landscape pages by 90° so they fill the whole portrait "
        "sheet (like “Auto-rotate” in Foxit Reader). "
        "Uncheck to fit them without rotation",
    "Автоцентрирование": "Auto-center",
    "Центрировать содержимое на листе (иначе — от левого верхнего угла)":
        "Center the content on the sheet (otherwise align to the top-left corner)",
    "Формат из принтера…": "Size from printer…",
    "Показать форматы бумаги, поддерживаемые драйвером "
    "выбранного принтера, и подставить один из них":
        "Show paper sizes supported by the selected printer driver "
        "and pick one of them",
    "Свои форматы…": "Custom sizes…",
    "Добавить произвольные форматы бумаги (плоттеры, рулоны, этикетки)":
        "Add custom paper sizes (plotters, rolls, labels)",
    "например: 1-3,7": "e.g.: 1-3,7",
    "← выбранные": "← selected",
    "Создать задание": "Create job",
    "Обновить выбранное": "Update selected",

    # ---- значения комбобоксов ----
    "Авто": "Auto",
    "Книжная": "Portrait",
    "Альбомная": "Landscape",
    "Вписать": "Fit",
    "Заполнить": "Fill",
    "100% (без масштаба)": "100% (no scaling)",
    "Свой процент": "Custom percent",
    "Нет": "None",
    "По длинной стороне": "Long edge",
    "По короткой стороне": "Short edge",
    "Цвет": "Color",
    "Монохром": "Monochrome",
    "книжная": "portrait",
    "альбомная": "landscape",
    "мм": "mm",

    # ---- список заданий ----
    "Задания": "Jobs",
    "Название": "Name",
    "Страниц": "Pages",
    "Принтер": "Printer",
    "Бумага": "Paper",
    "Ориентация": "Orientation",
    "Дуплекс": "Duplex",
    "Копии": "Copies",
    "(не выбран)": "(not set)",

    # ---- документ ----
    "Открыть PDF": "Open PDF",
    "PDF-файлы (*.pdf)": "PDF files (*.pdf)",
    "Не удалось открыть файл:\n{e}": "Failed to open file:\n{e}",
    "Открыт: {name} — {n} стр.": "Opened: {name} — {n} pages",
    "Загрузка миниатюр…": "Loading thumbnails…",
    "Отмена": "Cancel",
    "{label}, стр. {ranges}": "{label}, pages {ranges}",

    # ---- задание: ошибки и статусы ----
    "Сначала откройте PDF": "Open a PDF first",
    "Укажите страницы (или выделите их слева и нажмите «← выбранные»)":
        "Specify pages (or select them on the left and click “← selected”)",
    "Задание {n}": "Job {n}",
    "Выберите задание в таблице": "Select a job in the table",
    "Создано заданий: {n}": "Jobs created: {n}",
    "; без принтера: {n} — заполните вручную или через «Привязка принтеров…»":
        "; without printer: {n} — assign manually or via “Printer mapping…”",
    "Привязка принтеров сохранена": "Printer mapping saved",
    "Некорректный диапазон «{part}» (всего страниц: {total})":
        "Invalid range “{part}” (total pages: {total})",
    "Некорректная страница {n} (всего: {total})":
        "Invalid page {n} (total: {total})",

    # ---- превью размещения ----
    "Масштаб: {v} %": "Scale: {v} %",
    "Документ: {w} x {h} см": "Document: {w} x {h} cm",
    "Бумага: {w} x {h} см": "Paper: {w} x {h} cm",
    "Страница {i} из {n}": "Page {i} of {n}",

    # ---- свойства и форматы принтера ----
    "Сначала выберите принтер": "Select a printer first",
    "Диалог свойств принтера закрыт без изменений":
        "Printer properties dialog closed without changes",
    "бумага {paper}": "paper {paper}",
    "ориентация ": "orientation ",
    "копии {n}": "copies {n}",
    "дуплекс ": "duplex ",
    "цвет ": "color ",
    "Из свойств принтера подставлено: ": "Applied from printer properties: ",
    "Драйвер не вернул настроек — задание не изменено":
        "Driver returned no settings — job unchanged",
    "Драйвер «{printer}» не вернул список форматов бумаги":
        "Driver “{printer}” returned no paper size list",
    "Выбран формат «{paper}» ({w}×{h} мм)":
        "Selected size “{paper}” ({w}×{h} mm)",
    "Пользовательские форматы сохранены": "Custom paper sizes saved",

    # ---- печать ----
    "Нет заданий для печати": "No jobs to print",
    "Не выбран принтер для заданий:\n": "No printer selected for jobs:\n",
    "Найдите SumatraPDF.exe": "Locate SumatraPDF.exe",
    "Для печати нужен SumatraPDF 3.2+\n"
    "https://www.sumatrapdfreader.org/download-free-pdf-viewer":
        "SumatraPDF 3.2+ is required for printing\n"
        "https://www.sumatrapdfreader.org/download-free-pdf-viewer",
    "Печать…": "Printing…",
    "— отменено пользователем": "— cancelled by user",
    "ОШИБКА": "ERROR",
    "{n} стр.": "{n} pages",
    "Результат печати": "Print results",
    "Откройте PDF и создайте задания": "Open a PDF and create jobs",
    "Папка для экспорта": "Export folder",
    "\nМанифест сохранён: {path}": "\nManifest saved: {path}",
    "Экспорт завершён": "Export finished",

    # ---- диалог привязки принтеров ----
    "Привязка форматов к принтерам": "Paper-to-printer mapping",
    "Формат бумаги": "Paper size",
    "＋ Добавить формат": "＋ Add size",
    "Форматы из драйвера принтера…": "Sizes from printer driver…",
    "Добавить все форматы бумаги, которые поддерживает драйвер "
    "выбранного принтера, и сразу привязать их к нему":
        "Add all paper sizes supported by the selected printer's driver "
        "and map them to it at once",
    "Используется при авторазбивке: страницы каждого формата уйдут "
    "на привязанный принтер. Форматы из драйвера также сохраняются "
    "в пользовательские и появляются в списке «Бумага».":
        "Used by auto-split: pages of each size go to the mapped printer. "
        "Driver sizes are also saved to custom sizes and appear "
        "in the “Paper” list.",
    "Убрать строку": "Remove row",
    "Принтеры не найдены": "No printers found",
    "Форматы из драйвера": "Driver sizes",
    "Все форматы этого принтера уже в списке":
        "All sizes of this printer are already listed",

    # ---- диалог пользовательских форматов ----
    "Пользовательские форматы бумаги": "Custom paper sizes",
    "Ширина, мм": "Width, mm",
    "Высота, мм": "Height, mm",
    "Например: Рулон 610×914": "E.g.: Roll 610×914",
    "Добавить": "Add",
    "Удалить выбранный": "Delete selected",
    "Форматы сохраняются и участвуют в авторазбивке и привязке "
    "принтеров. Для рулона укажите ширину рулона и типовую длину.":
        "Sizes are saved and used in auto-split and printer mapping. "
        "For a roll, enter the roll width and a typical length.",
    "Укажите название формата": "Enter a size name",

    # ---- диалог форматов из драйвера ----
    "Форматы бумаги: {printer}": "Paper sizes: {printer}",
    "Формат (драйвер)": "Size (driver)",
    "Формат будет добавлен в список «Бумага» (и в пользовательские "
    "форматы), драйвер сможет напечатать его без подгонки.":
        "The size will be added to the “Paper” list (and to custom "
        "sizes); the driver will print it without adjustments.",
    "Выберите формат в списке": "Select a size in the list",

    # ---- printers.py / jobs.py / gdi_print.py ----
    "не выбран принтер": "no printer selected",
    "таймаут (принтер не отвечает?)": "timeout (printer not responding?)",
    "отправлено на печать": "sent to printer",
    "код {code}: {out}": "code {code}: {out}",
    "{name} ({n} стр.)": "{name} ({n} pages)",
    "{name}: стр. {n} шт. → {printer}, {paper}, {orient}, дуплекс={duplex}, копий={copies}":
        "{name}: {n} pages → {printer}, {paper}, {orient}, duplex={duplex}, copies={copies}",
    "(принтер не выбран)": "(no printer selected)",
    "Пустой mediabox страницы": "Empty page mediabox",
    "PDF защищён паролем": "PDF is password-protected",
    "Не удалось открыть принтер «{name}»": "Failed to open printer “{name}”",
    "DocumentProperties: не удалось получить размер DEVMODE":
        "DocumentProperties: failed to get DEVMODE size",
    "DocumentProperties: не удалось получить DEVMODE":
        "DocumentProperties: failed to get DEVMODE",
    "CreateDCW: драйвер отклонил настройки бумаги":
        "CreateDCW: driver rejected the paper settings",
    "драйвер вернул некорректные параметры страницы":
        "driver returned invalid page parameters",
    "StartDoc: задание не создано": "StartDoc: job not created",
    "StartPage: ошибка драйвера": "StartPage: driver error",
    "StretchDIBits: ошибка вывода": "StretchDIBits: output error",
    "EndPage: ошибка драйвера": "EndPage: driver error",
    "отправлено на печать (GDI)": "sent to printer (GDI)",

    # ---- запуск не в Windows ----
    "Принтеры не найдены (это нормально при запуске не в Windows)":
        "No printers found (normal when not running on Windows)",
}
