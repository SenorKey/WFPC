import mss
import threading
from PIL import Image
from datetime import datetime

from read_ss import extract_words
from market_data import (
    fetch_all_prices,
    save_cache,
    load_cache,
    find_sets_from_words,
)


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

    # =========================================================================
    # MARKET DATA — loading, fetching, and cache staleness
    # =========================================================================

    def load_cached_data(self):
        """
        Try to load market data from the local JSON cache file.
        If the cache is older than 7 days, tell the GUI to show
        a yellow warning so the user knows prices may be stale.
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

    def _on_data_error(self, error_msg):
        """Called on the main thread if data fetch fails."""
        self.gui.set_refresh_busy(False)
        self.gui.update_status(f"Error: {error_msg[:30]}", "red")

    # =========================================================================
    # REGION DEFINITION — let the user draw a rectangle on screen
    # =========================================================================

    def define_region(self):
        """
        Hide the main GUI and open the fullscreen region selector.
        The user drags a rectangle to define the capture area, then
        accepts or cancels. The GUI reappears in either case.
        """
        self.gui.withdraw()
        self.gui.update()
        # Brief delay so the OS finishes hiding the window before
        # we screenshot the desktop for the selector backdrop
        self.gui.after(200, self._open_region_selector)

    def _open_region_selector(self):
        """Create the region selector overlay (called after the GUI hides)."""
        self.gui.show_region_selector(self._on_region_defined)

    def _on_region_defined(self, region):
        """
        Callback from the region selector. Receives (x, y, w, h) in
        absolute screen coordinates, or None if the user cancelled.
        """
        if region:
            self.capture_region = region
            x, y, w, h = region
            self.gui.update_region_display(
                f"Region: {w}\u00d7{h} at ({x}, {y})", defined=True
            )
            print(f"Capture region defined: {w}x{h} at ({x}, {y})")
        # Bring back the main window whether they accepted or cancelled
        self.gui.deiconify()
        self.gui.update()

    # =========================================================================
    # IN-GAME MODE — minimal floating buttons during gameplay
    # =========================================================================

    def enter_in_game_mode(self):
        """
        Switch to in-game mode: hide the main GUI and show a small
        floating panel with Capture and Back buttons. Requires a
        capture region to be defined first.
        """
        if not self.capture_region:
            self.gui.show_message(
                "No capture region defined.\n"
                "Click 'Region' to define the area first."
            )
            return

        self.gui.withdraw()
        self.gui.update()
        self.gui.show_in_game_overlay(
            on_capture=self._in_game_capture,
            on_back=self._exit_in_game_mode,
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

    def _exit_in_game_mode(self):
        """Leave in-game mode and restore the main GUI."""
        self.gui.deiconify()
        self.gui.update()

    # =========================================================================
    # SCREENSHOT CAPTURE — grab the stored screen region
    # =========================================================================

    def capture_screenshot(self):
        """
        Capture the stored screen region from the normal GUI.
        Hides the window briefly in case it overlaps the capture area,
        grabs the screenshot, then shows the window again with results.
        """
        if not self.capture_region:
            self.gui.show_message(
                "No capture region defined.\n"
                "Click 'Region' to define the area first."
            )
            return

        self.gui.set_capture_busy(True)
        self.gui.withdraw()
        self.gui.update()
        # Schedule capture after the window disappears
        self.gui.after(200, self._do_normal_capture)

    def _do_normal_capture(self):
        """Perform the capture from normal mode and restore the GUI."""
        self._do_capture()
        self.gui.deiconify()
        self.gui.update()
        self.gui.set_capture_busy(False)

    def _do_capture(self):
        """
        Core capture logic shared by both normal and in-game modes.
        Grabs the stored screen region with mss, then runs the
        OCR + lookup pipeline if market data is available.
        """
        x, y, w, h = self.capture_region

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
        """Run OCR on the captured image and display matching set prices."""
        words = extract_words(pil_image)
        print(f"OCR words: {words}")

        matches = find_sets_from_words(self.market_data, words)

        if matches:
            self.gui.display_results(matches)
        else:
            self.gui.show_message(
                "No prime items recognized.\n" f"OCR read: {' '.join(words[:15])}"
            )

    # =========================================================================
    # CLEAR — reset the results display
    # =========================================================================

    def clear_capture(self):
        """Reset the capture state and clear the results panel."""
        self.captured_image = None
        self.gui.show_message("Take a screenshot to look up prices.")
