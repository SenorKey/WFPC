import tkinter as tk
from PIL import Image, ImageTk, ImageEnhance
import mss

from market_data import break_down_set


# =============================================================================
# COLOR PALETTE — centralized so every widget draws from the same set
# =============================================================================

COLORS = {
    "bg": "#2b2b2b",  # main window background
    "bg_dark": "#1e1e1e",  # results panel, cards inner area
    "bg_card": "#262626",  # card surface (slightly lighter than bg_dark)
    "bg_title": "#222222",  # title bar strip
    "border": "#FFD700",  # gold — capture border, accents, prices
    "border_dim": "#BFA230",  # muted gold for subtle dividers
    "btn": "#3a3a3a",  # default button face
    "btn_hover": "#4a4a4a",  # button hover state
    "btn_active": "#555555",  # button pressed state
    "btn_primary": "#4a3a10",  # primary action button (gold-tinted dark)
    "btn_pri_hov": "#5c4a18",  # primary button hover
    "text": "#cccccc",  # primary text
    "text_dim": "#777777",  # secondary/placeholder text
    "text_muted": "#999999",  # part names in results
    "green": "#88cc88",  # success / totals
    "red": "#cc8888",  # errors / warnings
    "yellow": "#cccc88",  # in-progress status
    "separator": "#333333",  # thin divider lines
    "hl_blue": "#1a2a4a",  # subtle blue highlight for best set price
    "hl_green": "#1a3a1a",  # subtle green highlight for best parts total
    "btn_close": "#4a2020",  # close button (dark red-tinted)
    "btn_close_hov": "#5c2828",  # close button hover
}


# =============================================================================
# HOVER BUTTON — color-changing button for consistent interactive styling
# =============================================================================


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


# =============================================================================
# REGION SELECTOR — fullscreen overlay for defining the capture area
# =============================================================================


