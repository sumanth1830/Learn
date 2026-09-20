import re
import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter
from quizmaker.models import SourceChunk
from openai import OpenAI
import os

embedding_client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)


def count_tokens(text: str) -> int:
    encoding = tiktoken.encoding_for_model("text-embedding-3-small")
    return len(encoding.encode(text))

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    length_function=count_tokens,
)


def embed_chunks(chunk_texts: list[str]) -> list[list[float]]:
    response = embedding_client.embeddings.create(
        model="openai/text-embedding-3-small",
        input=chunk_texts,
    )
    return [item.embedding for item in response.data]


def strip_image_comments(text: str) -> str:
    return text.replace("<!-- image -->", "")


def split_into_sections(text: str) -> list[list[str]]:
    sections = []
    current_section = []
    current_header = ""

    for line in text.splitlines():
        if line.startswith("#"):
            content = "\n".join(current_section).strip()
            if content:
                sections.append([current_header, content])
            current_header = re.sub(r"^#+\s*", "", line).strip("*").strip()
            current_section = []
        else:
            current_section.append(line)

    content = "\n".join(current_section).strip()
    if content:
        sections.append([current_header, content])

    return sections

def classify_sections(content: str) -> str:
    if "<table>" in content.lower():
        return "table"

    for line in content.splitlines():
        if re.search(r"^\|.*\|.*-{3,}.*\|", line):
            return "table"

    return "prose"


def merge_with_buffer_section(buffer, section):
    combined_header = " / ".join(b[0] for b in buffer) + " / " + section[0]
    combined_content = "\n\n".join(b[1] for b in buffer) + "\n\n" + section[1]
    return combined_header, combined_content

def _looks_like_header(line: str) -> bool:
    # A genuine header cell is short and label-like. A misidentified
    # data row (like a full explanatory sentence) is typically much
    # longer. 150 characters is a generous cutoff for real headers.
    return len(line) < 150

def split_table_by_rows(content: str) -> list[str]:
    lines = [line for line in content.splitlines() if line.strip()]
    table_lines = [line for line in lines if line.strip().startswith("|")]

    separator_index = None
    for i, line in enumerate(table_lines):
        if re.match(r"^\|[\s\-:|]+\|$", line.strip()):
            separator_index = i
            break

    if separator_index is None:
        return [content]

    header_lines = table_lines[:separator_index]
    if not all(_looks_like_header(line) for line in header_lines):
        return [content]

    header_lines = table_lines[:separator_index]
    separator_row = table_lines[separator_index]
    data_rows = table_lines[separator_index + 1:]

    row_chunks = []
    for row in data_rows:
        header_block = "\n".join(header_lines)
        row_chunks.append(f"{header_block}\n{separator_row}\n{row}")

    return row_chunks


def build_chunks(sections):
    buffer = []
    finalized_chunks = []

    for section in sections:
        section_token_count = count_tokens(section[1])

        if section_token_count < 100:
            buffer.append(section)

        elif 100 <= section_token_count <= 500:
            if buffer:
                combined_header, combined_content = merge_with_buffer_section(buffer, section)
                section = [combined_header, combined_content, section[2]]
                buffer = []
            finalized_chunks.append(section)

        else:
            if buffer:
                combined_header, combined_content = merge_with_buffer_section(buffer, section)
                buffer = []
            else:
                combined_header, combined_content = section[0], section[1]

            split_pieces = splitter.split_text(combined_content)
            for piece in split_pieces:
                finalized_chunks.append([combined_header, piece, section[2]])

    # Leftover buffer content handling
    if buffer:
        header = " / ".join(b[0] for b in buffer)
        content = "\n\n".join(b[1] for b in buffer)
        finalized_chunks.append([header, content, buffer[-1][2]])

    return finalized_chunks


def save_chunks_for_source_text(source_text, user, topic_name):
    cleaned = strip_image_comments(source_text.source_text)
    sections = split_into_sections(cleaned)
    for section in sections:
        section.append(classify_sections(section[1]))
    chunks = build_chunks(sections)

    chunk_texts = [content for header, content, chunk_type in chunks]
    embeddings = embed_chunks(chunk_texts)

    SourceChunk.objects.bulk_create([
        SourceChunk(
            source_text=source_text,
            user=user,
            content=content,
            header=header,
            chunk_type=chunk_type,
            topic_name=topic_name,
            embedding=embedding,
        )
        for (header, content, chunk_type), embedding in zip(chunks, embeddings)
    ])
