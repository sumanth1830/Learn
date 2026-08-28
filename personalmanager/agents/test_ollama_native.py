"""
Run: python test_ollama_native.py path/to/your.pdf [max_questions]

Talks to Ollama's native /api/chat directly instead of the OpenAI-
compatible layer — the only way to actually pass think:false, since that
setting doesn't propagate through the OpenAI-compatibility shim at all.

Minimal prompt (no few-shot example), structured output via Ollama's own
`format` parameter (a raw JSON schema, not the openai library's
convenience wrapper), and detailed timing broken into phases.
"""
import sys
import time
import requests
from pydantic import ValidationError
import pdfplumber

from main import Quiz

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "gemma4:12b"


def extract_pdf_text(pdf_path):
    full_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            full_text.append(page_text)

            tables = page.extract_tables()
            for i, table in enumerate(tables, start=1):
                full_text.append(f"\n[Table {i} on page {page_num} — extracted with structure preserved:]")
                for row in table:
                    clean_row = [(cell or "").strip().replace("\n", " ") for cell in row]
                    full_text.append(" | ".join(clean_row))

    return "\n".join(full_text)


pdf_path = sys.argv[1]
max_questions = int(sys.argv[2]) if len(sys.argv) > 2 else 1

print(f"{'=' * 60}")
print("PHASE 1: Extract text")
print(f"{'=' * 60}")
t0 = time.time()
source_text = extract_pdf_text(pdf_path)
extract_time = time.time() - t0
print(f"Done in {extract_time:.1f}s — {len(source_text)} characters\n")

instructions_text = f"""
Generate exactly {max_questions} multiple choice question{'s' if max_questions != 1 else ''}, each with
4 options, one correct answer letter, a hint, and an explanation, based
strictly on the following source document.

<source_document>
{source_text}
</source_document>
"""

print(f"{'=' * 60}")
print(f"PHASE 2: Generate {max_questions} question(s) via Ollama native API")
print(f"{'=' * 60}")
print("Sending request (think=False, structured output via JSON schema)...")

t1 = time.time()
response = requests.post(OLLAMA_URL, json={
    "model": MODEL_NAME,
    "messages": [{"role": "user", "content": instructions_text}],
    "format": Quiz.model_json_schema(),
    "think": False,
    "stream": False,
    "options": {"temperature": 0.2},
})
wall_time = time.time() - t1

if response.status_code != 200:
    print(f"\nREQUEST FAILED: HTTP {response.status_code}")
    print(response.text)
    sys.exit(1)

data = response.json()

# Ollama's native response gives real internal timing, in nanoseconds —
# convert to seconds for readability. This is detail the OpenAI-compat
# layer never exposed at all.
def ns_to_s(ns):
    return ns / 1_000_000_000 if ns else 0.0

total_duration = ns_to_s(data.get("total_duration"))
load_duration = ns_to_s(data.get("load_duration"))
prompt_eval_duration = ns_to_s(data.get("prompt_eval_duration"))
eval_duration = ns_to_s(data.get("eval_duration"))
prompt_tokens = data.get("prompt_eval_count", 0)
completion_tokens = data.get("eval_count", 0)

print(f"\n{'=' * 60}")
print("TIMING BREAKDOWN")
print(f"{'=' * 60}")
print(f"Wall clock (request to response): {wall_time:.1f}s")
print(f"  Model load time:     {load_duration:.1f}s")
print(f"  Prompt processing:   {prompt_eval_duration:.1f}s  ({prompt_tokens} tokens)")
print(f"  Generation time:     {eval_duration:.1f}s  ({completion_tokens} tokens)")
print(f"Ollama's own total_duration: {total_duration:.1f}s")

# Confirm directly whether thinking is actually suppressed this time,
# rather than assuming — the "thinking" field, if present and non-empty,
# means reasoning still happened despite think=False.
message = data.get("message", {})
thinking = message.get("thinking", "")
if thinking:
    print(f"\n⚠️  'thinking' field is NOT empty ({len(thinking)} chars) — "
          f"reasoning still occurred despite think=False.")
    print(f"First 300 chars: {thinking[:300]}")
else:
    print(f"\n✅ 'thinking' field is empty — reasoning was genuinely suppressed.")

print(f"\n{'=' * 60}")
print("RESULT")
print(f"{'=' * 60}")

content = message.get("content", "")
try:
    quiz = Quiz.model_validate_json(content)
    print(f"Successfully parsed {len(quiz.quiz_items)} question(s):\n")
    for i, item in enumerate(quiz.quiz_items, 1):
        print(f"Q{i}: {item.question}")
        print(f"   Options: {item.options}")
        print(f"   Answer: {item.answer}")
        print(f"   Hint: {item.hint}")
        print(f"   Explanation: {item.explanation}\n")
except ValidationError as e:
    print(f"FAILED to parse response against Quiz schema: {e}")
    print(f"\nRaw content (first 1000 chars):\n{content[:1000]}")