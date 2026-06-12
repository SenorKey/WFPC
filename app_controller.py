import json
import os
import mss
import threading
from PIL import Image
from datetime import datetime

from read_ss import read_boxes, draw_boxes
from market_data import (
    fetch_all_prices,
    save_cache,
    load_cache,
    find_items_from_boxes,
    top_priced_parts,
)


REGION_CACHE_FILE = "region_cache.json"

# When True, every capture pops up a window showing the detected OCR text
# boxes drawn over the captured region. Handy for tuning/testing how
# RapidOCR is reading the screen; set to False for normal use.
OCR_DEBUG = False

# Fraction of the screen to crop off the top and bottom when auto-computing
# the capture region. The relic reward names sit in a band across the middle
# of the screen, so we keep the middle 60% of the height at full width.
CROP_TOP = 0.20
CROP_BOTTOM = 0.20

# After an in-game capture, how long (in milliseconds) to leave the full
# results window up before automatically flipping back to the minimal
# top-right overlay, ready for the next relic reward screen. Only applies
# to captures triggered from the in-game overlay, not the main window.
AUTO_INGAME_DELAY_MS = 30000

# How long (in milliseconds) the on-screen box drawn around the
# highest-priced reward stays up after a capture before removing itself.
HIGHLIGHT_DURATION_MS = 8000


