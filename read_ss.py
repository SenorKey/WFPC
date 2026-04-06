import cv2
import pytesseract
import numpy as np
import unicodedata

import sys
import os

# When running from a PyInstaller bundle, Tesseract is packed
# inside the temp extraction folder alongside the exe
if getattr(sys, 'frozen', False):
    base = sys._MEIPASS
    pytesseract.pytesseract.tesseract_cmd = os.path.join(base, "tesseract", "tesseract.exe")

def remove_accents(text):
    """
    Remove accents from characters in the text.
    For example: 'á' -> 'a', 'é' -> 'e', 'ñ' -> 'n', etc.
    """
    normalized = unicodedata.normalize('NFD', text)
    without_accents = ''.join(char for char in normalized if not unicodedata.combining(char))
    return without_accents


def preprocess_image(pil_image):
    """
    Prepare a screenshot for OCR by converting to high-contrast
    black-and-white. Warframe's relic reward screen has white text
    on a dark background, so we invert and threshold.
    """
    # Convert PIL image to OpenCV format
    image = np.array(pil_image)
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    # Grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Invert colors (white text on dark bg → dark text on white bg)
    inverted = cv2.bitwise_not(gray)
    # Thresholding (binary image)
    _, thresh = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Resize (scale up 2x to help Tesseract with small text)
    scaled = cv2.resize(thresh, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
    # Dilation to thicken thin text
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    dilated = cv2.dilate(scaled, kernel, iterations=1)

    return dilated


# Old read_ss that takes a file path (kept for standalone testing)
# def read_ss(image_path):
#     from PIL import Image
#     pil_image = Image.open(image_path)
#     return read_image(pil_image)


def read_image(pil_image):
    """
    Run OCR on a PIL image and return the raw text.
    Accepts the PIL image directly from the GUI's capture.
    """
    preprocessed = preprocess_image(pil_image)

    # psm 3 = auto page segmentation, oem 3 = default LSTM engine
    config = '--oem 3 --psm 3'
    text = pytesseract.image_to_string(preprocessed, config=config, lang="eng")
    text = remove_accents(text)
    return text


def extract_words(pil_image):
    """
    Full pipeline: take a PIL image, run OCR, clean up the output,
    and return a list of usable words for set matching.

    This is the main function the GUI calls after capturing a screenshot.
    """
    raw_text = read_image(pil_image)

    # Split into individual words
    words = raw_text.split()

    # Remove junk characters and very short words that aren't useful
    junk = {"}", "{", "~", "-", "|", "=", ".", "?", "!", ":", ";", ",", "—", "'", '"'}
    cleaned = []
    for word in words:
        # Skip junk symbols
        if word in junk:
            continue
        # Skip single characters (except &, used in "Silva & Aegis")
        if len(word) < 2 and word != "&":
            continue
        cleaned.append(word)

    return cleaned