import cv2
import pytesseract
import numpy as np
from PIL import Image
import unicodedata

def remove_accents(text):
    """
    Remove accents from characters in the text.
    For example: 'á' -> 'a', 'é' -> 'e', 'ñ' -> 'n', etc.
    """
    # Normalize unicode characters and remove accents
    normalized = unicodedata.normalize('NFD', text)
    # Remove combining characters (accents)
    without_accents = ''.join(char for char in normalized if not unicodedata.combining(char))
    return without_accents

def preprocess_image(pil_image):
    # Convert PIL image to OpenCV format
    image = np.array(pil_image)
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    # Grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Invert colors (since text is white on dark background)
    inverted = cv2.bitwise_not(gray)
    # Thresholding (binary image)
    _, thresh = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Resize (scale up 2x)
    scaled = cv2.resize(thresh, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
    # Dilation to help with thin text
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    dilated = cv2.dilate(scaled, kernel, iterations=1)

    return dilated

def read_ss(image_path):
    pil_image = Image.open(image_path)
    preprocessed = preprocess_image(pil_image)

    # Run OCR with recommended config (use psm 3 or 6) (psm 3 is for auto page semgmentation and psm 6 is for uniform blocks of text)
    # Also use a file with a list of words to bias the ocr to only words in names of prime items.
    config = '--oem 3 --psm 3 --user-words vocabulary.txt'
    text = pytesseract.image_to_string(preprocessed, config=config, lang="eng")
    text = remove_accents(text)
    return text.replace("\n", " ")

def process_output(text):
    #removing forma and blueprint because forma cant be sold and blueprint is often read in the wrong order
    words = text.split()
    filtered_words = [word for word in words if word not in ["Blueprint", "Forma", "}", "{", "~", "-", "|", "=", ".", "?", "!", ":", ";", ",", "—"]]
    for word in filtered_words:
        if len(word) < 2 and word != "&":
            filtered_words.remove(word)
    return filtered_words


print(process_output(read_ss("screenshot_test8.png")))

