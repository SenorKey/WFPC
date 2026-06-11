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

    def set_style(self, normal_bg, hover_bg, fg=None):
        """
        Update the button's color scheme at runtime. Used by the
        suggested-action highlight system to swap a button between
        default and primary styles without recreating it.
        """
        self._normal_bg = normal_bg
        self._hover_bg = hover_bg
        self.config(bg=normal_bg)
        if fg is not None:
            self.config(fg=fg)

    def _on_enter(self, event):
        if self["state"] != "disabled":
            self.config(bg=self._hover_bg)

    def _on_leave(self, event):
        if self["state"] != "disabled":
            self.config(bg=self._normal_bg)


# =============================================================================
# MONITOR PICKER — lets the user choose which monitor to draw on
# =============================================================================


class MonitorPicker(tk.Toplevel):
    """
    Dialog that shows all available monitors as clickable thumbnail
    previews, letting the user choose which screen to capture. Each
    thumbnail is a small screenshot of that monitor, captured right
    before the dialog is shown (while the main GUI is hidden, so the
    game is visible behind).

    If there's only one monitor, the controller skips this dialog
    entirely and uses that screen automatically.
    """

    THUMB_WIDTH = 220  # width of each monitor thumbnail in pixels

    def __init__(self, master, on_select):
        super().__init__(master)
        self.on_select = on_select
        self._photo_refs = []  # prevent garbage collection of thumbnail images

        # Capture a screenshot of each monitor for the preview thumbnails.
        # This happens before the dialog is drawn, so the screenshots
        # show the desktop/game cleanly without this dialog in the way.
        self._monitors = []
        with mss.mss() as sct:
            for mon in sct.monitors[1:]:  # skip index 0 (virtual/combined screen)
                raw = sct.grab(mon)
                img = Image.frombytes("RGB", raw.size, raw.rgb)
                self._monitors.append((mon, img))

        # Borderless, topmost dialog
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.configure(bg=COLORS["bg"])

        # Thin gold border accent around the entire dialog
        outer = tk.Frame(self, bg=COLORS["border"], padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=COLORS["bg"])
        inner.pack(fill="both", expand=True)

        # Title
        tk.Label(
            inner,
            text="Select Monitor",
            bg=COLORS["bg"],
            fg=COLORS["border"],
            font=("Segoe UI", 14, "bold"),
        ).pack(pady=(16, 4))

        # Subtitle with instructions
        tk.Label(
            inner,
            text="Choose which screen the game is on",
            bg=COLORS["bg"],
            fg=COLORS["text_dim"],
            font=("Consolas", 9),
        ).pack(pady=(0, 12))

        # Monitor thumbnails arranged horizontally
        row = tk.Frame(inner, bg=COLORS["bg"])
        row.pack(padx=20, pady=(0, 12))

        for i, (mon, screenshot) in enumerate(self._monitors):
            self._build_monitor_card(row, i, mon, screenshot)

        # Cancel button at the bottom
        HoverButton(
            inner,
            text="\u2715  Cancel",
            command=self._cancel,
            normal_bg=COLORS["btn_close"],
            hover_bg=COLORS["btn_close_hov"],
            fg=COLORS["red"],
            font=("Segoe UI", 10),
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
        ).pack(pady=(0, 16))

        # Center the dialog on the first monitor. Using the first
        # monitor's bounds is more predictable than winfo_screenwidth()
        # which returns the full virtual desktop on multi-monitor setups.
        self.update_idletasks()
        dialog_w = self.winfo_reqwidth()
        dialog_h = self.winfo_reqheight()
        win_x = master.winfo_x()
        win_y = master.winfo_y()
        # Find the monitor whose bounds contain the main window's top-left corner.
        # Fall back to the first monitor if none match (shouldn't normally happen).
        host_monitor = self._monitors[0][0]
        for mon, _ in self._monitors:
            if (
                mon["left"] <= win_x < mon["left"] + mon["width"]
                and mon["top"] <= win_y < mon["top"] + mon["height"]
            ):
                host_monitor = mon
                break
        center_x = host_monitor["left"] + (host_monitor["width"] - dialog_w) // 2
        center_y = host_monitor["top"] + (host_monitor["height"] - dialog_h) // 2
        self.geometry(f"+{center_x}+{center_y}")

        # Grab keyboard focus so ESC works (overrideredirect windows
        # don't receive focus automatically)
        self.focus_force()
        self.bind("<Escape>", lambda e: self._cancel())

    def _build_monitor_card(self, parent, index, monitor, screenshot):
        """
        Build a clickable thumbnail card for one monitor. Shows a
        scaled-down screenshot and the monitor number + resolution.
        """
        # Scale the full screenshot down to a small thumbnail
        aspect = monitor["height"] / monitor["width"]
        thumb_h = int(self.THUMB_WIDTH * aspect)
        thumb = screenshot.resize((self.THUMB_WIDTH, thumb_h), Image.LANCZOS)
        photo = ImageTk.PhotoImage(thumb)
        self._photo_refs.append(photo)  # prevent garbage collection

        # Card container
        card = tk.Frame(parent, bg=COLORS["bg_card"], cursor="hand2")
        card.pack(side="left", padx=8)

        # Gold top accent bar
        accent = tk.Frame(card, bg=COLORS["border"], height=2)
        accent.pack(fill="x")

        # Thumbnail image
        img_label = tk.Label(card, image=photo, bg=COLORS["bg_card"])
        img_label.pack(padx=6, pady=(6, 4))

        # Monitor number and resolution label
        text = (
            f"Monitor {index + 1}  \u2014  {monitor['width']}\u00d7{monitor['height']}"
        )
        text_label = tk.Label(
            card,
            text=text,
            bg=COLORS["bg_card"],
            fg=COLORS["text"],
            font=("Consolas", 9),
        )
        text_label.pack(padx=6, pady=(0, 8))

        # Make everything in the card clickable — clicking anywhere
        # selects this monitor. Hand cursor signals interactivity.
        clickable_widgets = [card, img_label, text_label]
        for widget in clickable_widgets:
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda e, m=monitor: self._select(m))

    def _select(self, monitor):
        """User picked a monitor — pass it to the callback and close."""
        callback = self.on_select
        self.destroy()
        if callback:
            callback(monitor)

    def _cancel(self):
        """User cancelled — pass None to indicate no selection."""
        callback = self.on_select
        self.destroy()
        if callback:
            callback(None)


