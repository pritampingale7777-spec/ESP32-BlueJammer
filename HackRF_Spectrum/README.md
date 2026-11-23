# HackRF Full-Spectrum Scanner (1 MHz - 6 GHz)

Receive-only GUI for a HackRF One. It runs `hackrf_sweep` and shows a live
trace, a max-hold trace, a top-15 peak table, and CSV export.

## Requirements
- HackRF One
- HackRF host tools with `hackrf_sweep` on PATH
  (Windows: https://github.com/greatscottgadgets/hackrf/releases, then add the `bin` folder to PATH)
- Python 3.9+ with Tkinter

## Run
```
python hackrf_spectrum.py
```

## Settings
| Setting | Meaning |
|---|---|
| Start / Stop (MHz) | Range, between 1 and 6000 MHz |
| Bin (Hz) | FFT bin width, minimum 2445 Hz. Smaller = finer, slower |
| LNA | Front-end gain: 0, 8, 16, 24, 32 or 40 dB |
| VGA | Baseband gain: even values 0-62 |
| RF amp | Adds about 14 dB. Use only with weak signals |
| Antenna power | Sends 3.3 V to the antenna port. Leave off unless your active antenna needs it |

## Notes
- The lowest frequency is 1 MHz. HackRF One cannot tune to 1 Hz.
- Levels are relative dB from `hackrf_sweep`, not calibrated power.
- Save CSV writes `freq_hz, latest_db, maxhold_db`.

## Study / monitoring (`spectrum_monitor.py`)
Logs the spectrum over time and reports how often each common band is occupied
(percent of bins above a dB threshold). It records activity only and does not
track individual transmissions.

```
python spectrum_monitor.py --log band_log.csv --threshold -60 --interval 30
python spectrum_monitor.py --start 400 --stop 1000 --duration 3600 --log ism.csv
```

`--threshold` is in uncalibrated dB, so tune it to your noise floor first.

## Install on Windows
1. Install Python 3.9+ from https://www.python.org/downloads/ and tick **Add python.exe to PATH**.
   In the Python installer, keep **tcl/tk and IDLE** enabled (needed for the GUI).
2. Download the HackRF host tools from https://github.com/greatscottgadgets/hackrf/releases,
   extract them, and add the folder that contains `hackrf_sweep.exe` to your PATH.
3. Keep `install_windows.bat`, `hackrf_spectrum.py`, `spectrum_monitor.py` and `README.md` in one folder.
4. Double-click `install_windows.bat`. It copies the files to `%LOCALAPPDATA%\HackRF_Spectrum`,
   creates launchers and a desktop shortcut, and checks for `hackrf_sweep`.

To uninstall, delete the `%LOCALAPPDATA%\HackRF_Spectrum` folder and the desktop shortcut.
