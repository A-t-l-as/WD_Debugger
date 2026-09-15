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