class AppController:
    """
    The 'brain' of the app. Coordinates the capture -> OCR -> lookup
    pipeline and manages market data state. Calls back into the GUI
    (self.gui) to update the display — the controller never creates
    or modifies widgets directly.

    The capture workflow uses stored screen coordinates (defined once
    via the region selector) rather than reading geometry from a
    transparent overlay. This allows the GUI to be a normal window
    and supports an in-game mode where only a small floating panel
    is visible during gameplay.
    """

    def __init__(self, gui):
        # Reference to the GUI window so we can call its display methods
        self.gui = gui

        # Market data cache (loaded from JSON or fetched fresh)
        self.market_data = None

        # The most recently captured screenshot (PIL Image)
        self.captured_image = None

        # Stored capture region as (x, y, width, height) in absolute
        # screen coordinates. Set via the region selector overlay.
        self.capture_region = None

        # The mss monitor dict for the screen the user selected when
        # defining their capture region. Used to position the in-game
        # overlay on the correct monitor.
        self.capture_monitor = None

        # Timestamp (ISO 8601 string) for when the current capture
        # region was defined. Persisted alongside the coordinates so
        # the user can see how old their saved region is.
        self.region_timestamp = None

    # =========================================================================
    # MARKET DATA — loading, fetching, and cache staleness
    # =========================================================================

    def load_cached_data(self):
        """
        Try to load market data from the local JSON cache file.
        If the cache is older than 7 days, tell the GUI to show
        a yellow warning so the user knows prices may be stale.

        Also restores the saved capture region (if any) so the user
        doesn't have to redefine it every session.
        """
        cache = load_cache()
        if cache:
            self.market_data = cache
            num_sets = len(cache["sets"])
            timestamp = cache.get("timestamp", "unknown")
            date_str = timestamp[:10] if len(timestamp) >= 10 else timestamp

            # Check if the cache is older than 7 days and warn the user
            try:
                cache_time = datetime.fromisoformat(timestamp)
                age_days = (datetime.now() - cache_time).days
                if age_days >= 7:
                    self.gui.update_status(
                        f"\u26a0 {num_sets} sets loaded ({date_str}) \u2014 {age_days}d old",
                        "yellow",
                    )
                else:
                    self.gui.update_status(
                        f"{num_sets} sets loaded ({date_str})", "green"
                    )
            except (ValueError, TypeError):
                self.gui.update_status(f"{num_sets} sets loaded ({date_str})", "green")

            print(f"Loaded cached market data: {num_sets} sets from {date_str}")
        else:
            self.gui.update_status("No data \u2014 click Refresh", "red")

        # Populate the always-visible top-items panel from the cache
        # (shows a placeholder if no data was loaded).
        self._refresh_top_items()

        # Restore saved capture region if one exists. Done before the
        # suggested-highlight update so the next-step logic sees the
        # restored region and suggests "In Game" rather than "Region".
        self._load_region()

        # Set the initial button highlight based on current state
        self._update_suggested_highlight()

    def refresh_data(self):
        """
        Kick off a background thread to fetch fresh prices from
        warframe.market. Disables the refresh button while running,
        updates the status bar with progress, and re-enables when done.
        """
        self.gui.set_refresh_busy(True)
        self.gui.update_status("Fetching prices...", "yellow")

        thread = threading.Thread(target=self._fetch_data_thread, daemon=True)
        thread.start()

    def _fetch_data_thread(self):
        """Background thread that fetches all prices (takes a few minutes)."""

        def update_progress(current, total, name):
            self.gui.after(
                0,
                lambda c=current, t=total: self.gui.update_status(
                    f"Loading: {c}/{t}", "yellow"
                ),
            )

        try:
            cache = fetch_all_prices(progress_callback=update_progress)
            save_cache(cache)
            self.gui.after(0, lambda: self._on_data_loaded(cache))
        except Exception as e:
            err_msg = str(e)
            self.gui.after(0, lambda: self._on_data_error(err_msg))

    def _on_data_loaded(self, cache):
        """Called on the main thread when data fetch completes."""
        self.market_data = cache
        num_sets = len(cache["sets"])
        self.gui.set_refresh_busy(False)
        self.gui.update_status(f"{num_sets} sets loaded (fresh)", "green")
        self._refresh_top_items()
        self._update_suggested_highlight()

    def _on_data_error(self, error_msg):
        """Called on the main thread if data fetch fails."""
        self.gui.set_refresh_busy(False)
        self.gui.update_status(f"Error: {error_msg[:30]}", "red")
        self._update_suggested_highlight()

    def _refresh_top_items(self):
        """
        Recompute the highest-priced individual parts from the current
        cache and push them to the always-visible top-items panel.
        Passes an empty list when no data is loaded so the panel shows
        its placeholder.
        """
        if not self.market_data:
            self.gui.update_top_items([])
            return
        self.gui.update_top_items(top_priced_parts(self.market_data, n=15))

    # =========================================================================
    # SUGGESTED HIGHLIGHT — guide the user through the setup flow
    # =========================================================================

    def _data_is_stale(self):
        """
        Check if cached market data is older than 5 days.
        Returns True if no data exists or if the timestamp is too old.
        """
        if not self.market_data:
            return True
        timestamp = self.market_data.get("timestamp", "")
        try:
            cache_time = datetime.fromisoformat(timestamp)
            return (datetime.now() - cache_time).days >= 5
        except (ValueError, TypeError):
            # Timestamp is malformed — data exists but age is unknown,
            # don't force a refresh just because of a bad timestamp
            return False

    def _update_suggested_highlight(self):
        """
        Evaluate the current app state and highlight the single button
        that represents the most logical next step for the user.

        Priority order:
          1. Refresh — if no market data or data is older than 5 days
          2. In Game — once data is ready (the capture region is figured
             out automatically, so there's no separate region step)
        """
        if not self.market_data or self._data_is_stale():
            self.gui.highlight_suggested("refresh")
        else:
            self.gui.highlight_suggested("ingame")

    # =========================================================================
    # CAPTURE REGION — auto center-crop of the chosen monitor
    # =========================================================================

    def _center_region(self, monitor):
        """
        Compute an (x, y, w, h) capture region covering the center band of
        the given mss monitor: CROP_TOP/CROP_BOTTOM fractions are trimmed
        off, leaving the full-width middle strip where the relic rewards
        appear. Coordinates are absolute (offset by the monitor's left/top)
        so they work directly with mss.grab on any monitor.
        """
        mw, mh = monitor["width"], monitor["height"]
        x = monitor["left"]
        y = monitor["top"] + int(mh * CROP_TOP)
        w = mw
        h = mh - int(mh * CROP_TOP) - int(mh * CROP_BOTTOM)
        return (x, y, w, h)

    def _set_monitor(self, monitor):
        """
        Store the chosen monitor, derive its center capture region, and
        persist the choice so it's remembered next session.
        """
        self.capture_monitor = monitor
        self.capture_region = self._center_region(monitor)
        self.region_timestamp = datetime.now().isoformat()
        self._save_region()

    def _ensure_capture_ready(self, on_ready):
        """
        Make sure a capture monitor + region are set, then run on_ready().

        Single-monitor systems resolve silently. Multi-monitor systems
        show the monitor picker the first time so the user can say which
        screen the game is on; that choice is saved and reused afterwards.
        """
        if self.capture_monitor and self.capture_region:
            on_ready()
            return

        with mss.mss() as sct:
            monitors = sct.monitors[1:]  # skip index 0 (virtual/combined)

        if len(monitors) == 1:
            self._set_monitor(monitors[0])
            on_ready()
        else:

            def picked(monitor):
                if monitor is None:
                    return  # cancelled — stay on the main screen
                self._set_monitor(monitor)
                on_ready()

            self.gui.show_monitor_picker(picked)

    # =========================================================================
    # REGION PERSISTENCE — save/load to JSON between sessions
    # =========================================================================

    def _save_region(self):
        """
        Persist the current capture region, monitor, and timestamp to
        disk so the user doesn't have to redefine the region every time
        they launch the app.
        """
        if not self.capture_region:
            return
        try:
            with open(REGION_CACHE_FILE, "w") as f:
                json.dump(
                    {
                        "region": list(self.capture_region),  # tuple → list for JSON
                        "monitor": self.capture_monitor,
                        "timestamp": self.region_timestamp,
                    },
                    f,
                    indent=2,
                )
            print(f"Region saved to {REGION_CACHE_FILE}")
        except Exception as e:
            print(f"Failed to save region: {e}")

    def _load_region(self):
        """
        Restore the saved capture monitor from disk (if present) and
        recompute the center-crop region from it, so the current crop
        math applies even to choices saved by older versions. Silently
        does nothing if the file is missing or malformed — the monitor
        picker resolves it on first use instead.
        """
        if not os.path.exists(REGION_CACHE_FILE):
            return
        try:
            with open(REGION_CACHE_FILE, "r") as f:
                data = json.load(f)

            self.capture_monitor = data.get("monitor")
            self.region_timestamp = data.get("timestamp")

            if self.capture_monitor:
                self.capture_region = self._center_region(self.capture_monitor)
            elif data.get("region"):
                self.capture_region = tuple(data["region"])

            if self.capture_region:
                x, y, w, h = self.capture_region
                print(f"Restored capture region: {w}x{h} at ({x}, {y})")
        except Exception as e:
            print(f"Failed to load saved region: {e}")

    # =========================================================================
    # IN-GAME MODE — minimal floating buttons during gameplay
    # =========================================================================

    def enter_in_game_mode(self):
        """
        Switch to in-game mode: hide the main GUI and show a small
        floating panel with Capture and Back buttons. Ensures a capture
        monitor/region is set first (prompting the monitor picker on
        multi-monitor systems), then shows the overlay on that monitor.

        Also used as the auto-return target after an in-game capture, so
        we stop any running countdown here to avoid stacking.
        """
        self.gui.stop_ingame_countdown()
        self._ensure_capture_ready(self._show_in_game_overlay)

    def _show_in_game_overlay(self):
        """Hide the main GUI and bring up the in-game capture overlay."""
        self.gui.withdraw()
        self.gui.update()
        self.gui.show_in_game_overlay(
            on_capture=self._in_game_capture,
            on_back=self._exit_in_game_mode,
            monitor=self.capture_monitor,
        )

    def _in_game_capture(self):
        """
        Called when the user clicks Capture on the in-game overlay.
        The overlay has already destroyed itself by this point, so we
        wait briefly for it to disappear, then capture and process.
        """
        # Schedule the actual capture after a short delay so the
        # overlay has time to fully disappear from the screen
        self.gui.after(200, self._do_in_game_capture)

    def _do_in_game_capture(self):
        """Perform the capture and bring back the main GUI with results."""
        self._do_capture()
        self.gui.deiconify()
        self.gui.update()
        self._update_suggested_highlight()

        # Start the auto-return countdown so that, after reviewing the
        # prices, the In Game button ticks down and then flips back to the
        # minimal overlay, ready for the next relic screen without any
        # further clicks. The GUI owns the per-second label updates.
        self.gui.start_ingame_countdown(
            AUTO_INGAME_DELAY_MS // 1000, self.enter_in_game_mode
        )

    def _exit_in_game_mode(self):
        """Leave in-game mode and restore the main GUI."""
        self.gui.stop_ingame_countdown()
        self.gui.deiconify()
        self.gui.update()
        self._update_suggested_highlight()

    # =========================================================================
    # SCREENSHOT CAPTURE — grab the stored screen region
    # =========================================================================

    def _do_capture(self):
        """
        Core capture logic shared by both normal and in-game modes.
        Grabs the stored screen region with mss, then runs the
        OCR + lookup pipeline if market data is available.
        """
        x, y, w, h = self.capture_region

        # A highlight box from the previous capture would be photographed
        # into this one if it were still up — remove it before grabbing.
        self.gui.hide_reward_highlight()

        try:
            with mss.mss() as sct:
                region = {
                    "left": x,
                    "top": y,
                    "width": w,
                    "height": h,
                }
                raw = sct.grab(region)
                img = Image.frombytes("RGB", raw.size, raw.rgb)
        except Exception as e:
            self.gui.show_message(f"Capture failed:\n{str(e)}")
            return

        self.captured_image = img
        print(f"Captured {w}x{h} region at ({x}, {y})")

        # Run OCR and look up prices if market data is loaded
        if self.market_data:
            self._process_screenshot(img)
        else:
            self.gui.show_message("No market data loaded.\nClick 'Refresh' first.")

    # =========================================================================
    # OCR + LOOKUP — extract words, match to sets, send results to GUI
    # =========================================================================

    def _process_screenshot(self, pil_image):
        """Run OCR on the captured image and display matching reward prices."""
        boxes = read_boxes(pil_image)
        box_texts = [text for _box, text, _score in boxes]
        print(f"OCR boxes: {box_texts}")

        # Testing aid: show the detected text boxes drawn over the capture.
        if OCR_DEBUG:
            try:
                self.gui.show_ocr_debug(draw_boxes(pil_image, boxes))
            except Exception as e:
                print(f"OCR debug view failed: {e}")

        # Match detections to specific reward items. Pass the full boxes
        # (not just text) so the matcher can stitch back names that wrapped
        # onto two lines using each box's position.
        items = find_items_from_boxes(self.market_data, boxes)

        if items:
            self._highlight_best_reward(items, pil_image)
            self.gui.display_results(items)
        else:
            self.gui.show_message(
                "No prime items recognized.\n" f"OCR read: {' '.join(box_texts[:6])}"
            )

    def _highlight_best_reward(self, items, pil_image):
        """
        Flash an on-screen box around the highest-priced matched reward
        so the user can spot the best pick in game without reading the
        results window. Uses the same highest-item-buy-price rule as the
        green highlight in the results panel, so the two always agree.

        The OCR bboxes are in capture-image pixels, and the capture is a
        crop of the screen, so mapping back to screen coordinates is the
        capture region's origin plus the box — after dividing out the
        HiDPI scale. (On scaled displays mss returns more pixels than
        the region's nominal size, while Tk positions windows in logical
        points, so image pixels must be converted back to points first.)
        """
        candidates = [
            item for item in items
            if item.get("bbox") is not None and item.get("buy_price") is not None
        ]
        if not candidates:
            return
        best = max(candidates, key=lambda item: item["buy_price"])

        rx, ry, rw, rh = self.capture_region
        scale_x = pil_image.width / rw
        scale_y = pil_image.height / rh

        x0, y0, x1, y1 = best["bbox"]
        self.gui.show_reward_highlight(
            rx + int(x0 / scale_x),
            ry + int(y0 / scale_y),
            max(1, int((x1 - x0) / scale_x)),
            max(1, int((y1 - y0) / scale_y)),
            HIGHLIGHT_DURATION_MS,
        )

    # =========================================================================
    # CLEAR — reset the results display
    # =========================================================================

    def clear_capture(self):
        """Reset the capture state and clear the results panel."""
        self.captured_image = None
        self.gui.show_message("Take a screenshot to look up prices.")
