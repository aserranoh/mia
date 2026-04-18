
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import AsyncIterator

from google import genai
from google.genai.types import GenerateContentConfig, GenerateContentResponse, Tool
from google.genai.chats import AsyncChat

from .nlp import sentence_tokenizer


TIME_FOR_NEW_CHAT = timedelta(minutes=5)

LIST_FILES_FUNCTION = {
    "name": "list_files",
    "description": "List the name of the files that we could access to get more information",
    "parameters": {},
}

READ_FILE_FUNCTION = {
    "name": "read_file",
    "description": (
        "Read the content of a file. The content will be used to answer the user's question, "
        "so only read files that are relevant to the question asked by the user."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_name": {
                "type": "string",
                "description": "The name of the file to read. The file name should be one of the names returned by the list_files function.",
            },
        },
        "required": ["file_name"],
    },
}

class LLM(ABC):

    @abstractmethod
    def send_message_stream(self, text: str) -> AsyncIterator[str]:
        """Generate a response to the input text, yielding chunks of the response as they are received."""
        ...


@dataclass
class GeminiLLM(LLM):
    """A wrapper around the Gemini language model that can generate responses to text input."""

    system_prompt: str
    model: str
    api_key: str
    chat_timeout: timedelta = timedelta(minutes=5)

    _config: GenerateContentConfig = field(init=False)
    _gemini_client: genai.Client = field(init=False)
    _current_chat: AsyncChat | None = field(init=False, default=None)
    _last_interaction: datetime = field(init=False, default_factory=lambda: datetime.min)

    def __post_init__(self) -> None:
        """Initialize Gemini client/config for streaming chat responses."""
        self._config = GenerateContentConfig(system_instruction=self.system_prompt)
        self._gemini_client = genai.Client(api_key=self.api_key)

    async def send_message_stream(self, text: str) -> AsyncIterator[str]:
        """Generate a response to the input text, yielding chunks of the response as they are received."""
        request_text = text.strip()
        if not request_text:
            return
        chat = self._get_or_create_chat()
        response = await chat.send_message_stream([request_text])
        async for sentence in sentence_tokenizer(self._stream_text_chunks(response)):
            yield sentence

    def _get_or_create_chat(self) -> AsyncChat:
        """Reuse the active chat unless the idle timeout has elapsed."""
        now = datetime.now()
        if self._current_chat is None or now - self._last_interaction > self.chat_timeout:
            self._current_chat = self._gemini_client.aio.chats.create(
                model=self.model,
                config=self._config,
            )
        self._last_interaction = now
        return self._current_chat

    async def _stream_text_chunks(
        self,
        response: AsyncIterator[GenerateContentResponse],
    ) -> AsyncIterator[str]:
        """Yield only text payloads from Gemini streaming chunks."""
        async for chunk in response:
            if chunk.text:
                yield chunk.text


class DummyLLM(LLM):
    """A dummy LLM that yields a fixed response in chunks, for testing purposes."""

    async def send_message_stream(self, text: str) -> AsyncIterator[str]:
        """Return a local fixed paragraph split into chunk-like objects."""
        paragraph = (
            "Maia is running in local test mode, so this response is generated without calling any "
            "external model service. Streaming still behaves like the real API by sending small "
            "text chunks, which lets you validate your audio, NLP, and UI pipeline end-to-end."
        )
        async for sentence in sentence_tokenizer(self._paragraph_stream(paragraph)):
            yield sentence

    async def _paragraph_stream(self, text: str) -> AsyncIterator[str]:
        """Yield fixed paragraph in chunks that roughly simulate Gemini's streaming behavior."""
        yield text


'''@dataclass
class LLM:
    """A wrapper around a language model that can generate responses to text input."""

    system_prompt: str
    model: str
    api_key: str
    use_dummy_stream: bool = True
    dummy_chunk_size: int = 40

    _config: GenerateContentConfig = field(init=False)
    _gemini_client: genai.Client | None = field(init=False)
    _current_chat: AsyncChat | None = field(init=False, default=None)
    _last_interaction: datetime = field(init=False, default_factory=lambda: datetime.min)


    def __post_init__(self) -> None:
        tools = Tool(function_declarations=[LIST_FILES_FUNCTION, READ_FILE_FUNCTION])
        self._config = GenerateContentConfig(system_instruction=self.system_prompt, tools=[tools])
        self._gemini_client = None if self.use_dummy_stream else genai.Client(api_key=self.api_key)

    async def _dummy_generate_content_stream(self) -> AsyncGenerator["_DummyChunk", None]:
        """Return a local fixed paragraph split into chunk-like objects."""
        paragraph = (
            "Maia is running in local test mode, so this response is generated without calling any "
            "external model service. Streaming still behaves like the real API by sending small "
            "text chunks, which lets you validate your audio, NLP, and UI pipeline end-to-end."
        )
        for i in range(0, len(paragraph), self.dummy_chunk_size):
            yield _DummyChunk(text=paragraph[i : i + self.dummy_chunk_size])

    async def generate_response(self, text: str) -> AsyncGenerator[str, None]:
        """Generate a response to the input text, yielding chunks of the response as they are received."""
        if self.use_dummy_stream:
            response = self._dummy_generate_content_stream()
        else:
            if self._gemini_client is None:
                raise RuntimeError("Gemini client is not initialized.")
            timestamp = datetime.now()
            if self._current_chat is None or datetime.now() - self._last_interaction > TIME_FOR_NEW_CHAT:
                self._current_chat = self._gemini_client.aio.chats.create(
                    model=self.model,
                    config=self._config,
                )
            self._last_interaction = timestamp
            response = await self._current_chat.send_message_stream([text])
        async for chunk in response:
            if chunk.text:
                yield chunk.text
            # 2) Function-call parts
            for candidate in (chunk.candidates or []):
                for part in candidate.content.parts:
                    function_call = part.function_call
                    if not function_call:
                        continue
                    print({
                        "type": "function_call",
                        "name": fc.name,
                        "id": getattr(fc, "id", None),
                        "args": dict(fc.args or {}),
                    })


@dataclass
class _DummyChunk:
    text: str'''


