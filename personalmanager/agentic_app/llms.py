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

moderation_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
)

guardrail_llm = ChatOpenAI(
    model="openai/gpt-5.4-nano", temperature=0.0, max_tokens=500,
    api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1",
)

creator_llm = ChatOpenAI(
    model="deepseek/deepseek-v4-flash", temperature=0.2,
    api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1",
)

evaluator_llm = ChatOpenAI(
    model="google/gemini-3.7-flash", temperature=0,
    api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1",
)

safety_llm = ChatOpenAI(
    model="deepseek/deepseek-v4-pro", temperature=0, max_tokens=1500,
    api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1",
    extra_body={"reasoning": {"enabled": False}},
)

corrector_llm = ChatOpenAI(
    model="deepseek/deepseek-v4-pro", temperature=0,
    api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1",
)