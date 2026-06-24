"""
Token counting utilities using tiktoken (cl100k_base approximation).
NOTE: For exact counts with LLaMA 3 in production, replace with:
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained("meta-llama/Meta-Llama-3-70B")
    count = len(tokenizer.encode(text))
"""
import tiktoken
from functools import lru_cache
from core.config import TIKTOKEN_ENCODING

# Singleton encoder — initialized once and reused
_encoder: tiktoken.Encoding | None = None


def get_encoder() -> tiktoken.Encoding:
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding(TIKTOKEN_ENCODING)
    return _encoder


def count_tokens(text: str) -> int:
    """Count tokens in a plain text string."""
    return len(get_encoder().encode(text))


def count_message_tokens(message) -> int:
    """Count tokens for a LangChain message object.
    Each message has ~4 overhead tokens (role marker, separators).
    """
    content = message.content if hasattr(message, "content") else str(message)
    return count_tokens(content) + 4


def count_messages_tokens(messages: list) -> int:
    """Sum token counts across a list of messages."""
    return sum(count_message_tokens(m) for m in messages)
