# WFPC

In-game price checker for Warframe relic rewards.

WFPC captures the relic reward screen, reads the item names with OCR, and shows current best buy prices from [warframe.market](https://warframe.market) — so you can pick the most valuable reward before the timer runs out.

## What it does

- Runs as a normal desktop window for setup and viewing results
- Switches to a small floating **In Game** panel (top-right) so you can capture without leaving the game
- Captures the center region of your game's monitor automatically — no manual region drawing
- Reads item names from the screenshot with OCR (RapidOCR, bundled — no external engine to install)
- Matches recognized text against all known prime items, in two passes so names that wrapped onto two lines still match
- Displays the price for each reward item, plus a panel of top-value items from the loaded data
- After a capture, automatically flips back to the In Game panel after ~30 seconds, ready for the next relic

## How to use

1. Launch WFPC and click **Refresh** to pull current prices from warframe.market (takes a few minutes on first run; cached afterward).
2. Click **In Game** to shrink down to the minimal top-right panel. On a multi-monitor setup you'll be asked which screen your game is on (remembered for next time).
3. When the relic rewards appear, click **Capture** on the panel.
4. The full window returns with the price for each reward item and a top-items panel. After ~30s it auto-switches back to the In Game panel for your next run — or click **Cancel** on the In Game button during the countdown to stay put.

## Setup

### Requirements

- Python 3
- Windows (the capture and in-game flow are built around a PC Warframe setup)

No external OCR engine is needed — RapidOCR bundles its models and runs on onnxruntime, both pulled in by pip.

### Install

```
pip install -r requirements.txt
```

### Run

```
python main.py
```

## Built with

- **RapidOCR** (onnxruntime) — screen text recognition
- **warframe.market API** — live pricing data
- **Tkinter** — desktop UI and in-game panel
- **mss** — screen capture
- **Pillow** / **NumPy** — image handling

## Building the Windows executable (maintainer notes)

Notes to self for cutting a downloadable `WFPC.exe`. Must be done on Windows
(PyInstaller can't cross-compile from macOS/Linux).

```
git pull
build-env\Scripts\activate          # or create once: python -m venv build-env
pip install -r requirements.txt     # catches any new/updated deps
pip install pyinstaller             # first time only

pyinstaller --noconfirm --clean --onefile --windowed --name WFPC --collect-all rapidocr_onnxruntime --collect-all onnxruntime main.py
```

(PowerShell uses backtick `` ` `` for line breaks instead of `^`, or just put it
all on one line. After the first build you can reuse the generated spec with
`pyinstaller WFPC.spec`.)

The two `--collect-all` flags are essential — they bundle RapidOCR's ONNX models
and the onnxruntime DLLs. Without them the exe launches but crashes on first OCR.

The result is `dist\WFPC.exe`. Smoke-test it (Refresh + one capture), ideally on
a machine without Python, then attach it to a tagged GitHub release.

