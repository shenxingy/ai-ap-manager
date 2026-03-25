"""Multi-provider LLM client abstraction for the AP system.

Supported providers:
  anthropic    — Anthropic API (requires ANTHROPIC_API_KEY)
  ollama       — Local Ollama server (requires OLLAMA_BASE_URL + OLLAMA_MODEL)
  claude_code  — 'claude -p' subprocess (free; Celery/sync tasks ONLY)
  none         — Disables LLM; callers receive empty response and handle gracefully

Provider resolution per use-case:
  1. LLM_PROVIDER_{USE_CASE.upper()} (if non-empty)
  2. LLM_PROVIDER (global default)
  3. "none"

Use-cases: extraction | policy | analytics | ask_ai
"""
import abc
import logging
import os
import subprocess
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ─── Response model ───

@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    model: str  # e.g. "claude-sonnet-4-6", "qwen2.5:7b", "claude-code-cli", "none"


# ─── Abstract base ───

class BaseLLMClient(abc.ABC):
    @abc.abstractmethod
    def complete(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> LLMResponse:
        """Send a list of chat messages and return the model's response."""
        ...


# ─── Anthropic provider ───

class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str) -> None:
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> LLMResponse:
        kwargs: dict = dict(model=self._model, max_tokens=max_tokens, messages=messages)
        if system:
            kwargs["system"] = system
        start = time.monotonic()
        resp = self._client.messages.create(**kwargs)
        latency_ms = int((time.monotonic() - start) * 1000)
        text = resp.content[0].text if resp.content else ""
        p_tokens = resp.usage.input_tokens if resp.usage else 0
        c_tokens = resp.usage.output_tokens if resp.usage else 0
        return LLMResponse(
            text=text,
            prompt_tokens=p_tokens,
            completion_tokens=c_tokens,
            latency_ms=latency_ms,
            model=self._model,
        )


# ─── Ollama provider (OpenAI-compatible) ───

class OllamaClient(BaseLLMClient):
    def __init__(self, base_url: str, model: str) -> None:
        from openai import OpenAI
        self._client = OpenAI(base_url=f"{base_url}/v1", api_key="ollama")
        self._model = model

    def complete(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> LLMResponse:
        all_messages: list[dict] = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)
        start = time.monotonic()
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=all_messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        text = resp.choices[0].message.content if resp.choices else ""
        p_tokens = resp.usage.prompt_tokens if resp.usage else 0
        c_tokens = resp.usage.completion_tokens if resp.usage else 0
        return LLMResponse(
            text=text or "",
            prompt_tokens=p_tokens,
            completion_tokens=c_tokens,
            latency_ms=latency_ms,
            model=self._model,
        )


# ─── Claude Code (subprocess) provider ───

class ClaudeCodeClient(BaseLLMClient):
    """Calls 'claude -p' as a subprocess.

    SYNC/BLOCKING — safe for Celery tasks only. Never use in async FastAPI routes.
    Token counts are unavailable from the CLI; they are reported as 0.
    """

    _MODEL_LABEL = "claude-code-cli"

    def complete(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> LLMResponse:
        parts: list[str] = []
        if system:
            parts.append(f"[System]\n{system}\n")
        for msg in messages:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")
            parts.append(f"[{role}]\n{content}\n")
        combined = "\n".join(parts)

        env = os.environ.copy()
        env.pop("CLAUDECODE", None)  # prevent nested claude session error

        start = time.monotonic()
        try:
            result = subprocess.run(
                ["claude", "-p", combined],
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("claude -p timed out after 120s") from exc

        latency_ms = int((time.monotonic() - start) * 1000)

        if result.returncode != 0:
            stderr = (result.stderr or "")[:500]
            raise RuntimeError(f"claude -p exited {result.returncode}: {stderr}")

        return LLMResponse(
            text=result.stdout.strip(),
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=latency_ms,
            model=self._MODEL_LABEL,
        )


# ─── Null provider ───

class NullClient(BaseLLMClient):
    """No-op client — LLM is disabled. Returns empty text with zero latency."""

    def complete(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> LLMResponse:
        return LLMResponse(
            text="",
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0,
            model="none",
        )


# ─── Factory ───

_USE_CASE_SETTING: dict[str, str] = {
    "extraction": "LLM_PROVIDER_EXTRACTION",
    "policy": "LLM_PROVIDER_POLICY",
    "analytics": "LLM_PROVIDER_ANALYTICS",
    "ask_ai": "LLM_PROVIDER_ASK_AI",
}


def get_llm_client(use_case: str) -> BaseLLMClient:
    """Return the appropriate LLM client for the given use_case.

    Provider resolution order:
      1. Per-use-case setting (e.g. LLM_PROVIDER_EXTRACTION)
      2. Global LLM_PROVIDER
      3. "none" (safe default)
    """
    from app.core.config import settings

    setting_name = _USE_CASE_SETTING.get(use_case)
    provider = ""
    if setting_name:
        provider = getattr(settings, setting_name, "").strip()
    if not provider:
        provider = settings.LLM_PROVIDER.strip()
    if not provider:
        provider = "none"
    provider = provider.lower()

    if provider == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            logger.warning(
                "LLM provider 'anthropic' requested for '%s' but ANTHROPIC_API_KEY is not set; "
                "falling back to NullClient.",
                use_case,
            )
            return NullClient()
        return AnthropicClient(api_key=settings.ANTHROPIC_API_KEY, model=settings.ANTHROPIC_MODEL)

    if provider == "ollama":
        return OllamaClient(base_url=settings.OLLAMA_BASE_URL, model=settings.OLLAMA_MODEL)

    if provider == "claude_code":
        return ClaudeCodeClient()

    if provider == "none":
        return NullClient()

    logger.warning(
        "Unknown LLM provider '%s' for use_case '%s'; using NullClient.", provider, use_case
    )
    return NullClient()
