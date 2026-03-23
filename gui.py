import tkinter as tk
from take_ss import take_screenshot

main_window = tk.Tk()
main_window.title("Quick Item Price Checker")
main_window.geometry("500x500")

#WHAT THE BUTTONS DO
def on_screenshot():
    print("Screenshot button clicked")
    img_tk = take_screenshot()
    image_label.config(image=img_tk)
    image_label.image = img_tk #keep a reference

def on_stop():
    print("Stop button clicked")

#HOW THE BUTTONS LOOK
button_frame = tk.Frame(main_window)
button_frame.pack(side="bottom", pady=20)

screenshot = tk.Button(button_frame, text="Screen Shot", command=on_screenshot)
screenshot.pack(side="left", padx=10)
stop = tk.Button(button_frame, text="Stop", command=on_stop)
stop.pack(side="right", padx=10)


#IMAGE LABEL
image_label = tk.Label(main_window)
image_label.pack(pady=10)


#HOW THE LIST BOX LOOKS
list_box = tk.Listbox(main_window, font=("Arial", 16))
list_box.pack(expand=True, fill="both", padx=10, pady=10)

#ADDING NEW LINES
# items = ["Item 1", "Item 2", "Item 3", "Item 4"]
# for item in items:
#     listbox.insert(tk.END, item)

if __name__ == "__main__":
    main_window.mainloop()