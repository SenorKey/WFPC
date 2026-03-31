import tkinter as tk
from PIL import Image, ImageTk
import mss
import time


class WFV74(tk.Tk):
    """
    Main application window with a transparent see-through capture region.
    The user positions this window so the transparent area overlays the
    in-game relic reward screen, then clicks 'Take Screenshot' to capture
    exactly what's behind that region.
    """

    # Windows will render this exact color as fully transparent (see-through).
    # Using a very specific green that's unlikely to appear in our UI elements.
    TRANSPARENT_COLOR = '#01FF00'

    def __init__(self):
        super().__init__()

        self.title("WFV74")
        self.geometry("750x500")
        self.minsize(400, 350)
        self.configure(bg='#2b2b2b')

        # Tell Windows to make our chosen color fully transparent
        self.wm_attributes('-transparentcolor', self.TRANSPARENT_COLOR)

        # Keep the window above the game so the overlay is always visible
        self.wm_attributes('-topmost', True)

        # Will hold the captured PIL image for later OCR processing
        self.captured_image = None

        self._build_ui()

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

        # Take Screenshot — hides window, captures, shows result
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
        self.clear_btn.pack(side='left')

        # =====================================================================
        # RESULTS AREA — fixed height panel at the bottom
        # =====================================================================

        # Outer container with fixed height so the capture region gets
        # all remaining space when the window is resized
        self.results_frame = tk.Frame(self, bg='#1e1e1e', height=180)
        self.results_frame.pack(fill='x', padx=8, pady=(4, 8))
        self.results_frame.pack_propagate(False)  # enforce the fixed height

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

        # Container for the actual result rows
        self.results_list = tk.Frame(self.results_frame, bg='#1e1e1e')
        self.results_list.pack(fill='both', expand=True, padx=12, pady=(0, 8))

        # Show placeholder data so user can preview the layout
        self._show_placeholder_results()

    def _show_placeholder_results(self):
        """
        Display fake/template items in the results area.
        This just previews what the layout will look like once OCR and
        price lookup are wired in.
        """
        # Clear any existing rows
        for widget in self.results_list.winfo_children():
            widget.destroy()

        # Example items to show the layout (these aren't real results)
        placeholders = [
            ("Rhino Prime Chassis",   "15p"),
            ("Boltor Prime Barrel",   "8p"),
            ("Nikana Prime Blade",    "25p"),
            ("Forma Blueprint",       "—"),
        ]

        for name, price in placeholders:
            row = tk.Frame(self.results_list, bg='#1e1e1e')
            row.pack(fill='x', pady=1)

            tk.Label(
                row, text=name, bg='#1e1e1e', fg='#aaaaaa',
                font=('Consolas', 10), anchor='w'
            ).pack(side='left')

            tk.Label(
                row, text=price, bg='#1e1e1e', fg='#FFD700',
                font=('Consolas', 10, 'bold'), anchor='e'
            ).pack(side='right')

    # =========================================================================
    # ACTIONS
    # =========================================================================

    def on_screenshot(self):
        """
        Capture the screen region behind the transparent capture area.

        How it works:
        1. Record the capture area's screen coordinates and size
        2. Hide the window (withdraw) so mss captures the game, not our overlay
        3. Brief pause so Windows finishes hiding the window
        4. Grab that screen region with mss
        5. Bring window back (deiconify)
        6. Display the captured image where the transparent area was
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
        # (swap the transparent background to opaque so image is visible)
        img_display = img.resize((cap_w, cap_h), Image.LANCZOS)
        img_tk = ImageTk.PhotoImage(img_display)
        self.capture_label.config(image=img_tk, bg='#1e1e1e')
        self.capture_label.image = img_tk  # prevent garbage collection

        # Store the raw captured image for later OCR processing
        self.captured_image = img

        print(f"Captured {cap_w}x{cap_h} region at ({cap_x}, {cap_y})")

    def on_clear(self):
        """Reset the capture region back to transparent for repositioning."""
        self.capture_label.config(image='', bg=self.TRANSPARENT_COLOR)
        self.capture_label.image = None
        self.captured_image = None


# Allow running the GUI directly for testing
if __name__ == "__main__":
    app = WFV74()
    app.mainloop()