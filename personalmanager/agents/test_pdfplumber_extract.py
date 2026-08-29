"""
Run: python test_pdfplumber_extract.py path/to/your.pdf

Extracts text using pdfplumber, with the extract_tables() improvement
from earlier in the session (catches side-by-side tables that plain
extract_text() jumbles together). Saves to a file for direct comparison
against the PaddleOCR and Gemma4-vision outputs.
"""
import sys
import pdfplumber


def extract_pdf_text(pdf_path):
    full_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            full_text.append(f"--- Page {page_num} ---\n{page_text}")

            tables = page.extract_tables()
            for i, table in enumerate(tables, start=1):
                full_text.append(f"\n[Table {i} on page {page_num} — extracted with structure preserved:]")
                for row in table:
                    clean_row = [(cell or "").strip().replace("\n", " ") for cell in row]
                    full_text.append(" | ".join(clean_row))

    return "\n".join(full_text)


pdf_path = sys.argv[1]
text = extract_pdf_text(pdf_path)

print(f"Extracted {len(text)} characters from {pdf_path}\n")
print(text)

with open("pdfplumber_output.txt", "w") as f:
    f.write(text)

print(f"\n\nSaved to pdfplumber_output.txt")