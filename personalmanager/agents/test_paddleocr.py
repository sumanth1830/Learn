"""
Run: python test_paddleocr.py path/to/your.pdf

Tests PP-StructureV3 (PaddleOCR's document-structure pipeline) — no LLM
involved at all, so structurally immune to both the paraphrasing and
repetition-loop failures we hit with Gemma 4. Checks specifically how it
handles the side-by-side table (page 5, committees/chairmen) that broke
pdfplumber originally.
"""
import sys
import time
from paddleocr import PPStructureV3

pdf_path = sys.argv[1]

print("Initializing PP-StructureV3 pipeline (first run downloads model weights, may take a while)...")
pipeline = PPStructureV3(text_recognition_model_name="en_PP-OCRv5_mobile_rec")

print(f"\nProcessing {pdf_path}...")
t0 = time.time()
results = pipeline.predict(input=pdf_path)
elapsed = time.time() - t0

print(f"\n{'=' * 60}")
print(f"Total time: {elapsed:.1f}s")
print(f"{'=' * 60}\n")

full_text = []
for i, res in enumerate(results):
    print(f"--- Page {i + 1} ---")

    # Best-guess API based on current docs — PP-StructureV3 emits markdown
    # directly. If this doesn't match your installed version exactly,
    # the else branch prints the object's real attributes so we can see
    # the correct one instead of guessing further.
    if hasattr(res, "markdown"):
        raw = res.markdown
        print(f"DEBUG: res.markdown type = {type(raw)}")
        if isinstance(raw, dict):
            print(f"DEBUG: dict keys = {list(raw.keys())}")
            # Most likely shape based on PaddleOCR's markdown export pattern
            page_text = raw.get("markdown_texts") or raw.get("text") or str(raw)
        else:
            page_text = raw
    elif hasattr(res, "save_to_markdown"):
        res.save_to_markdown(f"page_{i + 1}.md")
        with open(f"page_{i + 1}.md") as f:
            page_text = f.read()
    else:
        print("No 'markdown' attribute found — here's what this object actually has:")
        print([attr for attr in dir(res) if not attr.startswith("_")])
        page_text = str(res)

    full_text.append(f"--- Page {i + 1} ---\n{page_text}")
    print(page_text[:500])
    print("...\n")

with open("paddleocr_output.txt", "w") as f:
    f.write("\n\n".join(full_text))

print(f"Full output saved to paddleocr_output.txt")
print(f"Total time: {elapsed:.1f}s for {len(results)} page(s)")