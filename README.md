# WFPC

In-game price checker for Warframe relic rewards.

WFPC is a desktop overlay that captures the relic reward screen, reads item names with OCR, and displays current best buy prices from [warframe.market](https://warframe.market) — all without leaving the game.

## What it does

- Sits on top of your game as a transparent overlay
- Captures the screen region behind the overlay on command
- Reads item names from the screenshot using OCR
- Matches recognized names against all known prime items
- Displays per-part prices and full set prices side by side
- Highlights the best-value option so you can pick quickly

## How to use

1. Launch WFPC and click **Refresh Data** to pull current prices from warframe.market (takes a few minutes on first run; cached afterward).
2. Position the transparent capture region over the relic reward area in-game.
3. Click **Capture** when rewards appear.
4. Prices show up in the overlay — part breakdowns, set prices, and the best pick highlighted.

## Setup

### Requirements

- Python 3
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed and on your PATH
- Windows (uses transparent window overlay and screen capture)

### Install

```
pip install -r requirements.txt
```

### Run

```
python main.py
```

## Built with

- **Tesseract OCR** + **OpenCV** — screen reading and image processing
- **warframe.market API** — live pricing data
- **Tkinter** — overlay UI
- **mss** — screen capture