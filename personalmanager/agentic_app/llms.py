from functools import lru_cache
from langchain_openai import ChatOpenAI
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

# CORRECTORS = {
#     "GLM-5.3-Flash": "z-ai/glm-5.3-flash",
#     "MiniMax M3": "minimax/minimax-m3",
#     "DeepSeek V4 Pro": "deepseek/deepseek-v4-pro",
# }


@lru_cache(maxsize=None)
def get_moderation_client():
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
    )


@lru_cache(maxsize=None)
def get_guardrail_llm():
    return ChatOpenAI(
        model="openai/gpt-5.4-nano", temperature=0.0, max_tokens=500, timeout=120,
        api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1",
    )


@lru_cache(maxsize=None)
def get_creator_llm():
    return ChatOpenAI(
        model="deepseek/deepseek-v4-flash", temperature=0.2, timeout=240,
        api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1",
    )


@lru_cache(maxsize=None)
def get_evaluator_llm():
    return ChatOpenAI(
        model="google/gemini-3.7-flash", temperature=0, timeout=120,
        api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1",
    )


@lru_cache(maxsize=None)
def get_safety_llm():
    return ChatOpenAI(
        model="deepseek/deepseek-v4-pro", temperature=0, max_tokens=1500, timeout=120,
        api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1",
        extra_body={"reasoning": {"enabled": False}},
    )


@lru_cache(maxsize=None)
def get_corrector_llm():
    return ChatOpenAI(
        model="deepseek/deepseek-v4-pro", temperature=0, timeout=120,
        api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1",
    )


# Digest Summary Workflow LLM's

@lru_cache(maxsize=None)
def get_filter_digest_llm():
    return ChatOpenAI(
        model="openai/gpt-5.4-nano", temperature=0.0, max_tokens=3000, timeout=120,
        api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1",
    )


@lru_cache(maxsize=None)
def get_group_summary_llm():
    return ChatOpenAI(
        model="google/gemini-2.5-flash-lite", temperature=0.2, timeout=120,
        api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1",
    )


@lru_cache(maxsize=None)
def get_group_evaluator_llm():
    return ChatOpenAI(
        model="google/gemini-3.7-flash", temperature=0, timeout=120,
        api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1",
    )


@lru_cache(maxsize=None)
def get_relevance_filter_llm():
    return ChatOpenAI(
        model="openai/gpt-5.4-nano", temperature=0.0, max_tokens=3000, timeout=120,
        api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1",
    )


@lru_cache(maxsize=None)
def get_topics_preview_llm():
    return ChatOpenAI(
        model="google/gemini-2.5-flash-lite", temperature=0.2, timeout=180,
        api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1",
    )