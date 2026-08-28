"""
Run: python test_hybrid_nothink.py path/to/your.pdf [max_questions]

Full hybrid pipeline, think:false on BOTH phases:
  1. Transcribe every page via vision (native API, think=False)
  2. Generate challenging questions from the accumulated clean text
     (native API, think=False, structured output)

Saves the transcript to disk immediately after Phase 1, so a slow/failed
Phase 2 never costs you the transcription time again.
"""
import sys
import time
import os
import requests
from pydantic import ValidationError

from main import Quiz
from pdf_to_images import pdf_to_base64_images

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "gemma4:12b"
TRANSCRIPT_CACHE = "transcribed_text_nothink.txt"


# def transcribe_page(image_b64):
#     response = requests.post(OLLAMA_URL, json={
#         "model": MODEL_NAME,
#         "messages": [{
#             "role": "user",
#             "content": (
#                 "Transcribe all content on this page accurately and completely. "
#                 "If there are tables, format each one as a clean markdown table, "
#                 "keeping every table's rows and columns correctly separated — "
#                 "do not merge content from different tables together, even if "
#                 "they appear side by side on the page. Output only the "
#                 "transcription, no commentary."
#             ),
#             "images": [image_b64],
#         }],
#         "think": False,
#         "stream": False,
#     })
#     return response.json()["message"]["content"]

import re


def looks_like_garbage(text, max_repeat_ratio=0.3):
    """
    Detects the specific degenerate-repetition failure we hit on page 10 —
    a short substring (like '**|**') repeating far more than any real
    transcription ever would. Not foolproof, but catches the extreme case
    cheaply, without needing to understand the content itself.
    """
    if len(text) < 50:
        return False

    # Find any short chunk (3-10 chars) that repeats an excessive number
    # of times relative to the text's total length.
    for chunk_len in range(3, 11):
        chunks = [text[i:i + chunk_len] for i in range(0, len(text) - chunk_len, chunk_len)]
        if not chunks:
            continue
        most_common = max(set(chunks), key=chunks.count)
        repeat_count = chunks.count(most_common)
        if repeat_count / len(chunks) > max_repeat_ratio and repeat_count > 20:
            return True
    return False


def transcribe_page(image_b64, max_attempts=2):
    for attempt in range(max_attempts):
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL_NAME,
            "messages": [{
                "role": "user",
                "content": (
                    "Transcribe all content on this page EXACTLY as written — "
                    "word for word, verbatim. Do NOT paraphrase, summarize, "
                    "rephrase, or improve the wording in any way, even if it "
                    "would read more naturally. Reproduce the precise text as "
                    "it appears on the page. "
                    "If there are tables, format each one as a clean markdown "
                    "table, keeping every table's rows and columns correctly "
                    "separated — do not merge content from different tables "
                    "together, even if they appear side by side on the page. "
                    "Output only the verbatim transcription, no commentary."
                ),
                "images": [image_b64],
            }],
            "think": False,
            "stream": False,
            "options": {
                "num_predict": 4000,  # hard cap — bounds worst-case time even
                                       # if the known repetition bug fires
            },
        })
        text = response.json()["message"]["content"]

        if not looks_like_garbage(text):
            return text

        print(f"    (attempt {attempt + 1}: detected repetition-loop garbage, retrying...)")

    # Ran out of attempts — return what we have with a clear marker rather
    # than silently passing garbage downstream into generation.
    return f"[TRANSCRIPTION FAILED — repetition loop detected after {max_attempts} attempts]\n{text[:200]}"


def transcribe_pdf(pdf_path):
    images = pdf_to_base64_images(pdf_path)
    pages_text = []

    for i, img_b64 in enumerate(images, start=1):
        t0 = time.time()
        page_text = transcribe_page(img_b64)
        elapsed = time.time() - t0
        print(f"  Page {i}/{len(images)}: {elapsed:.1f}s")
        pages_text.append(f"--- Page {i} ---\n{page_text}")

    return "\n\n".join(pages_text)


def create_quiz(quiz_details, source_text):
    instructions_text = f"""
Before writing your final answer, briefly consider which fact in the source
material is specific and non-obvious enough to make a genuinely challenging
question — in one or two sentences only, not more.

Then generate exactly {quiz_details['max_questions']} multiple choice question{'s' if quiz_details['max_questions'] != 1 else ''}, each with
4 options, one correct answer letter, a hint, and an explanation, based
strictly on the following source document.

<source_document>
{source_text}
</source_document>
"""
    response = requests.post(OLLAMA_URL, json={
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": instructions_text}],
        "format": Quiz.model_json_schema(),
        "think": False,
        "stream": False,
        "options": {"temperature": 0.2},
    })
    data = response.json()
    content = data["message"]["content"]
    thinking = data["message"].get("thinking", "")
    usage = {
        "prompt_tokens": data.get("prompt_eval_count", 0),
        "completion_tokens": data.get("eval_count", 0),
    }
    return content, thinking, usage


pdf_path = sys.argv[1]
max_questions = int(sys.argv[2]) if len(sys.argv) > 2 else 10
quiz_details = {"max_questions": max_questions}

if os.path.exists(TRANSCRIPT_CACHE):
    print(f"Found cached transcript at {TRANSCRIPT_CACHE}, skipping Phase 1.")
    with open(TRANSCRIPT_CACHE) as f:
        source_text = f.read()
    transcribe_time = 0.0
else:
    print(f"{'=' * 60}")
    print("PHASE 1: Transcribe (vision, think=False)")
    print(f"{'=' * 60}")
    t0 = time.time()
    source_text = transcribe_pdf(pdf_path)
    transcribe_time = time.time() - t0
    with open(TRANSCRIPT_CACHE, "w") as f:
        f.write(source_text)
    print(f"\nTotal transcription time: {transcribe_time:.1f}s ({transcribe_time / 60:.1f} min)")
    print(f"Saved to {TRANSCRIPT_CACHE}\n")

print(f"Source text length: {len(source_text)} characters\n")

print(f"{'=' * 60}")
print(f"PHASE 2: Generate {max_questions} question(s) (text, think=False)")
print(f"{'=' * 60}")
t1 = time.time()
content, thinking, usage = create_quiz(quiz_details, source_text)
generation_time = time.time() - t1

print(f"Generation time: {generation_time:.1f}s")
print(f"Prompt tokens: {usage['prompt_tokens']}, Completion tokens: {usage['completion_tokens']}")
if thinking:
    print(f"⚠️  thinking field NOT empty ({len(thinking)} chars)")
else:
    print("✅ thinking field empty — suppressed as expected")

print(f"\n{'=' * 60}")
print("RESULT")
print(f"{'=' * 60}")
try:
    quiz = Quiz.model_validate_json(content)
    for i, item in enumerate(quiz.quiz_items, 1):
        print(f"Q{i}: {item.question}")
        print(f"   Options: {item.options}")
        print(f"   Answer: {item.answer}")
        print(f"   Hint: {item.hint}")
        print(f"   Explanation: {item.explanation}\n")
except ValidationError as e:
    print(f"FAILED to parse: {e}")
    print(f"\nRaw content (first 1000 chars):\n{content[:1000]}")

total_time = transcribe_time + generation_time
print(f"{'=' * 60}")
print(f"TOTAL TIME: {total_time:.1f}s ({total_time / 60:.1f} min)")
print(f"  Transcription: {transcribe_time:.1f}s")
print(f"  Generation:    {generation_time:.1f}s")
print(f"{'=' * 60}")