# =============================================================================
# IN-GAME OVERLAY — minimal floating buttons for capturing during gameplay
# =============================================================================


class InGameOverlay(tk.Toplevel):
    """
    Small floating panel shown during in-game mode. Positioned in the
    top-right corner of the specified monitor with two buttons:
      - Capture: takes a screenshot of the stored region, runs OCR,
                 then restores the main GUI with results displayed
      - Back:    cancels in-game mode and restores the main GUI

    The monitor parameter determines which screen the overlay appears
    on, so it shows up on the same monitor the user is gaming on.
    """

    def __init__(self, master, on_capture, on_back, monitor=None):
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

        # Position in the top-right corner of the correct monitor.
        # If a monitor dict is provided, use its bounds so the overlay
        # appears on the same screen the user defined their region on.
        # Otherwise fall back to the right edge of the virtual desktop.
        self.update_idletasks()
        overlay_w = self.winfo_reqwidth()
        if monitor:
            right_edge = monitor["left"] + monitor["width"]
            top_edge = monitor["top"]
            self.geometry(f"+{right_edge - overlay_w - 20}+{top_edge + 20}")
        else:
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
        # Default size is roomy enough to show all four result cards in a
        # single row (a relic mission normally ends with four rewards)
        # plus the full top-items panel, with nothing scrolled. Width is
        # sized so the results canvas (= width - ~256px of chrome) clears
        # 4 x 288px of cards. The window can be shrunk down to minsize, at
        # which point the side panel gains a scrollbar and the result
        # cards reflow into fewer columns (down to a single one).
        self.geometry("1440x600")
        self.minsize(560, 380)
        self.configure(bg=COLORS["bg"])

        # Controller is set after construction via set_controller()
        self.controller = None

        # Card reflow state — tracks which card widgets exist and the
        # current column count so we only re-grid when layout changes
        self._result_cards = []
        self._prev_num_cols = 0

        # Auto-return countdown state. When an in-game capture finishes,
        # the In Game button counts down ("In Game  30s...") and then
        # flips back to the overlay. _countdown_after_id is the pending
        # tick's 'after' id (None when no countdown is running),
        # _countdown_on_fire is the callback to run at zero, and
        # _ingame_hovering tracks whether the cursor is over the button
        # so a hover can show "Cancel" instead of the countdown.
        self._countdown_after_id = None
        self._countdown_remaining = 0
        self._countdown_on_fire = None
        self._ingame_hovering = False

        self._build_ui()

    def set_controller(self, controller):
        """Connect the controller after both GUI and controller are created."""
        self.controller = controller

    # =========================================================================
    # UI CONSTRUCTION
    # =========================================================================

    def _build_ui(self):
        """Build all UI sections: title bar, buttons, results."""

        self._build_title_bar()
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

    def _build_button_bar(self):
        """
        Action buttons ordered left-to-right by typical first-use flow:
        Refresh Data → In Game → Clear → (gap) → Close.
        All action buttons start with the default style; the controller
        calls highlight_suggested() after startup to mark the next step.
        """

        button_frame = tk.Frame(self, bg=COLORS["bg"])
        button_frame.pack(fill="x", padx=10, pady=(6, 4))

        btn_font = ("Segoe UI", 10)

        # Refresh Data — first step: load/update market prices
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
        self.refresh_btn.pack(side="left", padx=(0, 6))

        # In Game — third step: switch to minimal overlay for capturing
        self.ingame_btn = HoverButton(
            button_frame,
            text="\u25b8  In Game",
            command=self._ingame_button_clicked,
            fg=COLORS["text"],
            font=btn_font,
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
        )
        self.ingame_btn.pack(side="left", padx=(0, 6))
        # Extra hover handlers (add="+" so HoverButton's color swap still
        # runs) to show "Cancel" while the auto-return countdown is active.
        self.ingame_btn.bind("<Enter>", self._ingame_hover_enter, add="+")
        self.ingame_btn.bind("<Leave>", self._ingame_hover_leave, add="+")

        # Clear — reset results after viewing
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
        self.clear_btn.pack(side="left")

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

    def _build_results_panel(self):
        """Scrollable results area at the bottom of the window."""

        # Thin gold accent line above the results panel
        accent_line = tk.Frame(self, bg=COLORS["border_dim"], height=1)
        accent_line.pack(fill="x", padx=10, pady=(4, 0))

        # Horizontal row holding the capture results (left, expanding) and
        # the always-visible top-items panel (right, fixed width).
        content_row = tk.Frame(self, bg=COLORS["bg"])
        content_row.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Build the fixed-width side panel first so it reserves its width;
        # the results frame then expands into whatever space remains.
        self._build_top_items_panel(content_row)

        self.results_frame = tk.Frame(content_row, bg=COLORS["bg_dark"])
        self.results_frame.pack(side="left", fill="both", expand=True)

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

    # Fixed width of the top-items side panel. Sized so the wrapped item
    # names fit comfortably while leaving room for the results column.
    _TOP_PANEL_WIDTH = 200

    def _build_top_items_panel(self, parent):
        """
        Build the always-visible side panel listing the highest-priced
        individual prime parts. Sits on the right of the content row at a
        fixed width; rows are (re)populated by update_top_items().

        The list area is scrollable: at the default window size all items
        fit without scrolling, but if the window is shrunk a scrollbar
        appears automatically (see _on_top_scroll_set).
        """
        panel = tk.Frame(
            parent, bg=COLORS["bg_dark"], width=self._TOP_PANEL_WIDTH
        )
        panel.pack(side="right", fill="y", padx=(8, 0))
        # Keep the panel at its fixed width regardless of child content
        panel.pack_propagate(False)

        # Gold accent strip along the top edge, matching result cards
        tk.Frame(panel, bg=COLORS["border"], height=2).pack(fill="x")

        # Header (stays fixed at the top, above the scrollable list)
        tk.Label(
            panel,
            text="Top Items",
            bg=COLORS["bg_dark"],
            fg=COLORS["border"],
            font=("Consolas", 11, "bold"),
            anchor="w",
        ).pack(fill="x", padx=10, pady=(8, 0))

        tk.Label(
            panel,
            text="top prices, 5+ buyers",
            bg=COLORS["bg_dark"],
            fg=COLORS["text_dim"],
            font=("Consolas", 8),
            anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 4))

        # Separator under header
        tk.Frame(panel, bg=COLORS["separator"], height=1).pack(
            fill="x", padx=10, pady=(0, 4)
        )

        # Scrollable region: canvas + (auto-hiding) scrollbar
        scroll_wrap = tk.Frame(panel, bg=COLORS["bg_dark"])
        scroll_wrap.pack(fill="both", expand=True)

        self.top_scrollbar = tk.Scrollbar(
            scroll_wrap, orient="vertical", troughcolor=COLORS["bg_dark"]
        )
        # Not packed yet — _on_top_scroll_set shows it only when needed.

        self.top_canvas = tk.Canvas(
            scroll_wrap, bg=COLORS["bg_dark"], highlightthickness=0
        )
        self.top_canvas.pack(side="left", fill="both", expand=True)
        self.top_scrollbar.config(command=self.top_canvas.yview)
        self.top_canvas.config(yscrollcommand=self._on_top_scroll_set)

        # Container that update_top_items() clears and rebuilds
        self.top_items_list = tk.Frame(self.top_canvas, bg=COLORS["bg_dark"])
        self._top_window = self.top_canvas.create_window(
            (0, 0), window=self.top_items_list, anchor="nw"
        )

        self.top_items_list.bind("<Configure>", self._on_top_items_configure)
        self.top_canvas.bind("<Configure>", self._on_top_canvas_configure)
        self.top_canvas.bind("<Enter>", self._bind_top_mousewheel)
        self.top_canvas.bind("<Leave>", self._unbind_top_mousewheel)

        # Initial state until the controller pushes data
        self._show_top_items_placeholder("Refresh to see top items")

    # --- top-items panel scrolling -------------------------------------------

    def _on_top_scroll_set(self, first, last):
        """
        yscrollcommand callback that auto-hides the scrollbar when all
        items fit, and shows it (flush right) only when they overflow.
        """
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.top_scrollbar.pack_forget()
        else:
            self.top_scrollbar.pack(side="right", fill="y")
        self.top_scrollbar.set(first, last)

    def _on_top_items_configure(self, event):
        """Update the side panel scroll region when its content changes."""
        self.top_canvas.configure(scrollregion=self.top_canvas.bbox("all"))

    def _on_top_canvas_configure(self, event):
        """Keep the inner list as wide as the side canvas."""
        self.top_canvas.itemconfig(self._top_window, width=event.width)

    def _bind_top_mousewheel(self, event):
        self.top_canvas.bind_all("<MouseWheel>", self._on_top_mousewheel)

    def _unbind_top_mousewheel(self, event):
        self.top_canvas.unbind_all("<MouseWheel>")

    def _on_top_mousewheel(self, event):
        self.top_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _show_top_items_placeholder(self, text):
        """Show a centered dim message in the top-items panel."""
        for widget in self.top_items_list.winfo_children():
            widget.destroy()
        tk.Label(
            self.top_items_list,
            text=text,
            bg=COLORS["bg_dark"],
            fg=COLORS["text_dim"],
            font=("Consolas", 9),
            wraplength=self._TOP_PANEL_WIDTH - 30,
            justify="center",
        ).pack(pady=24, padx=10)

    # =========================================================================
    # PUBLIC DISPLAY METHODS — called by the controller
    # =========================================================================

    def update_top_items(self, items):
        """
        Populate the top-items side panel with a ranked list of the
        highest-priced parts. Each item is a dict with "name" and
        "best_buy_price". An empty list shows the placeholder instead.
        """
        for widget in self.top_items_list.winfo_children():
            widget.destroy()

        if not items:
            self._show_top_items_placeholder("Refresh to see top items")
            return

        for rank, item in enumerate(items, 1):
            row = tk.Frame(self.top_items_list, bg=COLORS["bg_card"])
            row.pack(fill="x", padx=6, pady=3)

            # Drop the redundant " Prime " to save horizontal space
            short_name = item["name"].replace(" Prime ", " ")

            tk.Label(
                row,
                text=f"{rank}. {short_name}",
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"],
                font=("Consolas", 9),
                anchor="w",
                justify="left",
                wraplength=self._TOP_PANEL_WIDTH - 35,
            ).pack(fill="x", padx=6, pady=(4, 0))

            tk.Label(
                row,
                text=f"{item['best_buy_price']}p",
                bg=COLORS["bg_card"],
                fg=COLORS["border"],
                font=("Consolas", 10, "bold"),
                anchor="w",
            ).pack(fill="x", padx=6, pady=(0, 4))

    def update_status(self, text, color_key):
        """
        Update both the status label text and the dot color.
        color_key is a string like 'green', 'yellow', 'red' that maps
        to a color in the COLORS dict.
        """
        color = COLORS[color_key]
        self.status_label.config(text=text, fg=color)
        self._status_dot.config(fg=color)

    def highlight_suggested(self, name):
        """
        Highlight a single button as the suggested next action.
        The named button gets the gold-tinted primary style; all
        other action buttons revert to the default gray style.

        Valid names: 'refresh', 'ingame', or None to clear all
        highlights.
        """
        buttons = {
            "refresh": self.refresh_btn,
            "ingame": self.ingame_btn,
        }
        for key, btn in buttons.items():
            if key == name:
                btn.set_style(
                    COLORS["btn_primary"], COLORS["btn_pri_hov"], fg=COLORS["border"]
                )
            else:
                btn.set_style(COLORS["btn"], COLORS["btn_hover"], fg=COLORS["text"])

    # =========================================================================
    # AUTO-RETURN COUNTDOWN — In Game button ticks down then flips to overlay
    # =========================================================================

    _INGAME_TEXT = "▸  In Game"
    _INGAME_CANCEL_TEXT = "✕  Cancel"

    def _ingame_button_clicked(self):
        """
        Route a click on the In Game button. While the auto-return
        countdown is running the button acts as a Cancel (stop the
        countdown, stay in the main window); otherwise it enters
        in-game mode as usual.
        """
        if self._countdown_after_id is not None:
            self.stop_ingame_countdown()
        else:
            self.controller.enter_in_game_mode()

    def start_ingame_countdown(self, seconds, on_fire):
        """
        Begin counting down on the In Game button. Each second the label
        updates ("In Game  30s...", "29s...", ...); at zero, on_fire()
        runs (the controller's enter_in_game_mode). Any existing
        countdown is cleared first so back-to-back captures don't stack.
        """
        self.stop_ingame_countdown()
        self._countdown_remaining = seconds
        self._countdown_on_fire = on_fire
        self._countdown_tick()

    def _countdown_tick(self):
        """Update the button label once per second, then fire at zero."""
        if self._countdown_remaining <= 0:
            on_fire = self._countdown_on_fire
            self._clear_countdown_state()
            if on_fire:
                on_fire()
            return

        # While the cursor is over the button we leave it reading
        # "Cancel" instead of flashing the countdown out from under it.
        if not self._ingame_hovering:
            self.ingame_btn.config(
                text=f"{self._INGAME_TEXT}  {self._countdown_remaining}s..."
            )
        self._countdown_remaining -= 1
        self._countdown_after_id = self.after(1000, self._countdown_tick)

    def stop_ingame_countdown(self):
        """Cancel a running auto-return countdown, if any, and reset the label."""
        if self._countdown_after_id is not None:
            self.after_cancel(self._countdown_after_id)
        self._clear_countdown_state()

    def _clear_countdown_state(self):
        """Reset countdown bookkeeping and restore the default button label."""
        self._countdown_after_id = None
        self._countdown_remaining = 0
        self._countdown_on_fire = None
        self.ingame_btn.config(text=self._INGAME_TEXT)

    def _ingame_hover_enter(self, event):
        """Show 'Cancel' while hovering during an active countdown."""
        self._ingame_hovering = True
        if self._countdown_after_id is not None:
            self.ingame_btn.config(text=self._INGAME_CANCEL_TEXT)

    def _ingame_hover_leave(self, event):
        """Restore the countdown label when the cursor leaves mid-countdown."""
        self._ingame_hovering = False
        if self._countdown_after_id is not None:
            self.ingame_btn.config(
                text=f"{self._INGAME_TEXT}  {self._countdown_remaining + 1}s..."
            )

    def set_refresh_busy(self, busy):
        """Disable or re-enable the refresh button and update its label."""
        if busy:
            self.refresh_btn.config(state="disabled", text="Loading...")
        else:
            self.refresh_btn.config(state="normal", text="\u21bb  Refresh")

    def show_monitor_picker(self, on_select):
        """Create and display the monitor selection dialog."""
        MonitorPicker(self, on_select)

    def show_in_game_overlay(self, on_capture, on_back, monitor=None):
        """Create and display the minimal in-game floating panel."""
        InGameOverlay(self, on_capture, on_back, monitor)

    def show_message(self, text):
        """Show a centered placeholder message in the results area."""
        for widget in self.results_list.winfo_children():
            widget.destroy()
        # Clear card tracking so reflow doesn't act on destroyed widgets
        self._result_cards = []
        self._prev_num_cols = 0

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

    def show_ocr_debug(self, annotated_image):
        """
        Pop up a window showing the captured region with the OCR text
        boxes drawn on it (for testing). `annotated_image` is a PIL image
        already annotated by read_ss.draw_boxes(). The window is reused on
        subsequent captures so it doesn't stack up.

        Large captures (e.g. a full 3440x1440 grab) are scaled down to fit
        the screen while keeping aspect ratio.
        """
        img = annotated_image

        # Scale down to fit comfortably on screen while keeping aspect.
        max_w = min(1400, self.winfo_screenwidth() - 80)
        max_h = self.winfo_screenheight() - 120
        scale = min(max_w / img.width, max_h / img.height, 1.0)
        if scale < 1.0:
            img = img.resize(
                (max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                Image.LANCZOS,
            )

        photo = ImageTk.PhotoImage(img)

        win = getattr(self, "_ocr_debug_win", None)
        if win is None or not win.winfo_exists():
            win = tk.Toplevel(self)
            win.title("OCR Debug — detected text boxes")
            win.configure(bg=COLORS["bg_dark"])
            label = tk.Label(win, bg=COLORS["bg_dark"], bd=0)
            label.pack(padx=8, pady=8)
            self._ocr_debug_win = win
            self._ocr_debug_label = label
        else:
            label = self._ocr_debug_label

        # Keep a reference so the image isn't garbage-collected.
        self._ocr_debug_photo = photo
        label.configure(image=photo)
        win.deiconify()
        win.lift()

    def display_results(self, items):
        """
        Display one card per matched reward item. Each card shows the
        full item name, the item's own buy price, and the buy price of
        the set it belongs to. Cards reflow responsively as the window
        resizes; the most valuable reward (highest item buy price) is
        highlighted so the best pick stands out.

        `items` is the list of dicts returned by
        market_data.find_items_from_boxes.
        """
        # Clear existing content and previous card tracking
        for widget in self.results_list.winfo_children():
            widget.destroy()
        self._result_cards = []
        self._prev_num_cols = 0

        # Track the item-price rows so we can highlight the best one
        item_price_rows = []

        for entry in items:
            name = entry["name"]
            buy_price = entry["buy_price"]
            set_price = entry["set_buy_price"]

            # =================================================================
            # CARD — each reward gets a raised card with a gold top accent
            # =================================================================

            # Outer card container — this is what gets gridded during reflow
            card_pad = tk.Frame(self.results_list, bg=COLORS["bg_dark"])

            # Thin gold accent along the top edge of the card
            tk.Frame(card_pad, bg=COLORS["border"], height=2).pack(fill="x")

            # Card body with slightly elevated background
            card = tk.Frame(card_pad, bg=COLORS["bg_card"])
            card.pack(fill="both", expand=True)

            # --- Item name header (full name, wraps within the card) ---
            tk.Label(
                card,
                text=name,
                bg=COLORS["bg_card"],
                fg=COLORS["border"],
                font=("Consolas", 11, "bold"),
                anchor="w",
                justify="left",
                wraplength=self._CARD_WIDTH - 24,
            ).pack(fill="x", padx=10, pady=(10, 2))

            # Separator under header
            tk.Frame(card, bg=COLORS["separator"], height=1).pack(
                fill="x",
                padx=10,
                pady=(4, 6),
            )

            # --- Item buy price (this specific reward) ---
            item_str = f"{buy_price}p" if buy_price is not None else "\u2014"
            row = self._add_result_row(
                card, "Item", item_str, fg=COLORS["text_muted"], bold=True
            )
            if buy_price is not None:
                item_price_rows.append((buy_price, row))

            # --- Set buy price (the full set this part belongs to) ---
            set_str = f"{set_price}p" if set_price is not None else "\u2014"
            self._add_result_row(card, "Set", set_str, fg=COLORS["green"])

            # Bottom padding inside the card
            tk.Frame(card, bg=COLORS["bg_card"], height=6).pack()

            # Store the card frame for responsive reflow
            self._result_cards.append(card_pad)

        # =================================================================
        # HIGHLIGHT — mark the most valuable reward (highest item price)
        # =================================================================

        if item_price_rows:
            best = max(item_price_rows, key=lambda x: x[0])
            self._highlight_row(best[1], COLORS["hl_green"])

        # Perform the initial layout and scroll to top
        self._reflow_cards()
        self.results_canvas.yview_moveto(0)

    # Fixed result-card width. The full item-name header wraps to as many
    # lines as it needs (via wraplength), so the width is chosen to look
    # like a card rather than a full-width banner while still fitting the
    # short "Item"/"Set" price rows. Four cards fit across the default
    # window so a typical four-reward relic mission shows in one row.
    _CARD_WIDTH = 280
    _CARD_PAD = 4  # padding around each card on every side

    def _reflow_cards(self):
        """
        Arrange the fixed-width result cards into a grid whose column
        COUNT adapts to the available width. Cards themselves never
        resize — when the window is too narrow for the current number of
        columns, they reflow into fewer columns (down to a single one).

        Called on initial display and whenever the canvas resizes.
        Only re-grids if the column count actually changed, to avoid
        layout thrashing during smooth window dragging.
        """
        if not hasattr(self, "_result_cards") or not self._result_cards:
            return

        canvas_w = self.results_canvas.winfo_width()
        if canvas_w <= 1:
            # Canvas hasn't been drawn yet — use the requested width
            canvas_w = self.results_canvas.winfo_reqwidth()
        if canvas_w <= 1:
            canvas_w = self._CARD_WIDTH  # reasonable fallback for first frame

        # How many fixed-width cards (plus their padding) fit across
        col_total = self._CARD_WIDTH + 2 * self._CARD_PAD
        num_cols = max(1, canvas_w // col_total)
        # Don't use more columns than cards
        num_cols = min(num_cols, len(self._result_cards))

        # Skip re-gridding if the column count hasn't changed
        if num_cols == self._prev_num_cols:
            return
        self._prev_num_cols = num_cols

        # Reset any previously configured columns. Cards are a fixed
        # width (weight=0), so spare horizontal space is simply left
        # empty to the right rather than stretching the cards.
        for i in range(max(num_cols, 20)):
            self.results_list.columnconfigure(i, weight=0, uniform="", minsize=0)
        for col in range(num_cols):
            self.results_list.columnconfigure(
                col, weight=0, minsize=col_total
            )

        # Grid each card. Every column is pinned to the same width
        # (minsize=col_total, weight=0), and sticky="new" stretches each
        # card horizontally to fill it — so all cards render at exactly
        # _CARD_WIDTH — while "n" (not "s") leaves height natural.
        for i, card in enumerate(self._result_cards):
            card.grid(
                row=i // num_cols,
                column=i % num_cols,
                sticky="new",
                padx=self._CARD_PAD,
                pady=self._CARD_PAD,
            )

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _on_close(self):
        """Safely terminate the application and clean up resources."""
        self.destroy()

    def _add_result_row(self, parent, name, price, fg=COLORS["text_muted"], bold=False):
        """
        Add a single name → price row inside a card. Uses grid layout
        so the name column gets flexible space while the price column
        stays fixed-width — this prevents text overlap when cards are
        at their minimum width.

        Returns the row frame so callers can highlight it later.
        """
        row = tk.Frame(parent, bg=COLORS["bg_card"])
        row.pack(fill="x", padx=10, pady=2)

        # Name gets all available space, price stays compact on the right
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=0)

        name_font = ("Consolas", 10, "bold") if bold else ("Consolas", 10)

        tk.Label(
            row,
            text=name,
            bg=COLORS["bg_card"],
            fg=fg,
            font=name_font,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        tk.Label(
            row,
            text=price,
            bg=COLORS["bg_card"],
            fg=COLORS["border"],
            font=("Consolas", 10, "bold"),
            anchor="e",
        ).grid(row=0, column=1, sticky="e", padx=(8, 0))

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
        """
        Keep the inner results frame as wide as the canvas, and
        reflow cards when the available width changes.
        """
        self.results_canvas.itemconfig(self._results_window, width=event.width)
        self._reflow_cards()

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
