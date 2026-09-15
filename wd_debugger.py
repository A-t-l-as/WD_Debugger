#!/usr/bin/env python3
"""
WDDebugger
==========

Narzedzie do analizy archiwow .wd (format uzywany m.in. przez silnik gry
oparty o Earth 2150 / EarthTool). Uruchamiane z katalogu gry:

    python wd_debugger.py

Program wchodzi do podkatalogu WDFiles, wczytuje "central directory"
(liste elementow) z kazdego pliku .wd - BEZ rozpakowywania samych plikow,
tylko metadane - a nastepnie szuka elementow, ktore wystepuja w wiecej
niz jednym archiwum .wd (czyli potencjalnych duplikatow / nadpisan).

Format pliku .wd (odtworzony na podstawie zrodel EarthTool - MIT,
https://github.com/Arkezar/EarthTool, klasy ArchiveFactory.cs i Archive.cs):

    [skompresowany zlib naglowek archiwum]
    [dane elementu 1]
    ...
    [dane elementu N]
    [skompresowany zlib central directory]   <- to nas interesuje
    [4 bajty: dlugosc powyzszego bloku + 4]

Central directory (po rozpakowaniu zlib), little-endian:
    int64   LastModification (Windows FILETIME)
    int16   liczba elementow
    dla kazdego elementu:
        string  nazwa/sciezka (format .NET BinaryWriter: 7-bit-encoded
                 dlugosc + bajty w kodowaniu ISO-8859-2)
        byte    flags (Compressed=1, Archive=2, Text=4, Named=8,
                        Resource=16, Guid=32)
        int32   offset danych w pliku
        int32   compressedSize
        int32   decompressedSize
        [string translationId]   -- tylko jesli flaga Named
        [int32  resourceType]    -- tylko jesli flaga Resource
        [16B    guid]            -- tylko jesli flaga Guid
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

ENCODING = "iso-8859-2"  # tak zarejestrowane jest w EarthTool.Common/HostExtensions.cs

FLAG_COMPRESSED = 1
FLAG_ARCHIVE = 2
FLAG_TEXT = 4
FLAG_NAMED = 8
FLAG_RESOURCE = 16
FLAG_GUID = 32

DEFAULT_LANG = "pl"

# Wszystkie teksty widoczne dla uzytkownika (CLI + GUI + raporty) w dwoch
# wersjach jezykowych. Klucz -> {"pl": ..., "en": ...}. Uzycie: t(klucz, lang, **kwargs).
TEXTS: dict[str, dict[str, str]] = {
    "app_desc": {
        "pl": "WDDebugger - szuka duplikatow elementow w plikach .wd",
        "en": "WDDebugger - finds duplicate items across .wd archive files",
    },
    "help_wdfiles_dir": {
        "pl": "katalog z plikami .wd (domyslnie WDFiles obok programu)",
        "en": "directory containing .wd files (defaults to WDFiles next to the program)",
    },
    "help_game_dir": {
        "pl": "katalog glowny gry, w ktorym sprawdzane sa luzne (wypakowane) pliki "
              "nadpisujace zawartosc archiwow (domyslnie katalog biezacy)",
        "en": "game root directory, used to check for loose (extracted) files "
              "overriding archive contents (defaults to the current directory)",
    },
    "help_no_loose_check": {
        "pl": "nie sprawdzaj luznych plikow w katalogu gry, tylko duplikaty miedzy .wd",
        "en": "skip checking loose files in the game directory; only check duplicates between .wd files",
    },
    "help_no_stray_check": {
        "pl": "nie sprawdzaj, czy w katalogu gry i podkatalogach sa pliki .wd "
              "lezace poza katalogiem WDFiles",
        "en": "skip checking whether .wd files exist outside the WDFiles directory "
              "(in the game directory or its subdirectories)",
    },
    "help_case_sensitive": {
        "pl": "porownuj nazwy z rozroznieniem wielkosci liter",
        "en": "compare names case-sensitively",
    },
    "help_csv": {
        "pl": "dodatkowo zapisz raport duplikatow do CSV",
        "en": "also save the duplicates report to a CSV file",
    },
    "help_output_txt": {
        "pl": "plik .txt, do ktorego zapisany zostanie caly raport "
              "(domyslnie wd_debugger_report.txt; podaj '-' zeby wylaczyc zapis)",
        "en": "text file to write the full report to "
              "(defaults to wd_debugger_report.txt; pass '-' to disable saving)",
    },
    "help_gui": {
        "pl": "uruchom w trybie graficznym (okienko z logiem na zywo)",
        "en": "run in graphical mode (window with a live log)",
    },
    "help_lang": {
        "pl": "jezyk programu: pl lub en (domyslnie pl)",
        "en": "program language: pl or en (default: pl)",
    },
    "metavar_file": {"pl": "PLIK", "en": "FILE"},

    "err_no_wdfiles_dir": {
        "pl": "[BLAD] Nie znaleziono katalogu '{dir}'. Uruchom program z katalogu gry "
              "(lub podaj poprawna sciezke do WDFiles).",
        "en": "[ERROR] Directory '{dir}' not found. Run the program from the game directory "
              "(or provide the correct path to WDFiles).",
    },
    "err_no_wd_files": {
        "pl": "[BLAD] Brak plikow .wd w '{dir}'.",
        "en": "[ERROR] No .wd files found in '{dir}'.",
    },
    "found_wd_files": {
        "pl": "Znaleziono {n} plikow .wd w '{dir}'.",
        "en": "Found {n} .wd files in '{dir}'.",
    },
    "files_summary_header": {
        "pl": "Podsumowanie plikow:",
        "en": "File summary:",
    },
    "file_summary_line": {
        "pl": "  {name:<30} {count:>6} elementow",
        "en": "  {name:<30} {count:>6} items",
    },
    "parse_errors_footer": {
        "pl": "\n  ({n} plikow nie udalo sie sparsowac - patrz komunikaty powyzej)",
        "en": "\n  ({n} files could not be parsed - see messages above)",
    },
    "parse_error_line": {
        "pl": "[BLAD] {name}: {err}",
        "en": "[ERROR] {name}: {err}",
    },
    "loose_check_summary": {
        "pl": "Sprawdzono luzne pliki w katalogu gry '{dir}': znaleziono {n} elementow "
              "z archiwow, ktore maja odpowiednik na dysku.",
        "en": "Checked loose files in the game directory '{dir}': found {n} archive items "
              "that have a counterpart on disk.",
    },
    "stray_warning_header": {
        "pl": "[UWAGA] Znaleziono {n} plikow .wd w '{dir}' (lub podkatalogach), "
              "ktore leza POZA katalogiem '{wd_dir}':",
        "en": "[WARNING] Found {n} .wd files in '{dir}' (or its subdirectories) "
              "that lie OUTSIDE the '{wd_dir}' directory:",
    },
    "stray_warning_footer": {
        "pl": "      -> te pliki NIE zostaly wziete pod uwage w analizie duplikatow powyzej.",
        "en": "      -> these files were NOT taken into account in the duplicate analysis above.",
    },
    "no_stray_found": {
        "pl": "Nie znaleziono dodatkowych plikow .wd poza katalogiem '{wd_dir}' "
              "(przeszukano '{dir}' wraz z podkatalogami).",
        "en": "No additional .wd files found outside the '{wd_dir}' directory "
              "(searched '{dir}' and its subdirectories).",
    },
    "duplicates_header": {
        "pl": "Znaleziono {n} elementow wystepujacych w wiecej niz jednym pliku .wd:",
        "en": "Found {n} items that occur in more than one .wd file:",
    },
    "occurs_in": {
        "pl": "      -> wystepuje w: {archives}",
        "en": "      -> occurs in: {archives}",
    },
    "occurrence_count": {
        "pl": "      -> liczba wystapien: {n}",
        "en": "      -> occurrence count: {n}",
    },
    "loose_overrides_header": {
        "pl": "Znaleziono {n} elementow z archiwow .wd, ktore sa NADPISANE przez "
              "luzny (wypakowany) plik w katalogu gry:",
        "en": "Found {n} items from .wd archives that are OVERRIDDEN by a loose "
              "(extracted) file in the game directory:",
    },
    "in_archives": {
        "pl": "      -> w archiwach: {sources}",
        "en": "      -> in archives: {sources}",
    },
    "and_as_loose_file": {
        "pl": "      -> ORAZ jako luzny plik: {path}",
        "en": "      -> AND as a loose file: {path}",
    },
    "csv_saved": {
        "pl": "Zapisano raport CSV do: {path}",
        "en": "CSV report saved to: {path}",
    },
    "txt_saved": {
        "pl": "Zapisano pelny raport do: {path}",
        "en": "Full report saved to: {path}",
    },
    "csv_header_row": {
        "pl": "element,zrodlo,nazwa_oryginalna",
        "en": "item,source,original_name",
    },
    "csv_stray_section_title": {
        "pl": "plik_wd_poza_WDFiles",
        "en": "wd_file_outside_WDFiles",
    },
    "unexpected_exception": {
        "pl": "[BLAD] Nieoczekiwany wyjatek: {err}",
        "en": "[ERROR] Unexpected exception: {err}",
    },
    "loose_label": {
        "pl": "[LUZNE PLIKI]",
        "en": "[LOOSE FILES]",
    },

    # GUI
    "window_title": {"pl": "WDDebugger", "en": "WDDebugger"},
    "label_wdfiles_dir": {"pl": "Katalog WDFiles:", "en": "WDFiles directory:"},
    "label_game_dir": {"pl": "Katalog gry:", "en": "Game directory:"},
    "label_csv": {"pl": "Raport CSV (opcjonalnie):", "en": "CSV report (optional):"},
    "label_txt": {"pl": "Raport TXT:", "en": "TXT report:"},
    "label_language": {"pl": "Jezyk:", "en": "Language:"},
    "button_browse": {"pl": "Przegladaj...", "en": "Browse..."},
    "check_case_sensitive": {"pl": "Rozroznianie wielkosci liter", "en": "Case-sensitive matching"},
    "check_loose": {"pl": "Sprawdzaj luzne pliki w katalogu gry", "en": "Check loose files in game directory"},
    "check_stray": {"pl": "Szukaj plikow .wd poza WDFiles", "en": "Search for .wd files outside WDFiles"},
    "status_ready": {"pl": "Gotowy.", "en": "Ready."},
    "status_running": {"pl": "Analiza w toku...", "en": "Analysis in progress..."},
    "status_done": {"pl": "Zakonczono.", "en": "Done."},
    "button_run": {"pl": "Uruchom analize", "en": "Run analysis"},
    "default_report_filename": {"pl": "raport.txt", "en": "report.txt"},
}


def t(key: str, lang: str, **kwargs) -> str:
    """Zwraca przetlumaczony tekst dla danego klucza i jezyka (pl/en),
    z podstawionymi parametrami (jesli sa)."""
    template = TEXTS[key].get(lang, TEXTS[key][DEFAULT_LANG])
    return template.format(**kwargs) if kwargs else template


def _is_error_line(line: str) -> bool:
    """Rozpoznaje linie bledu niezaleznie od jezyka (do kolorowania w GUI)."""
    return line.startswith("[BLAD]") or line.startswith("[ERROR]")


def _detect_cli_lang(argv: list[str]) -> str:
    """Wstepnie wykrywa jezyk z argumentow wiersza polecen (dla poprawnego --help)."""
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            val = argv[i + 1].strip().lower()
            if val in ("pl", "en"):
                return val
        elif a.startswith("--lang="):
            val = a.split("=", 1)[1].strip().lower()
            if val in ("pl", "en"):
                return val
    return DEFAULT_LANG


class WdFormatError(Exception):
    pass


@dataclass
class WdItem:
    name: str
    flags: int
    offset: int
    compressed_size: int
    decompressed_size: int
    translation_id: str | None = None
    resource_type: int | None = None
    guid: bytes | None = None


def read_7bit_encoded_int(buf: bytes, pos: int) -> tuple[int, int]:
    """Odpowiednik .NET BinaryReader.Read7BitEncodedInt."""
    result = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise WdFormatError("Nieoczekiwany koniec danych przy odczycie dlugosci stringa")
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
        if shift > 35:
            raise WdFormatError("Zle uformowany 7-bit-encoded int (za dlugi)")
    return result, pos


def read_net_string(buf: bytes, pos: int) -> tuple[str, int]:
    """Odpowiednik .NET BinaryReader.ReadString()."""
    length, pos = read_7bit_encoded_int(buf, pos)
    raw = buf[pos:pos + length]
    if len(raw) != length:
        raise WdFormatError("Nieoczekiwany koniec danych przy odczycie tresci stringa")
    pos += length
    return raw.decode(ENCODING, errors="replace"), pos


def parse_central_directory(data: bytes) -> tuple[int, list[WdItem]]:
    """Parsuje juz ROZPAKOWANY blok central directory. Zwraca (last_mod_filetime, items)."""
    if len(data) < 10:
        raise WdFormatError("Central directory za krotki")

    last_mod = struct.unpack_from("<q", data, 0)[0]
    item_count = struct.unpack_from("<h", data, 8)[0]
    pos = 10

    items: list[WdItem] = []
    for _ in range(item_count):
        name, pos = read_net_string(data, pos)
        flags = data[pos]
        pos += 1
        offset, compressed_size, decompressed_size = struct.unpack_from("<iii", data, pos)
        pos += 12

        translation_id = None
        if flags & FLAG_NAMED:
            translation_id, pos = read_net_string(data, pos)

        resource_type = None
        if flags & FLAG_RESOURCE:
            resource_type = struct.unpack_from("<i", data, pos)[0]
            pos += 4

        guid = None
        if flags & FLAG_GUID:
            guid = data[pos:pos + 16]
            pos += 16

        items.append(WdItem(name, flags, offset, compressed_size, decompressed_size,
                             translation_id, resource_type, guid))

    return last_mod, items


def read_wd_item_list(path: Path) -> tuple[int, list[WdItem]]:
    """Otwiera plik .wd i zwraca liste elementow (bez rozpakowywania samych plikow)."""
    with path.open("rb") as f:
        f.seek(0, 2)
        file_size = f.tell()
        if file_size < 4:
            raise WdFormatError(f"{path}: plik zbyt maly")

        f.seek(file_size - 4)
        (descriptor_length,) = struct.unpack("<i", f.read(4))

        central_dir_offset = file_size - descriptor_length
        central_dir_size = descriptor_length - 4
        if central_dir_offset < 0 or central_dir_size < 0:
            raise WdFormatError(f"{path}: nieprawidlowa dlugosc central directory ({descriptor_length})")

        f.seek(central_dir_offset)
        compressed = f.read(central_dir_size)

    try:
        raw = zlib.decompress(compressed)
    except zlib.error as e:
        raise WdFormatError(f"{path}: blad dekompresji zlib central directory: {e}") from e

    return parse_central_directory(raw)


def normalize_name(name: str) -> str:
    """Normalizacja do porownan: gra traktuje sciezki bez rozroznienia
    wielkosci liter i uzywa '\\' jako separatora."""
    return name.replace("/", "\\").lower()


def find_stray_wd_files(search_root: Path, wd_dir_resolved: Path) -> list[Path]:
    """Przeszukuje search_root i wszystkie podkatalogi w poszukiwaniu plikow .wd/.WD,
    ktore leza POZA katalogiem WDFiles (wd_dir_resolved). Zwraca posortowana liste
    znalezionych sciezek (bez duplikatow, np. gdy system plikow nie rozroznia wielkosci liter)."""
    stray: set[Path] = set()
    for path in search_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() != ".wd":
            continue
        resolved = path.resolve()
        try:
            resolved.relative_to(wd_dir_resolved)
            continue  # plik jest wewnatrz WDFiles - to nie jest "zabladzony" plik
        except ValueError:
            pass
        stray.add(resolved)
    return sorted(stray)


def main() -> int:
    # Wykrywamy jezyk wczesniej, zeby --help tez byl wyswietlony w odpowiedniej wersji.
    pre_lang = _detect_cli_lang(sys.argv[1:])

    parser = argparse.ArgumentParser(description=t("app_desc", pre_lang))
    parser.add_argument("--wdfiles-dir", default="WDFiles",
                         help=t("help_wdfiles_dir", pre_lang))
    parser.add_argument("--game-dir", default=".",
                         help=t("help_game_dir", pre_lang))
    parser.add_argument("--no-loose-check", action="store_true",
                         help=t("help_no_loose_check", pre_lang))
    parser.add_argument("--no-stray-check", action="store_true",
                         help=t("help_no_stray_check", pre_lang))
    parser.add_argument("--case-sensitive", action="store_true",
                         help=t("help_case_sensitive", pre_lang))
    parser.add_argument("--csv", metavar=t("metavar_file", pre_lang), default=None,
                         help=t("help_csv", pre_lang))
    parser.add_argument("--output-txt", metavar=t("metavar_file", pre_lang), default="wd_debugger_report.txt",
                         help=t("help_output_txt", pre_lang))
    parser.add_argument("--gui", action="store_true",
                         help=t("help_gui", pre_lang))
    parser.add_argument("--lang", choices=["pl", "en"], default=pre_lang,
                         help=t("help_lang", pre_lang))
    args = parser.parse_args()
    lang = args.lang

    if args.gui:
        launch_gui(
            wdfiles_dir=args.wdfiles_dir,
            game_dir=args.game_dir,
            case_sensitive=args.case_sensitive,
            no_loose_check=args.no_loose_check,
            no_stray_check=args.no_stray_check,
            csv_path=args.csv or "",
            output_txt=args.output_txt,
            lang=lang,
        )
        return 0

    ok = run_analysis(
        wdfiles_dir=args.wdfiles_dir,
        game_dir=args.game_dir,
        case_sensitive=args.case_sensitive,
        no_loose_check=args.no_loose_check,
        no_stray_check=args.no_stray_check,
        csv_path=args.csv,
        output_txt=args.output_txt,
        log=print,
        lang=lang,
    )
    return 0 if ok else 1


def run_analysis(
    *,
    wdfiles_dir: str,
    game_dir: str,
    case_sensitive: bool,
    no_loose_check: bool,
    no_stray_check: bool = False,
    csv_path: str | None,
    output_txt: str | None,
    log,
    lang: str = DEFAULT_LANG,
) -> bool:
    """
    Wykonuje cala analize i przekazuje kolejne linie raportu do funkcji `log`
    (log(str) -> None). Zwraca False jesli wystapil blad krytyczny
    (np. brak katalogu WDFiles), True w przeciwnym razie.

    Ta funkcja jest wspolna zarowno dla trybu konsolowego, jak i GUI - dzieki
    temu obie wersje zawsze pokazuja dokladnie to samo.
    """
    report_lines: list[str] = []

    def out(line: str = "") -> None:
        log(line)
        report_lines.append(line)

    wd_dir = Path(wdfiles_dir)
    if not wd_dir.is_dir():
        out(t("err_no_wdfiles_dir", lang, dir=wd_dir))
        return False

    game_dir_path = Path(game_dir).resolve()
    wd_dir_resolved = wd_dir.resolve()

    wd_files = sorted(wd_dir.glob("*.wd")) + sorted(wd_dir.glob("*.WD"))
    wd_files = sorted(set(wd_files))
    if not wd_files:
        out(t("err_no_wd_files", lang, dir=wd_dir))
        return False

    out(t("found_wd_files", lang, n=len(wd_files), dir=wd_dir))
    out()

    # normalized_name -> list of (source_label, original_name)
    # source_label to albo nazwa pliku .wd, albo "[LUZNE PLIKI]" dla plikow z dysku
    occurrences: dict[str, list[tuple[str, str]]] = defaultdict(list)
    per_file_counts: dict[Path, int] = {}
    errors: list[tuple[Path, str]] = []

    LOOSE_LABEL = t("loose_label", lang)

    for wd_path in wd_files:
        try:
            _, items = read_wd_item_list(wd_path)
        except WdFormatError as e:
            errors.append((wd_path, str(e)))
            out(t("parse_error_line", lang, name=wd_path.name, err=e))
            continue

        per_file_counts[wd_path] = len(items)
        for item in items:
            key = item.name if case_sensitive else normalize_name(item.name)
            occurrences[key].append((wd_path.name, item.name))

    out(t("files_summary_header", lang))
    for wd_path in wd_files:
        if wd_path in per_file_counts:
            out(t("file_summary_line", lang, name=wd_path.name, count=per_file_counts[wd_path]))
    if errors:
        out(t("parse_errors_footer", lang, n=len(errors)))

    # --- sprawdzenie luznych (wypakowanych) plikow w katalogu gry ---
    loose_found = 0
    if not no_loose_check:
        for key, occ_list in occurrences.items():
            # bierzemy oryginalna nazwe z pierwszego wystapienia jako sciezke do sprawdzenia
            original_name = occ_list[0][1]
            relative_path = original_name.replace("\\", "/")
            candidate = (game_dir_path / relative_path).resolve()

            # zabezpieczenie: nie liczymy plikow .wd samej siebie i pomijamy WDFiles
            try:
                candidate.relative_to(wd_dir_resolved)
                continue  # sciezka wskazuje w katalog WDFiles - pomijamy
            except ValueError:
                pass

            if candidate.is_file():
                occ_list.append((LOOSE_LABEL, original_name))
                loose_found += 1

        out()
        out(t("loose_check_summary", lang, dir=game_dir_path, n=loose_found))

    # --- sprawdzenie plikow .wd lezacych poza katalogiem WDFiles ---
    stray_wd_files: list[Path] = []
    if not no_stray_check:
        stray_wd_files = find_stray_wd_files(game_dir_path, wd_dir_resolved)
        out()
        if stray_wd_files:
            out(t("stray_warning_header", lang, n=len(stray_wd_files), dir=game_dir_path, wd_dir=wd_dir))
            for p in stray_wd_files:
                try:
                    display = p.relative_to(game_dir_path)
                except ValueError:
                    display = p
                out(f"  {display}")
            out(t("stray_warning_footer", lang))
        else:
            out(t("no_stray_found", lang, wd_dir=wd_dir, dir=game_dir_path))

    # duplikaty = klucze, ktore pojawiaja sie w wiecej niz jednym miejscu
    # (dwa lub wiecej pliki .wd, LUB co najmniej jeden .wd + luzny plik na dysku)
    duplicates: dict[str, list[tuple[str, str]]] = {}
    loose_overrides: dict[str, list[tuple[str, str]]] = {}
    for key, occ_list in occurrences.items():
        sources_involved = {src for src, _ in occ_list}
        if len(sources_involved) > 1:
            if LOOSE_LABEL in sources_involved:
                loose_overrides[key] = occ_list
            else:
                duplicates[key] = occ_list

    out()
    out(t("duplicates_header", lang, n=len(duplicates)))
    out()

    csv_rows: list[tuple[str, str, str]] = []
    # sortujemy tak, zeby duplikaty wystepujace w najwiekszej liczbie archiwow byly na gorze
    for key in sorted(duplicates, key=lambda k: (-len(duplicates[k]), k)):
        occ_list = duplicates[key]
        display_name = occ_list[0][1]
        archive_names = ", ".join(src for src, _ in occ_list)
        out(f"  {display_name}")
        out(t("occurs_in", lang, archives=archive_names))
        out(t("occurrence_count", lang, n=len(occ_list)))
        out()  # pusta linia po kazdym wpisie dla czytelnosci
        for src, orig in occ_list:
            csv_rows.append((display_name, src, orig))

    if not no_loose_check:
        out()
        out(t("loose_overrides_header", lang, n=len(loose_overrides)))
        out()
        for key in sorted(loose_overrides, key=lambda k: k):
            occ_list = loose_overrides[key]
            display_name = occ_list[0][1]
            wd_sources = ", ".join(src for src, _ in occ_list if src != LOOSE_LABEL)
            out(f"  {display_name}")
            out(t("in_archives", lang, sources=wd_sources))
            out(t("and_as_loose_file", lang, path=(game_dir_path / display_name.replace(chr(92), '/'))))
            out()
            for src, orig in occ_list:
                csv_rows.append((display_name, src, orig))

    if csv_path:
        import csv as csv_mod
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv_mod.writer(f)
            writer.writerow(t("csv_header_row", lang).split(","))
            writer.writerows(csv_rows)
            if stray_wd_files:
                writer.writerow([])
                writer.writerow([t("csv_stray_section_title", lang)])
                for p in stray_wd_files:
                    try:
                        display = p.relative_to(game_dir_path)
                    except ValueError:
                        display = p
                    writer.writerow([str(display)])
        out(t("csv_saved", lang, path=csv_path))

    if output_txt and output_txt != "-":
        with open(output_txt, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines) + "\n")
        out(t("txt_saved", lang, path=output_txt))

    return True


def launch_gui(
    *,
    wdfiles_dir: str = "WDFiles",
    game_dir: str = ".",
    case_sensitive: bool = False,
    no_loose_check: bool = False,
    no_stray_check: bool = False,
    csv_path: str = "",
    output_txt: str = "wd_debugger_report.txt",
    lang: str = DEFAULT_LANG,
) -> None:
    """Otwiera okno GUI (tkinter) z logiem na zywo, formularzem parametrow
    i przelacznikiem jezyka PL/EN."""
    import queue
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    lang_state = {"lang": lang if lang in ("pl", "en") else DEFAULT_LANG}
    # lista (widget, klucz_tekstu) do zywej aktualizacji przy zmianie jezyka
    translatable: list[tuple[tk.Widget, str]] = []

    root = tk.Tk()
    root.title(t("window_title", lang_state["lang"]))
    root.geometry("880x650")

    log_queue: "queue.Queue[str]" = queue.Queue()
    is_running = {"flag": False}

    # --- pasek jezyka ---
    lang_bar = ttk.Frame(root, padding=(8, 8, 8, 0))
    lang_bar.pack(fill="x")
    lang_label = ttk.Label(lang_bar, text=t("label_language", lang_state["lang"]))
    lang_label.pack(side="left", padx=(0, 6))
    translatable.append((lang_label, "label_language"))

    lang_var = tk.StringVar(value=lang_state["lang"].upper())
    lang_combo = ttk.Combobox(lang_bar, textvariable=lang_var, values=["PL", "EN"],
                               state="readonly", width=5)
    lang_combo.pack(side="left")

    # --- formularz parametrow ---
    form = ttk.Frame(root, padding=8)
    form.pack(fill="x")

    def add_path_row(row: int, key: str, var: tk.StringVar, is_save_dialog: bool = False) -> None:
        label = ttk.Label(form, text=t(key, lang_state["lang"]))
        label.grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
        translatable.append((label, key))

        entry = ttk.Entry(form, textvariable=var, width=60)
        entry.grid(row=row, column=1, sticky="we", pady=2)

        def browse() -> None:
            if is_save_dialog:
                default_name = t("default_report_filename", lang_state["lang"])
                path = filedialog.asksaveasfilename(defaultextension=".txt",
                                                     initialfile=Path(var.get() or default_name).name)
            else:
                path = filedialog.askdirectory(initialdir=var.get() or ".")
            if path:
                var.set(path)

        browse_btn = ttk.Button(form, text=t("button_browse", lang_state["lang"]), command=browse)
        browse_btn.grid(row=row, column=2, padx=(6, 0), pady=2)
        translatable.append((browse_btn, "button_browse"))

    form.columnconfigure(1, weight=1)

    var_wdfiles = tk.StringVar(value=wdfiles_dir)
    var_gamedir = tk.StringVar(value=game_dir)
    var_csv = tk.StringVar(value=csv_path)
    var_txt = tk.StringVar(value=output_txt)
    var_case = tk.BooleanVar(value=case_sensitive)
    var_loose = tk.BooleanVar(value=not no_loose_check)
    var_stray = tk.BooleanVar(value=not no_stray_check)

    add_path_row(0, "label_wdfiles_dir", var_wdfiles)
    add_path_row(1, "label_game_dir", var_gamedir)
    add_path_row(2, "label_csv", var_csv, is_save_dialog=True)
    add_path_row(3, "label_txt", var_txt, is_save_dialog=True)

    checks = ttk.Frame(form)
    checks.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))
    chk_case = ttk.Checkbutton(checks, text=t("check_case_sensitive", lang_state["lang"]), variable=var_case)
    chk_case.pack(side="left", padx=(0, 12))
    translatable.append((chk_case, "check_case_sensitive"))
    chk_loose = ttk.Checkbutton(checks, text=t("check_loose", lang_state["lang"]), variable=var_loose)
    chk_loose.pack(side="left", padx=(0, 12))
    translatable.append((chk_loose, "check_loose"))
    chk_stray = ttk.Checkbutton(checks, text=t("check_stray", lang_state["lang"]), variable=var_stray)
    chk_stray.pack(side="left")
    translatable.append((chk_stray, "check_stray"))

    # --- log ---
    log_widget = scrolledtext.ScrolledText(root, wrap="word", font=("Consolas", 10), state="disabled")
    log_widget.pack(fill="both", expand=True, padx=8, pady=8)
    log_widget.tag_configure("blad", foreground="#c0392b")

    def append_log(line: str) -> None:
        log_widget.configure(state="normal")
        if _is_error_line(line):
            log_widget.insert("end", line + "\n", "blad")
        else:
            log_widget.insert("end", line + "\n")
        log_widget.see("end")
        log_widget.configure(state="disabled")

    # --- pasek statusu i przycisk ---
    bottom = ttk.Frame(root, padding=(8, 0, 8, 8))
    bottom.pack(fill="x")
    status_var = tk.StringVar(value=t("status_ready", lang_state["lang"]))
    ttk.Label(bottom, textvariable=status_var).pack(side="left")

    def worker(params: dict) -> None:
        def thread_log(line: str = "") -> None:
            log_queue.put(line)

        try:
            run_analysis(
                wdfiles_dir=params["wdfiles_dir"],
                game_dir=params["game_dir"],
                case_sensitive=params["case_sensitive"],
                no_loose_check=params["no_loose_check"],
                no_stray_check=params["no_stray_check"],
                csv_path=params["csv_path"] or None,
                output_txt=params["output_txt"] or None,
                log=thread_log,
                lang=params["lang"],
            )
        except Exception as e:  # zabezpieczenie, zeby watek nigdy nie ubil GUI cicho
            log_queue.put(t("unexpected_exception", params["lang"], err=e))
        finally:
            log_queue.put(None)  # sygnal konca

    def poll_queue() -> None:
        try:
            while True:
                item = log_queue.get_nowait()
                if item is None:
                    is_running["flag"] = False
                    run_button.configure(state="normal")
                    status_var.set(t("status_done", lang_state["lang"]))
                else:
                    append_log(item)
        except queue.Empty:
            pass
        root.after(80, poll_queue)

    def on_run() -> None:
        if is_running["flag"]:
            return
        log_widget.configure(state="normal")
        log_widget.delete("1.0", "end")
        log_widget.configure(state="disabled")

        params = {
            "wdfiles_dir": var_wdfiles.get(),
            "game_dir": var_gamedir.get(),
            "case_sensitive": var_case.get(),
            "no_loose_check": not var_loose.get(),
            "no_stray_check": not var_stray.get(),
            "csv_path": var_csv.get(),
            "output_txt": var_txt.get(),
            "lang": lang_state["lang"],
        }
        is_running["flag"] = True
        run_button.configure(state="disabled")
        status_var.set(t("status_running", lang_state["lang"]))
        threading.Thread(target=worker, args=(params,), daemon=True).start()

    run_button = ttk.Button(bottom, text=t("button_run", lang_state["lang"]), command=on_run)
    run_button.pack(side="right")
    translatable.append((run_button, "button_run"))

    def apply_language(new_lang: str) -> None:
        lang_state["lang"] = new_lang
        root.title(t("window_title", new_lang))
        for widget, key in translatable:
            widget.configure(text=t(key, new_lang))
        if not is_running["flag"]:
            status_var.set(t("status_ready", new_lang))

    def on_lang_change(_event=None) -> None:
        apply_language(lang_var.get().lower())

    lang_combo.bind("<<ComboboxSelected>>", on_lang_change)

    root.after(80, poll_queue)
    root.mainloop()


if __name__ == "__main__":
    raise SystemExit(main())
