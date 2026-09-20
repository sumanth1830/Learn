from pgvector.django import CosineDistance

from quizmaker.models import SourceChunk
from quizmaker.rag_chunking import embed_chunks


def retrieve_similar_chunks(query_text, user, top_k=5):
    query_embedding = embed_chunks([query_text])[0]
    return (
        SourceChunk.objects.filter(user=user)
        .order_by(CosineDistance("embedding", query_embedding))[:top_k]
    )

def compare_retrieval_strategies(question, user):
    question_text = question.question_text
    citation_text = question.source_citation
    combined_text = f"{question_text} {citation_text}"

    print("=== Question only ===")
    for chunk in retrieve_similar_chunks(question_text, user):
        print(f"[{chunk.header}] {chunk.content[:150]}")

    print("\n=== Citation only ===")
    for chunk in retrieve_similar_chunks(citation_text, user):
        print(f"[{chunk.header}] {chunk.content[:150]}")

    print("\n=== Combined ===")
    for chunk in retrieve_similar_chunks(combined_text, user):
        print(f"[{chunk.header}] {chunk.content[:150]}")