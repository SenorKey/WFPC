import cv2
import pytesseract
import numpy as np
from PIL import Image
import unicodedata
from difflib import get_close_matches

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

# ---------- OLD read_ss (reads left-to-right, jumbles multi-line item names) ----------
# def read_ss(image_path):
#     pil_image = Image.open(image_path)
#     preprocessed = preprocess_image(pil_image)
#
#     # Run OCR with recommended config (use psm 3 or 6) (psm 3 is for auto page semgmentation and psm 6 is for uniform blocks of text)
#     # Also use a file with a list of words to bias the ocr to only words in names of prime items.
#     config = '--oem 3 --psm 3 --user-words vocabulary.txt'
#     text = pytesseract.image_to_string(preprocessed, config=config, lang="eng")
#     text = remove_accents(text)
#     return text.replace("\n", " ")

# ---------- OLD process_output (worked with flat string from old read_ss) ----------
# def process_output(text):
#     #removing forma and blueprint because forma cant be sold and blueprint is often read in the wrong order
#     words = text.split()
#     filtered_words = [word for word in words if word not in ["Blueprint", "Forma", "}", "{", "~", "-", "|", "=", ".", "?", "!", ":", ";", ",", "—"]]
#     for word in filtered_words:
#         if len(word) < 2 and word != "&":
#             filtered_words.remove(word)
#     return filtered_words


# =====================================================================================
# NEW APPROACH: Use image_to_data() to get word positions, then cluster by x-position
# to reconstruct each item name separately, even when names span multiple lines.
# =====================================================================================

# Junk strings that tesseract sometimes picks up from the UI
JUNK_WORDS = {"Blueprint", "Forma", "}", "{", "~", "-", "|", "=", ".", "?", "!", ":", ";", ",", "—", ""}

def is_valid_word(word):
    """Check if a word is meaningful (not junk, not a single random character)."""
    if word in JUNK_WORDS:
        return False
    # Allow "&" (used in item names like "Nami & Skyla") but reject other single chars
    if len(word) < 2 and word != "&":
        return False
    return True

def read_ss_clustered(image_path, num_items=4):
    """
    Read a screenshot of the relic reward screen and return a list of item name strings,
    one per reward slot.

    Instead of reading left-to-right across the whole image (which jumbles multi-line names),
    this uses pytesseract.image_to_data() to get the bounding box of every detected word.
    Words are then grouped into columns by their horizontal (x) position, so each item's
    words stay together even if the name wraps to a second line.

    Args:
        image_path: Path to the screenshot image file.
        num_items: Expected number of reward slots (default 4, but handles fewer gracefully).

    Returns:
        A list of cleaned item name strings, e.g. ["Akjagara Prime Blade", "Braton Prime Receiver", ...]
    """
    pil_image = Image.open(image_path)
    preprocessed = preprocess_image(pil_image)

    # image_to_data returns a TSV with columns: level, page_num, block_num, par_num,
    # line_num, word_num, left, top, width, height, conf, text
    # output_type=dict gives us a dict of lists, one list per column.
    config = '--oem 3 --psm 3 --user-words vocabulary.txt'
    data = pytesseract.image_to_data(preprocessed, config=config, lang="eng", output_type=pytesseract.Output.DICT)

    # Collect all valid words with their positions
    words_with_positions = []
    for i in range(len(data['text'])):
        text = data['text'][i].strip()
        conf = int(data['conf'][i])  # confidence score, -1 means no text detected

        # Skip empty detections and low-confidence garbage
        if conf < 0 or not text:
            continue

        clean_text = remove_accents(text)
        if not is_valid_word(clean_text):
            continue

        # Calculate horizontal center of the word's bounding box for clustering
        x_center = data['left'][i] + data['width'][i] / 2
        y_pos = data['top'][i]

        words_with_positions.append({
            'text': clean_text,
            'x_center': x_center,
            'y': y_pos,
            'conf': conf
        })

    if not words_with_positions:
        return []

    # --- Cluster words into columns by x_center position ---
    # Sort all words by x_center so we can find natural gaps between item columns.
    words_sorted_by_x = sorted(words_with_positions, key=lambda w: w['x_center'])

    # Find the largest gaps in x_center positions. The gaps between item cards should be
    # much wider than gaps between words within a single item name.
    # We need (num_items - 1) gaps to split into num_items groups.
    if len(words_sorted_by_x) < 2:
        # Only one word detected, return it as a single item
        return [words_sorted_by_x[0]['text']]

    # Calculate gaps between consecutive words (sorted by x position)
    gaps = []
    for i in range(1, len(words_sorted_by_x)):
        gap_size = words_sorted_by_x[i]['x_center'] - words_sorted_by_x[i - 1]['x_center']
        gaps.append((gap_size, i))  # (gap size, index where the gap occurs)

    # Sort gaps by size (largest first) and take the top (num_items - 1) gaps
    # These are the dividers between item columns
    gaps.sort(reverse=True)
    num_splits = min(num_items - 1, len(gaps))
    split_indices = sorted([idx for _, idx in gaps[:num_splits]])

    # Split the sorted word list at the gap positions to form clusters
    clusters = []
    prev_idx = 0
    for split_idx in split_indices:
        clusters.append(words_sorted_by_x[prev_idx:split_idx])
        prev_idx = split_idx
    clusters.append(words_sorted_by_x[prev_idx:])  # last cluster

    # --- Within each cluster, sort by y then x to get reading order, then join into a name ---
    item_names = []
    for cluster in clusters:
        # Sort top-to-bottom first, then left-to-right within the same line
        cluster.sort(key=lambda w: (w['y'], w['x_center']))
        name = " ".join(word['text'] for word in cluster)
        if name.strip():
            item_names.append(name)

    return item_names


