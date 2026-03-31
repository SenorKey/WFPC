import tkinter as tk
from PIL import Image, ImageTk
import mss
import time
import threading

from read_ss import extract_words
from market_data import (
    fetch_all_prices, save_cache, load_cache,
    find_sets_from_words, break_down_set
)


class WFV74(tk.Tk):
    """
    Main application window with a transparent see-through capture region.
    The user positions this window so the transparent area overlays the
    in-game relic reward screen, then clicks 'Take Screenshot' to capture,
    OCR the item names, and display prices from warframe.market.
    """

    # Windows will render this exact color as fully transparent (see-through)
    TRANSPARENT_COLOR = '#01FF00'

    def __init__(self):
        super().__init__()

        self.title("WFV74")
        self.geometry("750x550")
        self.minsize(400, 400)
        self.configure(bg='#2b2b2b')

        # Tell Windows to make our chosen color fully transparent
        self.wm_attributes('-transparentcolor', self.TRANSPARENT_COLOR)

        # Keep the window above the game so the overlay is always visible
        self.wm_attributes('-topmost', True)

        # Will hold the captured PIL image for OCR processing
        self.captured_image = None

        # Will hold the cached market data (loaded from JSON or fetched fresh)
        self.market_data = None

        self._build_ui()

        # Try to load cached market data on startup
        self._load_cached_data()

    def _build_ui(self):
        """Build the three sections: capture region, buttons, and results."""

        # =====================================================================
        # CAPTURE REGION — transparent area with a visible gold border
        # =====================================================================

        # Outer frame acts as the colored border around the see-through area
        self.border_frame = tk.Frame(self, bg='#FFD700')
        self.border_frame.pack(fill='both', expand=True, padx=8, pady=(8, 4))

        # The label inside is set to the transparent color, so the user
        # can see through it to the game below. After capturing, we swap
        # its background to opaque and show the screenshot image here.
        self.capture_label = tk.Label(self.border_frame, bg=self.TRANSPARENT_COLOR)
        self.capture_label.pack(fill='both', expand=True, padx=2, pady=2)

        # =====================================================================
        # BUTTON BAR
        # =====================================================================

        button_frame = tk.Frame(self, bg='#2b2b2b')
        button_frame.pack(fill='x', padx=8, pady=4)

        # Take Screenshot — hides window, captures, runs OCR, shows results
        self.screenshot_btn = tk.Button(
            button_frame,
            text="Take Screenshot",
            command=self.on_screenshot,
            bg='#4a4a4a', fg='white', activebackground='#5a5a5a',
            font=('Consolas', 11), relief='flat', padx=12, pady=4
        )
        self.screenshot_btn.pack(side='left', padx=(0, 5))

        # Clear — resets the capture region back to transparent
        self.clear_btn = tk.Button(
            button_frame,
            text="Clear",
            command=self.on_clear,
            bg='#4a4a4a', fg='white', activebackground='#5a5a5a',
            font=('Consolas', 11), relief='flat', padx=12, pady=4
        )
        self.clear_btn.pack(side='left', padx=(0, 5))

        # Refresh Data — fetches fresh prices from warframe.market
        self.refresh_btn = tk.Button(
            button_frame,
            text="Refresh Data",
            command=self.on_refresh_data,
            bg='#4a4a4a', fg='white', activebackground='#5a5a5a',
            font=('Consolas', 11), relief='flat', padx=12, pady=4
        )
        self.refresh_btn.pack(side='left')

        # Status label — shows whether market data is loaded
        self.status_label = tk.Label(
            button_frame, text="No data loaded",
            bg='#2b2b2b', fg='#888888',
            font=('Consolas', 9), anchor='e'
        )
        self.status_label.pack(side='right')

        # =====================================================================
        # RESULTS AREA — panel at the bottom to show detected items + prices
        # =====================================================================

        self.results_frame = tk.Frame(self, bg='#1e1e1e', height=250)
        self.results_frame.pack(fill='x', padx=8, pady=(4, 8))
        self.results_frame.pack_propagate(False)  # enforce fixed height

        # Column headers
        header_frame = tk.Frame(self.results_frame, bg='#1e1e1e')
        header_frame.pack(fill='x', padx=12, pady=(10, 0))

        tk.Label(
            header_frame, text="Item", bg='#1e1e1e', fg='#FFD700',
            font=('Consolas', 11, 'bold'), anchor='w'
        ).pack(side='left')

        tk.Label(
            header_frame, text="Best Buy Price", bg='#1e1e1e', fg='#FFD700',
            font=('Consolas', 11, 'bold'), anchor='e'
        ).pack(side='right')

        # Thin separator line under the headers
        tk.Frame(self.results_frame, bg='#444444', height=1).pack(
            fill='x', padx=12, pady=(6, 4)
        )

        # Scrollable container for the actual result rows
        self.results_list = tk.Frame(self.results_frame, bg='#1e1e1e')
        self.results_list.pack(fill='both', expand=True, padx=12, pady=(0, 8))

        # Show placeholder on first launch
        self._show_message("Take a screenshot to look up prices.")

    # =========================================================================
    # MARKET DATA
    # =========================================================================

    def _load_cached_data(self):
        """Try to load market data from the JSON cache file on startup."""
        cache = load_cache()
        if cache:
            self.market_data = cache
            num_sets = len(cache["sets"])
            timestamp = cache.get("timestamp", "unknown")
            # Show just the date portion of the timestamp
            date_str = timestamp[:10] if len(timestamp) >= 10 else timestamp
            self.status_label.config(
                text=f"{num_sets} sets loaded ({date_str})",
                fg='#88cc88'
            )
            print(f"Loaded cached market data: {num_sets} sets from {date_str}")
        else:
            self.status_label.config(text="No data — click Refresh Data", fg='#cc8888')

    def on_refresh_data(self):
        """Fetch fresh price data from warframe.market in a background thread."""
        self.refresh_btn.config(state='disabled', text='Loading...')
        self.status_label.config(text="Fetching prices...", fg='#cccc88')

        thread = threading.Thread(target=self._fetch_data_thread, daemon=True)
        thread.start()

    def _fetch_data_thread(self):
        """Background thread that fetches all prices (takes a few minutes)."""
        def update_progress(current, total, name):
            # Schedule UI update on the main thread
            self.after(0, lambda c=current, t=total: self.status_label.config(
                text=f"Loading: {c}/{t}"
            ))

        try:
            cache = fetch_all_prices(progress_callback=update_progress)
            save_cache(cache)
            # Schedule the final UI update on the main thread
            self.after(0, lambda: self._on_data_loaded(cache))
        except Exception as e:
            self.after(0, lambda: self._on_data_error(str(e)))

    def _on_data_loaded(self, cache):
        """Called on the main thread when data fetch completes."""
        self.market_data = cache
        num_sets = len(cache["sets"])
        self.refresh_btn.config(state='normal', text='Refresh Data')
        self.status_label.config(text=f"{num_sets} sets loaded (fresh)", fg='#88cc88')

    def _on_data_error(self, error_msg):
        """Called on the main thread if data fetch fails."""
        self.refresh_btn.config(state='normal', text='Refresh Data')
        self.status_label.config(text=f"Error: {error_msg[:30]}", fg='#cc8888')

    # =========================================================================
    # SCREENSHOT + OCR
    # =========================================================================

    def on_screenshot(self):
        """
        Capture the screen region behind the transparent area,
        run OCR on it, look up matching sets, and display prices.
        """
        # Finalize layout so winfo coordinates are accurate
        self.update_idletasks()

        # Get the screen-absolute position and size of the capture label
        cap_x = self.capture_label.winfo_rootx()
        cap_y = self.capture_label.winfo_rooty()
        cap_w = self.capture_label.winfo_width()
        cap_h = self.capture_label.winfo_height()

        # Hide the window so we capture the game underneath, not ourselves
        self.withdraw()
        self.update()
        time.sleep(0.15)  # small delay for the OS to finish hiding the window

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

        # Bring the window back
        self.deiconify()
        self.update()

        # Display the captured image in the capture area
        img_display = img.resize((cap_w, cap_h), Image.LANCZOS)
        img_tk = ImageTk.PhotoImage(img_display)
        self.capture_label.config(image=img_tk, bg='#1e1e1e')
        self.capture_label.image = img_tk  # prevent garbage collection

        # Store the raw captured image
        self.captured_image = img

        print(f"Captured {cap_w}x{cap_h} region at ({cap_x}, {cap_y})")

        # Run OCR and look up prices if market data is loaded
        if self.market_data:
            self._process_screenshot(img)
        else:
            self._show_message("No market data loaded.\nClick 'Refresh Data' first.")

    def _process_screenshot(self, pil_image):
        """Run OCR on the captured image and display matching set prices."""
        # Extract words from the screenshot via OCR
        words = extract_words(pil_image)
        print(f"OCR words: {words}")

        # Find which prime sets match any of the OCR words
        matches = find_sets_from_words(self.market_data, words)

        if matches:
            self._display_results(matches)
        else:
            self._show_message(
                "No prime items recognized.\n"
                f"OCR read: {' '.join(words[:15])}"
            )

    def on_clear(self):
        """Reset the capture region back to transparent for repositioning."""
        self.capture_label.config(image='', bg=self.TRANSPARENT_COLOR)
        self.capture_label.image = None
        self.captured_image = None
        self._show_message("Take a screenshot to look up prices.")

    # =========================================================================
    # RESULTS DISPLAY
    # =========================================================================

    def _show_message(self, text):
        """Show a simple text message in the results area."""
        for widget in self.results_list.winfo_children():
            widget.destroy()

        tk.Label(
            self.results_list, text=text,
            bg='#1e1e1e', fg='#888888',
            font=('Consolas', 10), justify='left'
        ).pack(anchor='w', pady=4)

    def _display_results(self, matches):
        """
        Display price results for each matched set.
        Shows individual parts, a parts total, and the set price
        so the user can compare selling individually vs as a set.
        """
        # Clear existing content
        for widget in self.results_list.winfo_children():
            widget.destroy()

        for prefix, items in matches.items():
            breakdown = break_down_set(items)

            # --- Set header (e.g. "Rhino Prime") ---
            header = tk.Label(
                self.results_list, text=f"{prefix} Prime",
                bg='#1e1e1e', fg='#FFD700',
                font=('Consolas', 10, 'bold'), anchor='w'
            )
            header.pack(fill='x', pady=(6, 2))

            # --- Individual parts ---
            for part in breakdown["parts"]:
                price = part["best_buy_price"]
                price_str = f"{price}p" if price is not None else "—"
                # Strip the prefix and " Prime " to keep names short
                short_name = part["name"].replace(f"{prefix} Prime ", "")
                self._add_result_row(f"  {short_name}", price_str, fg='#aaaaaa')

            # --- Separator ---
            tk.Frame(self.results_list, bg='#333333', height=1).pack(
                fill='x', pady=2
            )

            # --- Parts total ---
            parts_sum = breakdown["parts_sum"]
            sum_str = f"{parts_sum}p" if parts_sum is not None else "—"
            self._add_result_row("  Parts total", sum_str, fg='#88cc88')

            # --- Set price ---
            if breakdown["set_item"]:
                set_price = breakdown["set_item"]["best_buy_price"]
                set_str = f"{set_price}p" if set_price is not None else "—"
                self._add_result_row("  Set price", set_str, fg='#88cc88')

    def _add_result_row(self, name, price, fg='#aaaaaa'):
        """Add a single name/price row to the results area."""
        row = tk.Frame(self.results_list, bg='#1e1e1e')
        row.pack(fill='x', pady=1)

        tk.Label(
            row, text=name, bg='#1e1e1e', fg=fg,
            font=('Consolas', 10), anchor='w'
        ).pack(side='left')

        tk.Label(
            row, text=price, bg='#1e1e1e', fg='#FFD700',
            font=('Consolas', 10, 'bold'), anchor='e'
        ).pack(side='right')


# Allow running the GUI directly for testing
if __name__ == "__main__":
    app = WFV74()
    app.mainloop()