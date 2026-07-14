import os
import sys

from dotenv import find_dotenv, load_dotenv
from openai import OpenAI

# Locate the .env file by searching up the directory tree (repo root: aip444-research-memory-demo/.env)
load_dotenv(find_dotenv())

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    print("Error: OPENROUTER_API_KEY not found. Copy .env.example to .env and add your key.")
    sys.exit(1)

client = OpenAI(
    base_url=OPENROUTER_BASE_URL,
    api_key=OPENROUTER_API_KEY,
)

# google/gemini-2.5-flash-lite and deepseek/deepseek-v4-flash were both tried here and dropped:
# both intermittently skipped or under-extracted tool calls (a missed fact, a hallucinated id) on the
# exact same demo script gpt-4o-mini ran correctly end-to-end — see §8 "LLM decisions are inconsistent".
CHAT_MODEL = "openai/gpt-4o-mini"
EMBEDDING_MODEL = "openai/text-embedding-3-small"
RERANK_MODEL = "cohere/rerank-v3.5"
OPENROUTER_RERANK_URL = OPENROUTER_BASE_URL + "/rerank"

CHROMA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_db")
COLLECTION_NAME = "user_memories"