class RegionSelector(tk.Toplevel):
    """
    Fullscreen overlay that lets the user drag a rectangle to define
    the screen region that will be captured for OCR. Shows a darkened
    screenshot of the desktop as a backdrop so the user can see exactly
    what area they're selecting. The selected coordinates are returned
    as absolute screen positions via the on_complete callback.
    """

    def __init__(self, master, on_complete):
        super().__init__(master)
        self.on_complete = on_complete
        self.region = None

        # Capture the primary monitor as a backdrop image
        with mss.mss() as sct:
            self.monitor = sct.monitors[1]  # primary monitor
            raw = sct.grab(self.monitor)
            full_screenshot = Image.frombytes("RGB", raw.size, raw.rgb)

        # Darken the screenshot so the selection rectangle stands out
        self.dark_screenshot = ImageEnhance.Brightness(full_screenshot).enhance(0.3)

        # Fullscreen borderless window covering the primary monitor
        mon = self.monitor
        self.overrideredirect(True)
        self.geometry(f"{mon['width']}x{mon['height']}+{mon['left']}+{mon['top']}")
        self.wm_attributes("-topmost", True)

        # Canvas fills the entire window — we draw everything on it
        self.canvas = tk.Canvas(
            self,
            width=mon["width"],
            height=mon["height"],
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.pack()

        # Draw the darkened screenshot as the canvas background
        self.bg_photo = ImageTk.PhotoImage(self.dark_screenshot)
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_photo)

        # Instruction text centered near the top
        self.canvas.create_text(
            mon["width"] // 2,
            40,
            text="Click and drag to select the capture region  \u2022  ESC to cancel",
            fill=COLORS["border"],
            font=("Segoe UI", 13, "bold"),
        )

        # Drag state tracking
        self.start_x = None
        self.start_y = None
        self.rect_id = None  # canvas rectangle item
        self.dim_label_id = None  # dimensions text above the rectangle
        self.confirm_win_id = None  # canvas window for accept/cancel buttons

        # Mouse event bindings for click-drag selection
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._finish(None))

    def _on_press(self, event):
        """Record the drag start point and clear any previous selection."""
        self.start_x, self.start_y = event.x, event.y

        # Clean up previous drawing if the user is re-dragging
        for item_id in (self.rect_id, self.dim_label_id, self.confirm_win_id):
            if item_id is not None:
                self.canvas.delete(item_id)
        self.rect_id = None
        self.dim_label_id = None
        self.confirm_win_id = None

    def _on_drag(self, event):
        """Draw the selection rectangle and show its dimensions as the user drags."""
        # Clean up previous frame's rectangle and label
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        if self.dim_label_id:
            self.canvas.delete(self.dim_label_id)

        # Normalize coordinates so (x1,y1) is always the top-left corner
        x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
        x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)

        # Gold dashed rectangle showing the selected area
        self.rect_id = self.canvas.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            outline=COLORS["border"],
            width=2,
            dash=(6, 4),
        )

        # Dimensions label above the rectangle
        w, h = x2 - x1, y2 - y1
        self.dim_label_id = self.canvas.create_text(
            (x1 + x2) // 2,
            max(y1 - 14, 10),
            text=f"{w} \u00d7 {h}",
            fill=COLORS["border"],
            font=("Consolas", 10),
        )

    def _on_release(self, event):
        """
        When the user releases the mouse, finalize the rectangle and
        show Accept / Cancel buttons just below it.
        """
        x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
        x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)
        w, h = x2 - x1, y2 - y1

        # Ignore tiny accidental clicks
        if w < 10 or h < 10:
            return

        # Convert canvas coordinates to absolute screen coordinates.
        # The canvas (0,0) maps to monitor's (left, top).
        abs_x = self.monitor["left"] + x1
        abs_y = self.monitor["top"] + y1
        self.region = (abs_x, abs_y, w, h)

        # Redraw the rectangle with a solid outline now that it's finalized
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            outline=COLORS["border"],
            width=2,
        )

        # Show accept/cancel buttons centered below the rectangle
        btn_frame = tk.Frame(self.canvas, bg=COLORS["bg"])

        HoverButton(
            btn_frame,
            text="\u2713  Accept",
            command=lambda: self._finish(self.region),
            normal_bg=COLORS["btn_primary"],
            hover_bg=COLORS["btn_pri_hov"],
            fg=COLORS["border"],
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
        ).pack(side="left", padx=(0, 6))

        HoverButton(
            btn_frame,
            text="\u2715  Cancel",
            command=lambda: self._finish(None),
            normal_bg=COLORS["btn_close"],
            hover_bg=COLORS["btn_close_hov"],
            fg=COLORS["red"],
            font=("Segoe UI", 11),
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
        ).pack(side="left")

        # Place the button frame on the canvas below the selection
        btn_y = min(y2 + 20, self.monitor["height"] - 60)
        self.confirm_win_id = self.canvas.create_window(
            (x1 + x2) // 2,
            btn_y,
            window=btn_frame,
            anchor="n",
        )

    def _finish(self, region):
        """Close the selector and pass the result back to the callback."""
        callback = self.on_complete
        self.destroy()
        if callback:
            callback(region)


# =============================================================================
# IN-GAME OVERLAY — minimal floating buttons for capturing during gameplay
# =============================================================================


