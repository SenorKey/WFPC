import tkinter as tk
from PIL import Image, ImageTk

from market_data import break_down_set


# =============================================================================
# COLOR PALETTE — centralized so every widget draws from the same set
# =============================================================================

COLORS = {
    "bg":           "#2b2b2b",   # main window background
    "bg_dark":      "#1e1e1e",   # results panel, cards inner area
    "bg_card":      "#262626",   # card surface (slightly lighter than bg_dark)
    "bg_title":     "#222222",   # title bar strip
    "border":       "#FFD700",   # gold — capture border, accents, prices
    "border_dim":   "#BFA230",   # muted gold for subtle dividers
    "btn":          "#3a3a3a",   # default button face
    "btn_hover":    "#4a4a4a",   # button hover state
    "btn_active":   "#555555",   # button pressed state
    "btn_primary":  "#4a3a10",   # primary action button (gold-tinted dark)
    "btn_pri_hov":  "#5c4a18",   # primary button hover
    "text":         "#cccccc",   # primary text
    "text_dim":     "#777777",   # secondary/placeholder text
    "text_muted":   "#999999",   # part names in results
    "green":        "#88cc88",   # success / totals
    "red":          "#cc8888",   # errors / warnings
    "yellow":       "#cccc88",   # in-progress status
    "separator":    "#333333",   # thin divider lines
    "hl_blue":      "#1a2a4a",   # subtle blue highlight for best set price
    "hl_green":     "#1a3a1a",   # subtle green highlight for best parts total
    "btn_close":    "#4a2020",   # close button (dark red-tinted)
    "btn_close_hov":"#5c2828",   # close button hover
}


class HoverButton(tk.Button):
    """
    A tk.Button subclass that changes color on mouse enter/leave.
    Accepts normal_bg, hover_bg, and active_bg for the three states.
    """

    def __init__(self, master, normal_bg=None, hover_bg=None, active_bg=None, **kwargs):
        self._normal_bg = normal_bg or COLORS["btn"]
        self._hover_bg = hover_bg or COLORS["btn_hover"]
        self._active_bg = active_bg or COLORS["btn_active"]

        super().__init__(
            master,
            bg=self._normal_bg,
            activebackground=self._active_bg,
            **kwargs,
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, event):
        if self["state"] != "disabled":
            self.config(bg=self._hover_bg)

    def _on_leave(self, event):
        if self["state"] != "disabled":
            self.config(bg=self._normal_bg)


