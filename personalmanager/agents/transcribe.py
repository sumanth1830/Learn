import os
from openai import OpenAI
from dotenv import load_dotenv

from pdf_to_images import pdf_to_base64_images

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("API_BASE_URL"))


def transcribe_page(image_b64):
    """
    Transcribe a single page image to clean text. Deliberately NOT using
    response_format/structured output here — that's exactly the combination
    (vision + schema-constrained generation) that was hanging. Plain text
    output keeps this step fast, matching the already-proven-fast simple
    vision test.
    """
    response = client.chat.completions.create(
        model=os.getenv("MODEL_NAME"),
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": (
                    "Transcribe all content on this page accurately and completely. "
                    "If there are tables, format each one as a clean markdown table, "
                    "keeping every table's rows and columns correctly separated — "
                    "do not merge content from different tables together, even if "
                    "they appear side by side on the page. Output only the "
                    "transcription, no commentary."
                )},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            ]
        }],
    )
    return response.choices[0].message.content


def transcribe_pdf(pdf_path):
    """
    Transcribes every page independently — each call is a fresh request
    with no shared conversation history, which is effectively the "clear
    context between pages" behavior you're after, and happens naturally
    since every API call here is already stateless.
    """
    images = pdf_to_base64_images(pdf_path)
    pages_text = []

    for i, img_b64 in enumerate(images, start=1):
        print(f"Transcribing page {i}/{len(images)}...")
        page_text = transcribe_page(img_b64)
        pages_text.append(f"--- Page {i} ---\n{page_text}")

    return "\n\n".join(pages_text)