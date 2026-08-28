"""
Run: python test_transcribe.py path/to/your.pdf

Times a single-page transcription in isolation — the direct test of
whether splitting vision-reading from structured-generation actually
solves the hang, before wiring the whole pipeline around it.
"""
import sys
import time

from transcribe import transcribe_page
from pdf_to_images import pdf_to_base64_images

pdf_path = sys.argv[1]
images = pdf_to_base64_images(pdf_path)

print(f"Testing transcription on page 1 of {len(images)}...\n")
start = time.time()

result = transcribe_page(images[0])

elapsed = time.time() - start
print(f"\n{'=' * 60}")
print(f"Time: {elapsed:.1f}s")
print(f"{'=' * 60}")
print(result)