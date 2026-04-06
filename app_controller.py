import mss
import time
import threading
from PIL import Image
from datetime import datetime

from read_ss import extract_words
from market_data import (
    fetch_all_prices, save_cache, load_cache,
    find_sets_from_words,
)


class AppController:
    """
    The 'brain' of the app. Coordinates the capture → OCR → lookup
    pipeline and manages market data state. Calls back into the GUI
    (self.gui) to update the display — the controller never creates
    or modifies widgets directly.
    """

    def __init__(self, gui):
        # Reference to the GUI window so we can call its display methods
        self.gui = gui

        # Market data cache (loaded from JSON or fetched fresh)
        self.market_data = None

        # The most recently captured screenshot (PIL Image)
        self.captured_image = None

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
            # Show just the date portion of the timestamp
            date_str = timestamp[:10] if len(timestamp) >= 10 else timestamp

            # Check if the cache is older than 7 days and warn the user
            try:
                cache_time = datetime.fromisoformat(timestamp)
                age_days = (datetime.now() - cache_time).days
                if age_days >= 7:
                    # ⚠ caution symbol + yellow text to draw attention
                    self.gui.update_status(
                        f"\u26A0 {num_sets} sets loaded ({date_str}) \u2014 {age_days}d old",
                        "yellow"
                    )
                else:
                    self.gui.update_status(f"{num_sets} sets loaded ({date_str})", "green")
            except (ValueError, TypeError):
                # If the timestamp is malformed, just show it normally
                self.gui.update_status(f"{num_sets} sets loaded ({date_str})", "green")

            print(f"Loaded cached market data: {num_sets} sets from {date_str}")
        else:
            self.gui.update_status("No data \u2014 click Refresh Data", "red")

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
            # Schedule UI update on the main thread via tkinter's after()
            self.gui.after(0, lambda c=current, t=total: self.gui.update_status(
                f"Loading: {c}/{t}", "yellow"
            ))

        try:
            cache = fetch_all_prices(progress_callback=update_progress)
            save_cache(cache)
            # Schedule the final UI update on the main thread
            self.gui.after(0, lambda: self._on_data_loaded(cache))
        except Exception as e:
            self.gui.after(0, lambda: self._on_data_error(str(e)))

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
    # SCREENSHOT CAPTURE — hide window, grab screen, restore window
    # =========================================================================

    def capture_screenshot(self):
        """
        Capture the screen region behind the GUI's transparent area.
        Uses try/finally to guarantee the window always comes back,
        even if the screenshot fails. Disables the capture button
        to prevent double-click race conditions.
        """
        self.gui.set_capture_busy(True)

        # Finalize layout so winfo coordinates are accurate
        self.gui.update_idletasks()

        # Get the screen-absolute position and size of the capture region
        cap_x, cap_y, cap_w, cap_h = self.gui.get_capture_geometry()

        # Hide the window so we capture the game underneath, not ourselves.
        # The try/finally ensures the window always comes back.
        self.gui.withdraw()
        self.gui.update()
        time.sleep(0.15)  # small delay for the OS to finish hiding the window

        try:
            # Grab the screen region where our transparent area was
            with mss.mss() as sct:
                region = {
                    "left": cap_x,
                    "top": cap_y,
                    "width": cap_w,
                    "height": cap_h,
                }
                raw = sct.grab(region)
                img = Image.frombytes("RGB", raw.size, raw.rgb)
        finally:
            # No matter what happens above, bring the window back
            self.gui.deiconify()
            self.gui.update()
            self.gui.set_capture_busy(False)

        # Store the captured image and show it in the capture area
        self.captured_image = img
        self.gui.show_captured_image(img, cap_w, cap_h)
        print(f"Captured {cap_w}x{cap_h} region at ({cap_x}, {cap_y})")

        # Run OCR and look up prices if market data is loaded
        if self.market_data:
            self._process_screenshot(img)
        else:
            self.gui.show_message("No market data loaded.\nClick 'Refresh Data' first.")

    # =========================================================================
    # OCR + LOOKUP — extract words, match to sets, send results to GUI
    # =========================================================================

    def _process_screenshot(self, pil_image):
        """Run OCR on the captured image and display matching set prices."""
        # Extract words from the screenshot via OCR
        words = extract_words(pil_image)
        print(f"OCR words: {words}")

        # Find which prime sets match any of the OCR words
        matches = find_sets_from_words(self.market_data, words)

        if matches:
            self.gui.display_results(matches)
        else:
            self.gui.show_message(
                "No prime items recognized.\n"
                f"OCR read: {' '.join(words[:15])}"
            )

    # =========================================================================
    # CLEAR — reset the capture region
    # =========================================================================

    def clear_capture(self):
        """Reset the capture state and tell the GUI to go back to transparent."""
        self.captured_image = None
        self.gui.reset_capture_region()
        self.gui.show_message("Take a screenshot to look up prices.")