class InGameOverlay(tk.Toplevel):
    """
    Small floating panel shown during in-game mode. Positioned in the
    top-right corner of the screen with two buttons:
      - Capture: takes a screenshot of the stored region, runs OCR,
                 then restores the main GUI with results displayed
      - Back:    cancels in-game mode and restores the main GUI
    """

    def __init__(self, master, on_capture, on_back):
        super().__init__(master)
        self.on_capture = on_capture
        self.on_back = on_back

        # Borderless, always-on-top panel
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)

        # Outer frame provides a thin gold border accent around the panel
        outer = tk.Frame(self, bg=COLORS["border"], padx=1, pady=1)
        outer.pack(fill="both", expand=True)

        inner = tk.Frame(outer, bg=COLORS["bg"])
        inner.pack(fill="both", expand=True)

        btn_font = ("Segoe UI", 10)

        # Capture button — primary gold-tinted style
        HoverButton(
            inner,
            text="\u25b6  Capture",
            command=self._do_capture,
            normal_bg=COLORS["btn_primary"],
            hover_bg=COLORS["btn_pri_hov"],
            fg=COLORS["border"],
            font=btn_font,
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
        ).pack(side="left", padx=(8, 4), pady=8)

        # Back button — red-tinted close style
        HoverButton(
            inner,
            text="\u2715  Back",
            command=self._do_back,
            normal_bg=COLORS["btn_close"],
            hover_bg=COLORS["btn_close_hov"],
            fg=COLORS["red"],
            font=btn_font,
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
        ).pack(side="left", padx=(0, 8), pady=8)

        # Position in the top-right corner of the screen
        self.update_idletasks()
        overlay_w = self.winfo_reqwidth()
        screen_w = self.winfo_screenwidth()
        self.geometry(f"+{screen_w - overlay_w - 20}+20")

    def _do_capture(self):
        """Destroy the overlay and trigger the capture callback."""
        callback = self.on_capture
        self.destroy()
        if callback:
            callback()

    def _do_back(self):
        """Destroy the overlay and return to the main GUI."""
        callback = self.on_back
        self.destroy()
        if callback:
            callback()


# =============================================================================
# MAIN APPLICATION WINDOW
# =============================================================================


