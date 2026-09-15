# WD Debugger

Narzędzie do analizy archiwów `.wd` używanych przez gry `Reality Pump`. Szuka elementów (plików), które występują w więcej niż jednym archiwum `.wd` - czyli potencjalnych duplikatów lub nadpisań - a także sprawdza, czy w katalogu gry nie ma luźnych (wypakowanych) plików nadpisujących zawartość archiwów.

Program czyta wyłącznie **central directory** każdego pliku `.wd` (listę elementów wraz z metadanymi), bez rozpakowywania samej zawartości archiwów - dzięki temu analiza jest szybka nawet dla dużej liczby plików.

## Funkcje

- Wykrywanie elementów występujących w wielu archiwach `.wd` (duplikaty).
- Wykrywanie luźnych plików w katalogu gry, które nadpisują zawartość archiwów.
- Wykrywanie plików `.wd` leżących poza katalogiem `WDFiles`.
- Raport tekstowy (`.txt`) oraz opcjonalny eksport do CSV.
- Tryb graficzny (GUI, Tkinter) z podglądem logu na żywo.
- Interfejs dwujęzyczny: polski i angielski (`--lang pl` / `--lang en`).
- Porównywanie nazw bez rozróżniania wielkości liter (domyślnie) lub z rozróżnianiem (`--case-sensitive`).

## Wymagania

- Python 3.10+ (używa `from __future__ import annotations` oraz nowoczesnego typowania)
- Biblioteka standardowa - brak zewnętrznych zależności
- Do trybu GUI: `tkinter` (w większości dystrybucji Pythona dostępny domyślnie)

## Instalacja

Nie jest wymagana żadna instalacja - wystarczy pobrać/sklonować repozytorium i uruchomić skrypt Pythonem.

```bash
git clone https://github.com/A-t-l-as/WD_Debugger.git
cd WD_Debugger
```

## Użycie

Program uruchamia się z katalogu gry (tam, gdzie znajduje się podkatalog `WDFiles`):

```bash
python wd_debugger.py
```

### Tryb GUI

Na Windows można też skorzystać z dołączonych skryptów uruchomieniowych:

```
RUN_WD_DBG_GUI.bat
```

lub

```powershell
./RUN_WD_DBG_GUI.ps1
```

Albo bezpośrednio:

```bash
python wd_debugger.py --gui
```

### Najważniejsze opcje CLI

| Opcja | Opis |
|---|---|
| `--wdfiles-dir KATALOG` | katalog z plikami `.wd` (domyślnie `WDFiles` obok programu) |
| `--game-dir KATALOG` | katalog główny gry, sprawdzany pod kątem luźnych plików (domyślnie katalog bieżący) |
| `--no-loose-check` | pomiń sprawdzanie luźnych plików w katalogu gry |
| `--no-stray-check` | pomiń szukanie plików `.wd` leżących poza `WDFiles` |
| `--case-sensitive` | porównuj nazwy z rozróżnieniem wielkości liter |
| `--csv PLIK` | dodatkowo zapisz raport duplikatów do CSV |
| `--output-txt PLIK` | plik `.txt` z pełnym raportem (domyślnie `wd_debugger_report.txt`, `-` wyłącza zapis) |
| `--gui` | uruchamia tryb graficzny |
| `--lang {pl,en}` | język programu (domyślnie `pl`) |

Przykład z pełną konfiguracją:

```bash
python wd_debugger.py --game-dir "D:\Gry\KnightShift" --csv duplikaty.csv --output-txt raport.txt --lang en
```

## Format pliku .wd

Format archiwum został odtworzony na podstawie źródeł projektu **[EarthTool](https://github.com/Arkezar/EarthTool)** autorstwa **Arkezara** (licencja MIT), a konkretnie klas `ArchiveFactory.cs` i `Archive.cs`.

## Podziękowania

Ogromne podziękowania dla **[Arkezara](https://github.com/Arkezar)** za projekt **[EarthTool](https://github.com/Arkezar/EarthTool)** - to dzięki jego pracy nad formatem `.wd` ten program mógł w ogóle powstać.

## Licencja

[MIT](LICENSE)

---

# WD Debugger (English)

A tool for analyzing `.wd` archives used by **Reality Pump** games. It looks for items (files) that occur in more than one `.wd` archive - i.e. potential duplicates or overwrites - and also checks whether the game directory contains any loose (unpacked) files that override the contents of the archives.

The program reads only the **central directory** of each `.wd` file (the list of items along with their metadata), without extracting the actual archive contents - this makes the analysis fast even for a large number of files.

## Features

- Detecting items that occur in multiple `.wd` archives (duplicates).
- Detecting loose files in the game directory that override archive contents.
- Detecting `.wd` files located outside the `WDFiles` directory.
- Text report (`.txt`) with optional CSV export.
- Graphical mode (GUI, Tkinter) with a live log preview.
- Bilingual interface: Polish and English (`--lang pl` / `--lang en`).
- Case-insensitive name comparison (default) or case-sensitive (`--case-sensitive`).

## Requirements

- Python 3.10+ (uses `from __future__ import annotations` and modern typing)
- Standard library only - no external dependencies
- For GUI mode: `tkinter` (available by default in most Python distributions)

## Installation

No installation is required - just download/clone the repository and run the script with Python.

```bash
git clone https://github.com/A-t-l-as/WD_Debugger.git
cd WD_Debugger
```

## Usage

Run the program from the game directory (the one containing the `WDFiles` subdirectory):

```bash
python wd_debugger.py
```

### GUI mode

On Windows you can also use the included launcher scripts:

```
RUN_WD_DBG_GUI.bat
```

or

```powershell
./RUN_WD_DBG_GUI.ps1
```

Or directly:

```bash
python wd_debugger.py --gui
```

### Main CLI options

| Option | Description |
|---|---|
| `--wdfiles-dir DIR` | directory containing `.wd` files (default: `WDFiles` next to the program) |
| `--game-dir DIR` | main game directory, checked for loose files (default: current directory) |
| `--no-loose-check` | skip checking for loose files in the game directory |
| `--no-stray-check` | skip searching for `.wd` files located outside `WDFiles` |
| `--case-sensitive` | compare names with case sensitivity |
| `--csv FILE` | additionally save the duplicates report to CSV |
| `--output-txt FILE` | `.txt` file with the full report (default: `wd_debugger_report.txt`, `-` disables saving) |
| `--gui` | launches the graphical mode |
| `--lang {pl,en}` | program language (default: `pl`) |

Full configuration example:

```bash
python wd_debugger.py --game-dir "D:\Games\KnightShift" --csv duplicates.csv --output-txt report.txt --lang en
```

## .wd file format

The archive format was reconstructed based on the sources of the **[EarthTool](https://github.com/Arkezar/EarthTool)** project by **Arkezar** (MIT license), specifically the `ArchiveFactory.cs` and `Archive.cs` classes.

## Acknowledgements

Huge thanks to **[Arkezar](https://github.com/Arkezar)** for the **[EarthTool](https://github.com/Arkezar/EarthTool)** project - it's thanks to his work on the `.wd` format that this program could exist at all.

## License

[MIT](LICENSE)
