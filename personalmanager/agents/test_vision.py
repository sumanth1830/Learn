"""
Run this standalone first: python test_vision.py path/to/your.pdf

Verifies Gemma can actually read the page correctly via vision input,
before touching the real generation pipeline at all.
"""
import sys
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

from pdf_to_images import pdf_to_base64_images

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("API_BASE_URL"),
)

pdf_path = sys.argv[1]
images = pdf_to_base64_images(pdf_path)
print(f"Converted {len(images)} page(s) to images.")

# Test against just the first page for a fast, cheap check
content = [
    {"type": "text", "text": "Describe every table on this page in detail, "
                              "including which items belong to which table. "
                              "Be precise about which chairman/member belongs "
                              "to which committee."},
    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{images[0]}"}},
]

response = client.chat.completions.create(
    model=os.getenv("MODEL_NAME"),
    messages=[{"role": "user", "content": content}],
)

print("\n--- Model's response ---\n")
print(response.choices[0].message.content)