class WFPC(tk.Tk):
    """
    Main application window — a normal desktop GUI for setting up the
    capture region, managing market data, and viewing price results.

    The old transparent-overlay approach is replaced by two modes:
      1. Normal mode: full GUI for setup, data management, and viewing results
      2. In-game mode: GUI hides, a small floating panel lets the user
         trigger captures without leaving the game

    Button clicks are forwarded to the AppController, which handles all
    workflow logic and calls back into the GUI's display methods.
    """

    def __init__(self):
        super().__init__()

        self.title("WFPC")
        self.geometry("700x400")
        self.minsize(500, 350)
        self.configure(bg=COLORS["bg"])

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
        """Build all UI sections: title bar, region info, buttons, results."""

        self._build_title_bar()
        self._build_region_bar()
        self._build_button_bar()
        self._build_results_panel()

    def _build_title_bar(self):
        """Top strip with app name and status indicator."""

        title_bar = tk.Frame(self, bg=COLORS["bg_title"], height=36)
        title_bar.pack(fill="x", padx=0, pady=0)
        title_bar.pack_propagate(False)

        # Gold diamond accent before the app name
        tk.Label(
            title_bar,
            text="\u25c6",
            bg=COLORS["bg_title"],
            fg=COLORS["border"],
            font=("Consolas", 10),
        ).pack(side="left", padx=(12, 4), pady=0)

        # App name
        tk.Label(
            title_bar,
            text="WFPC",
            bg=COLORS["bg_title"],
            fg=COLORS["text"],
            font=("Consolas", 13, "bold"),
        ).pack(side="left", padx=(0, 0), pady=0)

        # Subtitle / tagline
        tk.Label(
            title_bar,
            text="warframe.market price check",
            bg=COLORS["bg_title"],
            fg=COLORS["text_dim"],
            font=("Consolas", 9),
        ).pack(side="left", padx=(8, 0), pady=(2, 0))

        # Status indicator (dot + text) on the right side of title bar
        self._status_dot = tk.Label(
            title_bar,
            text="\u2022",
            bg=COLORS["bg_title"],
            fg=COLORS["text_dim"],
            font=("Consolas", 14),
        )
        self._status_dot.pack(side="right", padx=(0, 10), pady=0)

        self.status_label = tk.Label(
            title_bar,
            text="No data loaded",
            bg=COLORS["bg_title"],
            fg=COLORS["text_dim"],
            font=("Consolas", 9),
            anchor="e",
        )
        self.status_label.pack(side="right", padx=(0, 2), pady=0)

    def _build_region_bar(self):
        """
        Thin bar showing the currently defined capture region, or a
        prompt to define one. Sits between the title bar and buttons.
        """
        self.region_bar = tk.Frame(self, bg=COLORS["bg_dark"], height=28)
        self.region_bar.pack(fill="x", padx=10, pady=(6, 0))
        self.region_bar.pack_propagate(False)

        # Region icon — a small square symbol
        tk.Label(
            self.region_bar,
            text="\u2b1c",
            bg=COLORS["bg_dark"],
            fg=COLORS["text_dim"],
            font=("Consolas", 8),
        ).pack(side="left", padx=(8, 4))

        # Region status text (updated dynamically)
        self.region_label = tk.Label(
            self.region_bar,
            text="No capture region defined \u2014 click Define Region",
            bg=COLORS["bg_dark"],
            fg=COLORS["text_dim"],
            font=("Consolas", 9),
            anchor="w",
        )
        self.region_label.pack(side="left", padx=(0, 8))

    def _build_button_bar(self):
        """Action buttons and controls."""

        button_frame = tk.Frame(self, bg=COLORS["bg"])
        button_frame.pack(fill="x", padx=10, pady=(6, 4))

        # Segoe UI for buttons — proportional sans-serif contrasts with
        # the monospace Consolas used in the data/results section
        btn_font = ("Segoe UI", 10)

        # Capture — primary action, gold-tinted background
        self.screenshot_btn = HoverButton(
            button_frame,
            text="\u25b6  Capture",
            command=lambda: self.controller.capture_screenshot(),
            normal_bg=COLORS["btn_primary"],
            hover_bg=COLORS["btn_pri_hov"],
            active_bg=COLORS["btn_active"],
            fg=COLORS["border"],
            font=btn_font,
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
        )
        self.screenshot_btn.pack(side="left", padx=(0, 6))

        # Clear — reset results
        self.clear_btn = HoverButton(
            button_frame,
            text="\u2715  Clear",
            command=lambda: self.controller.clear_capture(),
            fg=COLORS["text"],
            font=btn_font,
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
        )
        self.clear_btn.pack(side="left", padx=(0, 6))

        # Define Region — opens the fullscreen region selector
        self.region_btn = HoverButton(
            button_frame,
            text="\u2b1c  Region",
            command=lambda: self.controller.define_region(),
            fg=COLORS["text"],
            font=btn_font,
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
        )
        self.region_btn.pack(side="left", padx=(0, 6))

        # In Game — switches to minimal floating-button mode
        self.ingame_btn = HoverButton(
            button_frame,
            text="\u25b8  In Game",
            command=lambda: self.controller.enter_in_game_mode(),
            fg=COLORS["text"],
            font=btn_font,
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
        )
        self.ingame_btn.pack(side="left")

        # Close — far right, safely terminates the application
        self.close_btn = HoverButton(
            button_frame,
            text="\u2716  Close",
            command=self._on_close,
            normal_bg=COLORS["btn_close"],
            hover_bg=COLORS["btn_close_hov"],
            active_bg=COLORS["btn_active"],
            fg=COLORS["red"],
            font=btn_font,
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
        )
        self.close_btn.pack(side="right")

        # Refresh Data — next to close on the right
        self.refresh_btn = HoverButton(
            button_frame,
            text="\u21bb  Refresh",
            command=lambda: self.controller.refresh_data(),
            fg=COLORS["text"],
            font=btn_font,
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
        )
        self.refresh_btn.pack(side="right", padx=(0, 6))

    def _build_results_panel(self):
        """Scrollable results area at the bottom of the window."""

        # Thin gold accent line above the results panel
        accent_line = tk.Frame(self, bg=COLORS["border_dim"], height=1)
        accent_line.pack(fill="x", padx=10, pady=(4, 0))

        self.results_frame = tk.Frame(self, bg=COLORS["bg_dark"])
        self.results_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Scrollbar sits flush against the right edge
        scrollbar = tk.Scrollbar(
            self.results_frame,
            orient="vertical",
            troughcolor=COLORS["bg_dark"],
        )
        scrollbar.pack(side="right", fill="y", pady=6)

        # Canvas for scrollable content
        scroll_container = tk.Frame(self.results_frame, bg=COLORS["bg_dark"])
        scroll_container.pack(fill="both", expand=True, padx=6, pady=6)

        self.results_canvas = tk.Canvas(
            scroll_container,
            bg=COLORS["bg_dark"],
            highlightthickness=0,
        )
        self.results_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.configure(command=self.results_canvas.yview)
        self.results_canvas.pack(fill="both", expand=True)

        # Inner frame that result widgets are packed into
        self.results_list = tk.Frame(self.results_canvas, bg=COLORS["bg_dark"])
        self._results_window = self.results_canvas.create_window(
            (0, 0),
            window=self.results_list,
            anchor="nw",
        )

        # Update scroll region whenever the inner frame changes size
        self.results_list.bind("<Configure>", self._on_results_configure)
        self.results_canvas.bind("<Configure>", self._on_canvas_configure)

        # Bind mousewheel scrolling when hovering over the results area
        self.results_canvas.bind("<Enter>", self._bind_mousewheel)
        self.results_canvas.bind("<Leave>", self._unbind_mousewheel)

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

    def update_region_display(self, text, defined=True):
        """
        Update the region bar to show the current capture region info.
        When defined=True, shows in green; otherwise dim placeholder text.
        """
        fg = COLORS["green"] if defined else COLORS["text_dim"]
        self.region_label.config(text=text, fg=fg)

    def set_capture_busy(self, busy):
        """Disable or re-enable the capture button."""
        self.screenshot_btn.config(state="disabled" if busy else "normal")

    def set_refresh_busy(self, busy):
        """Disable or re-enable the refresh button and update its label."""
        if busy:
            self.refresh_btn.config(state="disabled", text="Loading...")
        else:
            self.refresh_btn.config(state="normal", text="\u21bb  Refresh")

    def show_region_selector(self, on_complete):
        """Create and display the fullscreen region selection overlay."""
        RegionSelector(self, on_complete)

    def show_in_game_overlay(self, on_capture, on_back):
        """Create and display the minimal in-game floating panel."""
        InGameOverlay(self, on_capture, on_back)

    def show_message(self, text):
        """Show a centered placeholder message in the results area."""
        for widget in self.results_list.winfo_children():
            widget.destroy()

        msg_frame = tk.Frame(self.results_list, bg=COLORS["bg_dark"])
        msg_frame.pack(fill="both", expand=True, pady=30)

        tk.Label(
            msg_frame,
            text=text,
            bg=COLORS["bg_dark"],
            fg=COLORS["text_dim"],
            font=("Consolas", 10),
            justify="center",
        ).pack(anchor="center")

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
            self.results_list.columnconfigure(col_idx, weight=1, uniform="set_col")

        # Track rows and their numeric values so we can highlight the best ones
        set_price_rows = []
        parts_total_rows = []

        for col_idx, (prefix, items) in enumerate(sets):
            breakdown = break_down_set(items)

            # =================================================================
            # CARD — each set gets a raised card frame with a gold top accent
            # =================================================================

            card_pad = tk.Frame(self.results_list, bg=COLORS["bg_dark"])
            card_pad.grid(
                row=0,
                column=col_idx,
                sticky="nsew",
                padx=(0 if col_idx == 0 else 4, 0 if col_idx == num_cols - 1 else 4),
                pady=4,
            )

            # Thin gold accent along the top edge of the card
            tk.Frame(card_pad, bg=COLORS["border"], height=2).pack(fill="x")

            # Card body
            card = tk.Frame(card_pad, bg=COLORS["bg_card"])
            card.pack(fill="both", expand=True)

            # --- Set header (e.g. "Rhino Prime") ---
            header_frame = tk.Frame(card, bg=COLORS["bg_card"])
            header_frame.pack(fill="x", padx=10, pady=(10, 2))

            tk.Label(
                header_frame,
                text=f"{prefix} Prime",
                bg=COLORS["bg_card"],
                fg=COLORS["border"],
                font=("Consolas", 11, "bold"),
                anchor="w",
            ).pack(side="left")

            tk.Label(
                header_frame,
                text="Buy",
                bg=COLORS["bg_card"],
                fg=COLORS["text_dim"],
                font=("Consolas", 8),
                anchor="e",
            ).pack(side="right")

            # Separator under header
            tk.Frame(card, bg=COLORS["separator"], height=1).pack(
                fill="x",
                padx=10,
                pady=(4, 4),
            )

            # --- Individual parts ---
            for part in breakdown["parts"]:
                price = part["best_buy_price"]
                price_str = f"{price}p" if price is not None else "\u2014"
                short_name = part["name"].replace(f"{prefix} Prime ", "")
                self._add_result_row(
                    card, short_name, price_str, fg=COLORS["text_muted"]
                )

            # Separator before totals
            tk.Frame(card, bg=COLORS["separator"], height=1).pack(
                fill="x",
                padx=10,
                pady=(6, 4),
            )

            # --- Parts total ---
            parts_sum = breakdown["parts_sum"]
            sum_str = f"{parts_sum}p" if parts_sum is not None else "\u2014"
            row = self._add_result_row(
                card, "Parts total", sum_str, fg=COLORS["green"], bold=True
            )
            if parts_sum is not None:
                parts_total_rows.append((parts_sum, row))

            # --- Set price ---
            if breakdown["set_item"]:
                set_price = breakdown["set_item"]["best_buy_price"]
                set_str = f"{set_price}p" if set_price is not None else "\u2014"
                row = self._add_result_row(
                    card, "Set price", set_str, fg=COLORS["green"], bold=True
                )
                if set_price is not None:
                    set_price_rows.append((set_price, row))

            # Bottom padding inside the card
            tk.Frame(card, bg=COLORS["bg_card"], height=6).pack()

        # =================================================================
        # HIGHLIGHT — apply subtle backgrounds to the best-value rows
        # =================================================================

        if set_price_rows:
            best_set = max(set_price_rows, key=lambda x: x[0])
            self._highlight_row(best_set[1], COLORS["hl_blue"])

        if parts_total_rows:
            best_total = max(parts_total_rows, key=lambda x: x[0])
            self._highlight_row(best_total[1], COLORS["hl_green"])

        self.results_canvas.yview_moveto(0)

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _on_close(self):
        """Safely terminate the application and clean up resources."""
        self.destroy()

    def _add_result_row(self, parent, name, price, fg=COLORS["text_muted"], bold=False):
        """
        Add a single name -> price row inside a card.
        Returns the row frame so callers can highlight it later.
        """
        row = tk.Frame(parent, bg=COLORS["bg_card"])
        row.pack(fill="x", padx=10, pady=2)

        name_font = ("Consolas", 10, "bold") if bold else ("Consolas", 10)

        tk.Label(
            row,
            text=name,
            bg=COLORS["bg_card"],
            fg=fg,
            font=name_font,
            anchor="w",
        ).pack(side="left")

        tk.Label(
            row,
            text=price,
            bg=COLORS["bg_card"],
            fg=COLORS["border"],
            font=("Consolas", 10, "bold"),
            anchor="e",
        ).pack(side="right")

        return row

    def _highlight_row(self, row_frame, bg_color):
        """
        Apply a subtle background highlight to a result row.
        Updates the row frame and all its child labels.
        """
        row_frame.config(bg=bg_color)
        for child in row_frame.winfo_children():
            child.config(bg=bg_color)

    # =========================================================================
    # SCROLL HELPERS
    # =========================================================================

    def _on_results_configure(self, event):
        """Update the canvas scroll region when the inner frame resizes."""
        self.results_canvas.configure(scrollregion=self.results_canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        """Keep the inner results frame as wide as the canvas."""
        self.results_canvas.itemconfig(self._results_window, width=event.width)

    def _bind_mousewheel(self, event):
        """Start capturing mousewheel events when the cursor enters the results area."""
        self.results_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, event):
        """Stop capturing mousewheel events when the cursor leaves."""
        self.results_canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        """Scroll the results canvas on mousewheel movement."""
        self.results_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


# Allow running the GUI directly for testing (creates its own controller)
if __name__ == "__main__":
    from app_controller import AppController

    app = WFPC()
    ctrl = AppController(app)
    app.set_controller(ctrl)
    ctrl.load_cached_data()
    app.mainloop()
