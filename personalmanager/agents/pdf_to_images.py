import base64
from io import BytesIO
from pdf2image import convert_from_path


def pdf_to_base64_images(pdf_path, dpi=150, max_pages=8):
    """
    Convert each page of a PDF into a base64-encoded PNG image, ready to
    send as vision input. dpi=150 balances legibility (small table text
    needs to actually be readable) against image size/token cost.

    max_pages caps how many pages get sent in one request — same practical
    reasoning as PDF_TEXT_CHAR_LIMIT: an unbounded number of high-res
    images per request will blow through context fast.
    """
    pages = convert_from_path(pdf_path, dpi=dpi)

    if len(pages) > max_pages:
        raise ValueError(
            f"PDF has {len(pages)} pages, over the {max_pages}-page limit "
            f"for vision-based generation. Try a shorter document."
        )

    base64_images = []
    for page in pages:
        buffered = BytesIO()
        page.save(buffered, format="PNG")
        b64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        base64_images.append(b64_str)

    return base64_images