"""Single LLM entry point. Ollama locally, Groq when deployed - same OpenAI client."""
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def get_provider() -> str:
    return os.getenv("LLM_PROVIDER", "ollama")


def get_client():
    """Returns (client, model_name) for the active provider."""
    if get_provider() == "groq":
        return OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.environ["GROQ_API_KEY"],
        ), os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    return OpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama",  # Ollama ignores the key but the client requires one
    ), os.getenv("OLLAMA_MODEL", "qwen3:8b")


def extra_opts() -> dict:
    """qwen3 is a 'thinking' model; long reasoning traces make agent steps slow.
    Disable thinking when running locally on Ollama."""
    if get_provider() == "ollama":
        return {"extra_body": {"think": False}}
    return {}


def strip_think(text: str) -> str:
    """Belt-and-braces: remove any <think>...</think> traces from output."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()