# =====================================================================================
# Fuzzy-match OCR results against known prime items from warframe.market.
# Corrects OCR typos like "Braton Prme Reciver" -> "Braton Prime Receiver".
# =====================================================================================

def match_items(ocr_names, known_items, cutoff=0.5):
    """
    Take a list of OCR-detected item name strings and fuzzy-match each one
    against the known list of prime items from warframe.market.

    Args:
        ocr_names:   List of strings from read_ss_clustered(), e.g. ["Akjagara Prime Blade", ...]
        known_items: List of all known prime item names from get_prime_items()
        cutoff:      Minimum similarity score (0-1) for a match to count. Lower = more lenient.
                     Default 0.5 is fairly forgiving of OCR typos.

    Returns:
        A list of tuples: (ocr_text, best_match_or_None)
        e.g. [("Akjagara Prime Blade", "Akjagara Prime Blade"),
              ("Braton Prme Reciver", "Braton Prime Receiver"),
              ("Forma", None)]
    """
    results = []
    for ocr_name in ocr_names:
        matches = get_close_matches(ocr_name, known_items, n=1, cutoff=cutoff)
        if matches:
            results.append((ocr_name, matches[0]))
        else:
            results.append((ocr_name, None))
    return results


# =====================================================================================
# TESTING - reads a screenshot, clusters words into items, then matches against known items
# =====================================================================================
if __name__ == "__main__":
    from all_prime_items import get_prime_items

    # Read and cluster the screenshot
    ocr_names = read_ss_clustered("screenshot_test8.png")
    print(f"OCR detected {len(ocr_names)} item slots:")
    for i, name in enumerate(ocr_names, 1):
        print(f"  {i}. \"{name}\"")
    print()

    # Fuzzy match each OCR result to a known item
    print("Fetching prime items from warframe.market...")
    known_items = get_prime_items()
    print(f"Loaded {len(known_items)} known prime items.\n")

    matched = match_items(ocr_names, known_items)
    print("Matching results:")
    for ocr_text, best_match in matched:
        if best_match:
            if ocr_text == best_match:
                print(f"  \"{ocr_text}\" -> {best_match} (exact match)")
            else:
                print(f"  \"{ocr_text}\" -> {best_match} (fuzzy match)")
        else:
            print(f"  \"{ocr_text}\" -> No match found (not a tradeable prime item)")