"""Natural language processing helpers."""

import re
from typing import AsyncIterator

from bs4 import BeautifulSoup
from markdown import markdown


# Covers the most common emoji Unicode blocks and emoji modifiers.
_EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"  # Regional indicator symbols (flags)
    "\U0001F300-\U0001F5FF"  # Symbols and pictographs
    "\U0001F600-\U0001F64F"  # Emoticons
    "\U0001F680-\U0001F6FF"  # Transport and map symbols
    "\U0001F700-\U0001F77F"  # Alchemical symbols
    "\U0001F780-\U0001F7FF"  # Geometric shapes extended
    "\U0001F800-\U0001F8FF"  # Supplemental arrows-C
    "\U0001F900-\U0001F9FF"  # Supplemental symbols and pictographs
    "\U0001FA00-\U0001FAFF"  # Symbols/pictographs extended blocks
    "\U00002702-\U000027B0"  # Dingbats
    "\U000024C2-\U0001F251"  # Enclosed and compatibility emoji
    "\u200d"  # Zero-width joiner
    "\ufe0f"  # Variation selector-16
    "]+",
    flags=re.UNICODE,
)

# Sentence ending punctuation, optionally followed by closing quotes/brackets.
_SENTENCE_END_RE = re.compile(r"[.!?]+(?:[\"')\]]+)?")


def markdown_to_plain(md: str) -> str:
    """Convert a Markdown string to plain text."""
    html = markdown(md)
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
    return " ".join(text.split())


def remove_emojis(text: str) -> str:
    """Return ``text`` with emoji characters removed."""
    return _EMOJI_RE.sub("", text).strip()


async def sentence_tokenizer(chunks: AsyncIterator[str]) -> AsyncIterator[str]:
    """Yield complete sentences from a generator/iterable of text chunks."""
    buffer = ""

    async for chunk in chunks:
        buffer += chunk
        last_end = 0

        for match in _SENTENCE_END_RE.finditer(buffer):
            end = match.end()

            # Only close a sentence when punctuation is followed by whitespace/end.
            if end < len(buffer) and not buffer[end].isspace():
                continue

            sentence = buffer[last_end:end].strip()
            if sentence:
                yield sentence
            last_end = end

        if last_end:
            buffer = buffer[last_end:].lstrip()

    tail = buffer.strip()
    if tail:
        yield tail
