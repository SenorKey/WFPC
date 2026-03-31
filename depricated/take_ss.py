import mss
from PIL import Image, ImageTk

#define region of screen
#1200, 600, 990, 45 covers two vertical levels of words in item names
x, y, width, height = 1280, 600, 900, 45
def take_screenshot():

    with mss.mss() as sct:
        #capture from the main monitor
        monitor = sct.monitors[-1] #i have no idea why -1 works

        region = {
            "top": monitor["top"] + y,
            "left": monitor["left"] + x,
            "width": width,
            "height": height,
        }

        #take and save screenshot
        screenshot = sct.grab(region)

        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
        img_tk = ImageTk.PhotoImage(img)

        file_path = "C:/Users/senor/PycharmProjects/WFV74/screenshot_test9.png"
        # file_path2 = "C:/Users/senor/PycharmProjects/WFV74/screenshot_test4.png"

        img.save(file_path)
        # img.save(file_path2)

        print(f"screenshot saved to {file_path}")
        return img_tk