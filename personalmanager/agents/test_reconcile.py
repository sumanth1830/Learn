"""
Run: python test_reconcile.py

Merges pdfplumber output (accurate text, wrong table structure) with
PaddleOCR output (correct table structure, occasional character errors)
into one final, corrected text — page by page, using a narrow comparison
task rather than open-ended transcription or generation.
"""
import re
import time
import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "gemma4:12b"


def split_into_pages(text):
    """Splits on the '--- Page N ---' markers both files already share."""
    parts = re.split(r"--- Page (\d+) ---", text)
    pages = {}
    # parts[0] is anything before the first marker (should be empty)
    for i in range(1, len(parts), 2):
        page_num = int(parts[i])
        page_text = parts[i + 1].strip()
        pages[page_num] = page_text
    return pages


def reconcile_page(page_num, pdfplumber_text, paddleocr_text):
    prompt = f"""You are given two extractions of the same page from a document.

Version A (accurate wording, but table rows/columns may be merged incorrectly):
{pdfplumber_text}

Version B (correct table structure, but may have occasional character-level errors):
{paddleocr_text}

Produce a single corrected version of this page that:
- Uses Version B's table structure and organization.
- Uses Version A's exact wording wherever the two versions describe the same
  content, correcting any character-level errors in Version B.
Output only the corrected page content. No commentary, no explanation.
"""
    response = requests.post(OLLAMA_URL, json={
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "think": False,
        "stream": False,
    })
    return response.json()["message"]["content"]


with open("pdfplumber_output.txt") as f:
    pdfplumber_pages = split_into_pages(f.read())

with open("paddleocr_output.txt") as f:
    paddleocr_pages = split_into_pages(f.read())

all_page_nums = sorted(set(pdfplumber_pages) | set(paddleocr_pages))
print(f"Reconciling {len(all_page_nums)} page(s)...\n")

merged_pages = []
t0 = time.time()

for page_num in all_page_nums:
    pt0 = time.time()
    pdf_text = pdfplumber_pages.get(page_num, "")
    paddle_text = paddleocr_pages.get(page_num, "")

    if not pdf_text or not paddle_text:
        # Fall back to whichever version exists if one is missing
        merged_pages.append(f"--- Page {page_num} ---\n{pdf_text or paddle_text}")
        print(f"Page {page_num}: skipped reconciliation (missing one source)")
        continue

    merged = reconcile_page(page_num, pdf_text, paddle_text)
    merged_pages.append(f"--- Page {page_num} ---\n{merged}")

    elapsed = time.time() - pt0
    print(f"Page {page_num}: {elapsed:.1f}s")

total_time = time.time() - t0
final_text = "\n\n".join(merged_pages)

with open("reconciled_output.txt", "w") as f:
    f.write(final_text)

print(f"\nTotal reconciliation time: {total_time:.1f}s")
print(f"Final text length: {len(final_text)} characters")
print(f"Saved to reconciled_output.txt")