from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TypeVar

from loguru import logger
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt, wait_random_exponential

from macro_sentinel.core.config import get_required_env
from macro_sentinel.models import AppConfig, ConfigurationError, LLMProviderError, LLMProviderSettings


T = TypeVar("T")


class BaseLLMClient(ABC):
    def __init__(self, provider: str, settings: LLMProviderSettings) -> None:
        self.provider = provider
        self.settings = settings
        self.model = settings.model

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        raise NotImplementedError


class OpenAIClient(BaseLLMClient):
    def __init__(self, settings: LLMProviderSettings, api_key: str) -> None:
        super().__init__("openai", settings)
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ConfigurationError("Install the openai package to use Active_LLM=openai.") from exc

        kwargs = {"api_key": api_key, "timeout": settings.timeout_seconds}
        if settings.base_url:
            kwargs["base_url"] = settings.base_url
        self._client = AsyncOpenAI(**kwargs)

    async def complete(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
        response = await _call_with_rate_limit_retry(
            "OpenAI",
            lambda: self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            ),
        )

        content = response.choices[0].message.content if response.choices else ""
        return _require_content(content, self.provider)


class AnthropicClient(BaseLLMClient):
    def __init__(self, settings: LLMProviderSettings, api_key: str) -> None:
        super().__init__("anthropic", settings)
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise ConfigurationError("Install the anthropic package to use Active_LLM=anthropic.") from exc

        self._client = AsyncAnthropic(api_key=api_key, timeout=settings.timeout_seconds)

    async def complete(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
        response = await _call_with_rate_limit_retry(
            "Anthropic",
            lambda: self._client.messages.create(
                model=self.model,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            ),
        )

        parts = [getattr(block, "text", "") for block in response.content if getattr(block, "type", "") == "text"]
        return _require_content("\n".join(parts), self.provider)


class GeminiClient(BaseLLMClient):
    def __init__(self, settings: LLMProviderSettings, api_key: str) -> None:
        super().__init__("gemini", settings)
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise ConfigurationError("Install the google-generativeai package to use Active_LLM=gemini.") from exc

        genai.configure(api_key=api_key)
        self._genai = genai

    async def complete(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
        def run_sync() -> str:
            generation_config = self._genai.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            )
            model = self._genai.GenerativeModel(self.model, system_instruction=system_prompt)
            response = model.generate_content(user_prompt, generation_config=generation_config)
            return getattr(response, "text", "") or ""

        content = await _call_with_rate_limit_retry("Gemini", lambda: asyncio.to_thread(run_sync))
        return _require_content(content, self.provider)


class GroqClient(BaseLLMClient):
    def __init__(self, settings: LLMProviderSettings, api_key: str) -> None:
        super().__init__("groq", settings)
        try:
            from groq import AsyncGroq
        except ImportError as exc:
            raise ConfigurationError("Install the groq package to use Active_LLM=groq.") from exc

        self._client = AsyncGroq(api_key=api_key, timeout=settings.timeout_seconds)

    async def complete(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
        response = await _call_with_rate_limit_retry(
            "Groq",
            lambda: self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            ),
        )

        content = response.choices[0].message.content if response.choices else ""
        return _require_content(content, self.provider)


def build_llm_client(config: AppConfig) -> BaseLLMClient:
    settings = config.llm.providers.get(config.active_llm)
    if not settings:
        raise ConfigurationError(f"No provider settings found for Active_LLM={config.active_llm}.")

    api_key = get_required_env(settings.api_key_env, f"{config.active_llm} API key")

    if config.active_llm == "openai":
        return OpenAIClient(settings, api_key)
    if config.active_llm == "anthropic":
        return AnthropicClient(settings, api_key)
    if config.active_llm == "gemini":
        return GeminiClient(settings, api_key)
    if config.active_llm == "groq":
        return GroqClient(settings, api_key)

    raise ConfigurationError(f"Unsupported Active_LLM={config.active_llm}.")


def _require_content(content: str | None, provider: str) -> str:
    text = (content or "").strip()
    if not text:
        raise LLMProviderError(f"{provider} returned an empty completion.")
    return text


async def _call_with_rate_limit_retry(provider: str, operation: Callable[[], Awaitable[T]]) -> T:
    try:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(_is_rate_limit_error),
            wait=wait_random_exponential(multiplier=1, min=1, max=30),
            stop=stop_after_attempt(5),
            before_sleep=_log_rate_limit_retry(provider),
            reraise=True,
        ):
            with attempt:
                return await operation()
    except Exception as exc:
        raise LLMProviderError(f"{provider} request failed: {exc}") from exc

    raise LLMProviderError(f"{provider} request failed without a response.")


def _is_rate_limit_error(exc: BaseException) -> bool:
    status_code = _status_code_from_exception(exc)
    if status_code == 429:
        return True

    message = str(exc).lower()
    return "429" in message or "rate limit" in message or "rate_limit" in message


def _status_code_from_exception(exc: BaseException) -> int | None:
    for attr_name in ("status_code", "status", "code"):
        raw_value = getattr(exc, attr_name, None)
        status_code = _coerce_status_code(raw_value)
        if status_code is not None:
            return status_code

    response = getattr(exc, "response", None)
    if response is not None:
        return _coerce_status_code(getattr(response, "status_code", None) or getattr(response, "status", None))

    return None


def _coerce_status_code(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _log_rate_limit_retry(provider: str) -> Callable[[RetryCallState], None]:
    def log_retry(retry_state: RetryCallState) -> None:
        sleep_seconds = retry_state.next_action.sleep if retry_state.next_action else 0
        logger.warning(
            "{} rate limit detected; retrying LLM request in {:.1f}s (attempt {}).",
            provider,
            sleep_seconds,
            retry_state.attempt_number + 1,
        )

    return log_retry
