import numpy as np
from PIL import ImageDraw, ImageFont

from rapidocr_onnxruntime import RapidOCR

# RapidOCR loads its ONNX models on first construction, which takes a
# moment. Build it lazily and reuse the single instance for every capture
# so we only pay that cost once.
_OCR_ENGINE = None


def _get_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def read_boxes(pil_image):
    """
    Run RapidOCR on a PIL image and return the raw detection results.

    RapidOCR is a detect -> recognize pipeline: it finds each chunk of
    text on its own and returns a list of detections. Each detection is
    a tuple of:
        (box, text, score)
    where:
        box   - 4 corner points [[x,y], [x,y], [x,y], [x,y]]
                (top-left, top-right, bottom-right, bottom-left)
        text  - the recognized string for that box
        score - recognition confidence as a float (0..1)

    Returns a list of these tuples (empty list if nothing was found).

    Note: unlike the old Tesseract path, we feed RapidOCR the raw RGB
    image. It's a deep model that does its own normalization, so the
    invert/threshold preprocessing we used for Tesseract would only hurt
    accuracy here.
    """
    engine = _get_engine()

    image = np.array(pil_image.convert("RGB"))
    result, _elapse = engine(image)

    boxes = []
    if result:
        for box, text, score in result:
            try:
                score = float(score)
            except (TypeError, ValueError):
                score = 0.0
            boxes.append((box, text, score))
    return boxes


def draw_boxes(pil_image, boxes):
    """
    Draw the detected OCR boxes onto a copy of the captured image for
    debugging/testing. Each box is outlined and labelled with the text
    RapidOCR read and its confidence score.

    Returns a new PIL.Image (the original is left untouched).
    """
    annotated = pil_image.convert("RGB").copy()
    draw = ImageDraw.Draw(annotated)

    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font = ImageFont.load_default()

    outline = (0, 255, 0)        # bright green box
    label_bg = (0, 0, 0)         # black label background
    label_fg = (0, 255, 0)       # green label text

    for box, text, score in boxes:
        # box corners are floats; turn into a flat list of int tuples
        pts = [(int(x), int(y)) for x, y in box]
        draw.line(pts + [pts[0]], fill=outline, width=2)

        label = f"{text}  ({score:.2f})"
        lx, ly = pts[0]
        ly = max(0, ly - 18)

        # Draw a filled background behind the label so it stays readable
        try:
            bbox = draw.textbbox((lx, ly), label, font=font)
            draw.rectangle(bbox, fill=label_bg)
        except Exception:
            pass
        draw.text((lx, ly), label, fill=label_fg, font=font)

    return annotated