class WFPC(tk.Tk):
    """
    Main application window with a transparent see-through capture region.
    The user positions this window so the transparent area overlays the
    in-game relic reward screen. Button clicks are forwarded to the
    AppController, which handles all workflow logic and calls back into
    the GUI's display methods to update what the user sees.
    """

    # Windows will render this exact color as fully transparent (see-through)
    TRANSPARENT_COLOR = '#01FF00'

    def __init__(self):
        super().__init__()

        self.title("WFPC")
        self.geometry("750x580")
        self.minsize(400, 420)
        self.configure(bg=COLORS["bg"])

        # Tell Windows to make our chosen color fully transparent
        self.wm_attributes('-transparentcolor', self.TRANSPARENT_COLOR)

        # Keep the window above the game so the overlay is always visible
        self.wm_attributes('-topmost', True)

        # Controller is set after construction via set_controller()
        self.controller = None

        self._build_ui()

    def set_controller(self, controller):
        """Connect the controller after both GUI and controller are created."""
        self.controller = controller

    # =========================================================================
    # UI CONSTRUCTION
    # =========================================================================

    def _build_ui(self):
        """Build all UI sections: title bar, capture region, buttons, results."""

        self._build_title_bar()
        self._build_capture_region()
        self._build_button_bar()
        self._build_results_panel()

    def _build_title_bar(self):
        """Top strip with app name and status indicator."""

        title_bar = tk.Frame(self, bg=COLORS["bg_title"], height=36)
        title_bar.pack(fill='x', padx=0, pady=0)
        title_bar.pack_propagate(False)  # enforce fixed height

        # Gold diamond accent before the app name
        tk.Label(
            title_bar, text="\u25C6",  # ◆ diamond character
            bg=COLORS["bg_title"], fg=COLORS["border"],
            font=('Consolas', 10),
        ).pack(side='left', padx=(12, 4), pady=0)

        # App name
        tk.Label(
            title_bar, text="WFPC",
            bg=COLORS["bg_title"], fg=COLORS["text"],
            font=('Consolas', 13, 'bold'),
        ).pack(side='left', padx=(0, 0), pady=0)

        # Subtitle / tagline
        tk.Label(
            title_bar, text="warframe.market price check",
            bg=COLORS["bg_title"], fg=COLORS["text_dim"],
            font=('Consolas', 9),
        ).pack(side='left', padx=(8, 0), pady=(2, 0))

        # Status indicator (dot + text) on the right side of title bar
        self._status_dot = tk.Label(
            title_bar, text="\u2022",  # • bullet character
            bg=COLORS["bg_title"], fg=COLORS["text_dim"],
            font=('Consolas', 14),
        )
        self._status_dot.pack(side='right', padx=(0, 10), pady=0)

        self.status_label = tk.Label(
            title_bar, text="No data loaded",
            bg=COLORS["bg_title"], fg=COLORS["text_dim"],
            font=('Consolas', 9), anchor='e',
        )
        self.status_label.pack(side='right', padx=(0, 2), pady=0)

    def _build_capture_region(self):
        """Transparent see-through area with a gold border."""

        # Outer frame acts as the colored border around the see-through area
        self.border_frame = tk.Frame(self, bg=COLORS["border"])
        self.border_frame.pack(fill='both', expand=True, padx=10, pady=(8, 4))

        # The label inside is set to the transparent color, so the user
        # can see through it to the game below. After capturing, we swap
        # its background to opaque and show the screenshot image here.
        self.capture_label = tk.Label(self.border_frame, bg=self.TRANSPARENT_COLOR)
        self.capture_label.pack(fill='both', expand=True, padx=1, pady=1)

    def _build_button_bar(self):
        """Action buttons and controls."""

        button_frame = tk.Frame(self, bg=COLORS["bg"])
        button_frame.pack(fill='x', padx=10, pady=(4, 4))

        # Segoe UI for buttons — proportional sans-serif contrasts with
        # the monospace Consolas used in the data/results section
        btn_font = ('Segoe UI', 10)

        # Take Screenshot — primary action, gold-tinted background
        self.screenshot_btn = HoverButton(
            button_frame,
            text="\u25B6  Capture",  # ▶ play symbol
            command=lambda: self.controller.capture_screenshot(),
            normal_bg=COLORS["btn_primary"],
            hover_bg=COLORS["btn_pri_hov"],
            active_bg=COLORS["btn_active"],
            fg=COLORS["border"], font=btn_font,
            relief='flat', padx=14, pady=5,
            cursor='hand2',
        )
        self.screenshot_btn.pack(side='left', padx=(0, 6))

        # Clear — secondary action
        self.clear_btn = HoverButton(
            button_frame,
            text="\u2715  Clear",  # ✕ x-mark
            command=lambda: self.controller.clear_capture(),
            fg=COLORS["text"], font=btn_font,
            relief='flat', padx=14, pady=5,
            cursor='hand2',
        )
        self.clear_btn.pack(side='left', padx=(0, 6))

        # Refresh Data — secondary action
        self.refresh_btn = HoverButton(
            button_frame,
            text="\u21BB  Refresh Data",  # ↻ refresh symbol
            command=lambda: self.controller.refresh_data(),
            fg=COLORS["text"], font=btn_font,
            relief='flat', padx=14, pady=5,
            cursor='hand2',
        )
        self.refresh_btn.pack(side='left')

        # Close — safely terminates the application, packed to the far right
        self.close_btn = HoverButton(
            button_frame,
            text="\u2716  Close",  # ✖ heavy x-mark
            command=self._on_close,
            normal_bg=COLORS["btn_close"],
            hover_bg=COLORS["btn_close_hov"],
            active_bg=COLORS["btn_active"],
            fg=COLORS["red"], font=btn_font,
            relief='flat', padx=14, pady=5,
            cursor='hand2',
        )
        self.close_btn.pack(side='right')

    def _build_results_panel(self):
        """Scrollable results area at the bottom of the window."""

        # Outer container with a thin gold top-edge accent
        accent_line = tk.Frame(self, bg=COLORS["border_dim"], height=1)
        accent_line.pack(fill='x', padx=10, pady=(4, 0))

        self.results_frame = tk.Frame(self, bg=COLORS["bg_dark"], height=250)
        self.results_frame.pack(fill='x', padx=10, pady=(0, 10))
        self.results_frame.pack_propagate(False)  # enforce fixed height

        # Scrollbar sits flush against the right edge
        scrollbar = tk.Scrollbar(self.results_frame, orient='vertical', troughcolor=COLORS["bg_dark"])
        scrollbar.pack(side='right', fill='y', pady=6)

        # Canvas for scrollable content
        scroll_container = tk.Frame(self.results_frame, bg=COLORS["bg_dark"])
        scroll_container.pack(fill='both', expand=True, padx=6, pady=6)

        self.results_canvas = tk.Canvas(
            scroll_container, bg=COLORS["bg_dark"], highlightthickness=0,
        )
        self.results_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.configure(command=self.results_canvas.yview)
        self.results_canvas.pack(fill='both', expand=True)

        # Inner frame that widgets are packed into
        self.results_list = tk.Frame(self.results_canvas, bg=COLORS["bg_dark"])
        self._results_window = self.results_canvas.create_window(
            (0, 0), window=self.results_list, anchor='nw',
        )

        # Update scroll region whenever the inner frame changes size
        self.results_list.bind('<Configure>', self._on_results_configure)
        # Keep inner frame width matched to canvas width
        self.results_canvas.bind('<Configure>', self._on_canvas_configure)

        # Bind mousewheel scrolling when hovering over the results area
        self.results_canvas.bind('<Enter>', self._bind_mousewheel)
        self.results_canvas.bind('<Leave>', self._unbind_mousewheel)

        # Show placeholder on first launch
        self.show_message("Take a screenshot to look up prices.")

    # =========================================================================
    # PUBLIC DISPLAY METHODS — called by the controller
    # =========================================================================

    def update_status(self, text, color_key):
        """
        Update both the status label text and the dot color.
        color_key is a string like 'green', 'yellow', 'red' that maps
        to a color in the COLORS dict.
        """
        color = COLORS[color_key]
        self.status_label.config(text=text, fg=color)
        self._status_dot.config(fg=color)

    def set_capture_busy(self, busy):
        """Disable or re-enable the capture button."""
        self.screenshot_btn.config(state='disabled' if busy else 'normal')

    def set_refresh_busy(self, busy):
        """Disable or re-enable the refresh button and update its label."""
        if busy:
            self.refresh_btn.config(state='disabled', text='Loading...')
        else:
            self.refresh_btn.config(state='normal', text='\u21BB  Refresh Data')

    def get_capture_geometry(self):
        """Return (x, y, width, height) of the capture label in screen coordinates."""
        return (
            self.capture_label.winfo_rootx(),
            self.capture_label.winfo_rooty(),
            self.capture_label.winfo_width(),
            self.capture_label.winfo_height(),
        )

    def show_captured_image(self, pil_image, width, height):
        """Display a captured PIL image inside the capture region."""
        img_display = pil_image.resize((width, height), Image.LANCZOS)
        img_tk = ImageTk.PhotoImage(img_display)
        self.capture_label.config(image=img_tk, bg=COLORS["bg_dark"])
        self.capture_label.image = img_tk  # prevent garbage collection

    def reset_capture_region(self):
        """Set the capture region back to transparent for repositioning."""
        self.capture_label.config(image='', bg=self.TRANSPARENT_COLOR)
        self.capture_label.image = None

    def show_message(self, text):
        """Show a centered placeholder message in the results area."""
        for widget in self.results_list.winfo_children():
            widget.destroy()

        # Center the message vertically and horizontally in the panel
        msg_frame = tk.Frame(self.results_list, bg=COLORS["bg_dark"])
        msg_frame.pack(fill='both', expand=True, pady=30)

        tk.Label(
            msg_frame, text=text,
            bg=COLORS["bg_dark"], fg=COLORS["text_dim"],
            font=('Consolas', 10), justify='center',
        ).pack(anchor='center')

        self.results_canvas.yview_moveto(0)

    def display_results(self, matches):
        """
        Display price results for each matched set inside individual
        card-style panels, one per column. After building all cards,
        highlight the highest set price (blue) and highest parts total (green).
        """
        # Clear existing content
        for widget in self.results_list.winfo_children():
            widget.destroy()

        sets = list(matches.items())
        num_cols = len(sets)

        # Configure grid columns to share width equally
        for col_idx in range(num_cols):
            self.results_list.columnconfigure(col_idx, weight=1, uniform='set_col')

        # Track rows and their numeric values so we can highlight the best ones
        # Each entry is (numeric_price, row_frame)
        set_price_rows = []
        parts_total_rows = []

        for col_idx, (prefix, items) in enumerate(sets):
            breakdown = break_down_set(items)

            # =================================================================
            # CARD — each set gets a raised card frame with a gold top accent
            # =================================================================

            # Outer card container provides padding between cards
            card_pad = tk.Frame(self.results_list, bg=COLORS["bg_dark"])
            card_pad.grid(
                row=0, column=col_idx, sticky='nsew',
                padx=(0 if col_idx == 0 else 4, 0 if col_idx == num_cols - 1 else 4),
                pady=4,
            )

            # Thin gold accent along the top edge of the card
            tk.Frame(card_pad, bg=COLORS["border"], height=2).pack(fill='x')

            # Card body with slightly elevated background
            card = tk.Frame(card_pad, bg=COLORS["bg_card"])
            card.pack(fill='both', expand=True)

            # --- Set header (e.g. "Rhino Prime") ---
            header_frame = tk.Frame(card, bg=COLORS["bg_card"])
            header_frame.pack(fill='x', padx=10, pady=(10, 2))

            tk.Label(
                header_frame, text=f"{prefix} Prime",
                bg=COLORS["bg_card"], fg=COLORS["border"],
                font=('Consolas', 11, 'bold'), anchor='w',
            ).pack(side='left')

            # Small "Buy" column header aligned right
            tk.Label(
                header_frame, text="Buy",
                bg=COLORS["bg_card"], fg=COLORS["text_dim"],
                font=('Consolas', 8), anchor='e',
            ).pack(side='right')

            # Separator under header
            tk.Frame(card, bg=COLORS["separator"], height=1).pack(
                fill='x', padx=10, pady=(4, 4),
            )

            # --- Individual parts ---
            for part in breakdown["parts"]:
                price = part["best_buy_price"]
                price_str = f"{price}p" if price is not None else "\u2014"
                # Strip the "Prefix Prime " from the front to get just "Chassis", "Blade", etc.
                short_name = part["name"].replace(f"{prefix} Prime ", "")
                self._add_result_row(card, short_name, price_str, fg=COLORS["text_muted"])

            # Separator before totals
            tk.Frame(card, bg=COLORS["separator"], height=1).pack(
                fill='x', padx=10, pady=(6, 4),
            )

            # --- Parts total ---
            parts_sum = breakdown["parts_sum"]
            sum_str = f"{parts_sum}p" if parts_sum is not None else "\u2014"
            row = self._add_result_row(card, "Parts total", sum_str, fg=COLORS["green"], bold=True)
            # Track this row for highlighting if it has a valid numeric total
            if parts_sum is not None:
                parts_total_rows.append((parts_sum, row))

            # --- Set price ---
            if breakdown["set_item"]:
                set_price = breakdown["set_item"]["best_buy_price"]
                set_str = f"{set_price}p" if set_price is not None else "\u2014"
                row = self._add_result_row(card, "Set price", set_str, fg=COLORS["green"], bold=True)
                # Track this row for highlighting if it has a valid price
                if set_price is not None:
                    set_price_rows.append((set_price, row))

            # Bottom padding inside the card
            tk.Frame(card, bg=COLORS["bg_card"], height=6).pack()

        # =================================================================
        # HIGHLIGHT — apply subtle backgrounds to the best-value rows
        # =================================================================

        # Highlight the highest set price in blue (even if there's only one)
        if set_price_rows:
            best_set = max(set_price_rows, key=lambda x: x[0])
            self._highlight_row(best_set[1], COLORS["hl_blue"])

        # Highlight the highest parts total in green (even if there's only one)
        if parts_total_rows:
            best_total = max(parts_total_rows, key=lambda x: x[0])
            self._highlight_row(best_total[1], COLORS["hl_green"])

        # Reset scroll position to the top
        self.results_canvas.yview_moveto(0)

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _on_close(self):
        """Safely terminate the application and clean up resources."""
        self.destroy()

    def _add_result_row(self, parent, name, price, fg=COLORS["text_muted"], bold=False):
        """
        Add a single name → price row inside a card.
        Returns the row frame so callers can highlight it later.
        """
        row = tk.Frame(parent, bg=COLORS["bg_card"])
        row.pack(fill='x', padx=10, pady=2)

        name_font = ('Consolas', 10, 'bold') if bold else ('Consolas', 10)

        tk.Label(
            row, text=name,
            bg=COLORS["bg_card"], fg=fg,
            font=name_font, anchor='w',
        ).pack(side='left')

        # Price always in gold, bold for emphasis
        tk.Label(
            row, text=price,
            bg=COLORS["bg_card"], fg=COLORS["border"],
            font=('Consolas', 10, 'bold'), anchor='e',
        ).pack(side='right')

        return row

    def _highlight_row(self, row_frame, bg_color):
        """
        Apply a subtle background highlight to a result row.
        Updates the row frame and all its child labels so the
        color is consistent across the entire row.
        """
        row_frame.config(bg=bg_color)
        for child in row_frame.winfo_children():
            child.config(bg=bg_color)

    # =========================================================================
    # SCROLL HELPERS
    # =========================================================================

    def _on_results_configure(self, event):
        """Update the canvas scroll region when the inner frame resizes."""
        self.results_canvas.configure(
            scrollregion=self.results_canvas.bbox('all')
        )

    def _on_canvas_configure(self, event):
        """Keep the inner results frame as wide as the canvas."""
        self.results_canvas.itemconfig(self._results_window, width=event.width)

    def _bind_mousewheel(self, event):
        """Start capturing mousewheel events when the cursor enters the results area."""
        self.results_canvas.bind_all('<MouseWheel>', self._on_mousewheel)

    def _unbind_mousewheel(self, event):
        """Stop capturing mousewheel events when the cursor leaves."""
        self.results_canvas.unbind_all('<MouseWheel>')

    def _on_mousewheel(self, event):
        """Scroll the results canvas on mousewheel movement."""
        self.results_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')


# Allow running the GUI directly for testing (creates its own controller)
if __name__ == "__main__":
    from app_controller import AppController
    app = WFPC()
    ctrl = AppController(app)
    app.set_controller(ctrl)
    ctrl.load_cached_data()
    app.mainloop()