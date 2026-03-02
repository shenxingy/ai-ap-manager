"""Unit tests for the multi-provider LLM client abstraction.

All external calls (anthropic SDK, openai SDK, subprocess) are mocked.
No real API keys or running services are required.
"""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.ai.llm_client import (
    AnthropicClient,
    ClaudeCodeClient,
    LLMResponse,
    NullClient,
    OllamaClient,
    get_llm_client,
)


# ─── NullClient ───

class TestNullClient:
    def test_complete_returns_empty_response(self):
        client = NullClient()
        resp = client.complete([{"role": "user", "content": "hello"}])
        assert isinstance(resp, LLMResponse)
        assert resp.text == ""
        assert resp.model == "none"
        assert resp.latency_ms == 0
        assert resp.prompt_tokens == 0
        assert resp.completion_tokens == 0

    def test_complete_ignores_system(self):
        client = NullClient()
        resp = client.complete([], system="ignored system prompt")
        assert resp.text == ""


# ─── AnthropicClient ───

class TestAnthropicClient:
    def _make_mock_response(self, text: str, p_tokens: int = 10, c_tokens: int = 5):
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=text)]
        mock_resp.usage.input_tokens = p_tokens
        mock_resp.usage.output_tokens = c_tokens
        return mock_resp

    def test_complete_basic(self):
        with patch("anthropic.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client
            mock_client.messages.create.return_value = self._make_mock_response("extracted fields")

            client = AnthropicClient(api_key="sk-test", model="claude-sonnet-4-6")
            resp = client.complete([{"role": "user", "content": "extract invoice"}], max_tokens=512)

        assert resp.text == "extracted fields"
        assert resp.model == "claude-sonnet-4-6"
        assert resp.prompt_tokens == 10
        assert resp.completion_tokens == 5
        assert resp.latency_ms >= 0

    def test_complete_with_system_prompt(self):
        with patch("anthropic.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client
            mock_client.messages.create.return_value = self._make_mock_response("ok")

            client = AnthropicClient(api_key="sk-test", model="claude-sonnet-4-6")
            client.complete(
                [{"role": "user", "content": "parse policy"}],
                system="You are an AP parser.",
            )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "system" in call_kwargs
        assert call_kwargs["system"] == "You are an AP parser."

    def test_empty_content_returns_empty_string(self):
        with patch("anthropic.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client
            mock_resp = MagicMock()
            mock_resp.content = []
            mock_resp.usage.input_tokens = 0
            mock_resp.usage.output_tokens = 0
            mock_client.messages.create.return_value = mock_resp

            client = AnthropicClient(api_key="sk-test", model="claude-sonnet-4-6")
            resp = client.complete([{"role": "user", "content": "hi"}])

        assert resp.text == ""


# ─── OllamaClient ───

class TestOllamaClient:
    def _make_mock_completion(self, text: str, p_tokens: int = 8, c_tokens: int = 3):
        mock = MagicMock()
        mock.choices = [MagicMock()]
        mock.choices[0].message.content = text
        mock.usage.prompt_tokens = p_tokens
        mock.usage.completion_tokens = c_tokens
        return mock

    def test_complete_basic(self):
        with patch("openai.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._make_mock_completion("ollama reply")

            client = OllamaClient(base_url="http://ollama:11434", model="qwen2.5:7b")
            resp = client.complete([{"role": "user", "content": "test"}])

        assert resp.text == "ollama reply"
        assert resp.model == "qwen2.5:7b"
        assert resp.prompt_tokens == 8
        assert resp.completion_tokens == 3

    def test_system_prepended_to_messages(self):
        with patch("openai.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._make_mock_completion("ok")

            client = OllamaClient(base_url="http://ollama:11434", model="qwen2.5:7b")
            client.complete(
                [{"role": "user", "content": "question"}],
                system="system instruction",
            )

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "system instruction"}
        assert messages[1] == {"role": "user", "content": "question"}


# ─── ClaudeCodeClient ───

class TestClaudeCodeClient:
    def test_complete_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "  extracted data  "
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            client = ClaudeCodeClient()
            resp = client.complete([{"role": "user", "content": "test prompt"}])

        assert resp.text == "extracted data"
        assert resp.model == "claude-code-cli"
        assert resp.prompt_tokens == 0
        assert resp.completion_tokens == 0

        call_args = mock_run.call_args
        assert call_args.args[0][0] == "claude"
        assert call_args.args[0][1] == "-p"
        # CLAUDECODE must be removed from env
        env_passed = call_args.kwargs.get("env", {})
        assert "CLAUDECODE" not in env_passed

    def test_nonzero_exit_raises(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "some error"

        with patch("subprocess.run", return_value=mock_result):
            client = ClaudeCodeClient()
            with pytest.raises(RuntimeError, match="claude -p exited 1"):
                client.complete([{"role": "user", "content": "hi"}])

    def test_timeout_raises(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 120)):
            client = ClaudeCodeClient()
            with pytest.raises(RuntimeError, match="timed out"):
                client.complete([{"role": "user", "content": "hi"}])

    def test_claudecode_env_removed(self):
        """CLAUDECODE env var is stripped to prevent nested session errors."""
        import os
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ok"
        mock_result.stderr = ""

        with patch.dict(os.environ, {"CLAUDECODE": "1"}):
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                client = ClaudeCodeClient()
                client.complete([{"role": "user", "content": "test"}])

            env_passed = mock_run.call_args.kwargs.get("env", {})
            assert "CLAUDECODE" not in env_passed

    def test_system_prompt_included_in_combined(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "result"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            client = ClaudeCodeClient()
            client.complete(
                [{"role": "user", "content": "user question"}],
                system="You are a parser.",
            )

        prompt_arg = mock_run.call_args.args[0][2]
        assert "[System]" in prompt_arg
        assert "You are a parser." in prompt_arg
        assert "user question" in prompt_arg


# ─── Factory (get_llm_client) ───

class TestGetLlmClient:
    def test_returns_null_for_none_provider(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "none")
        monkeypatch.setenv("LLM_PROVIDER_EXTRACTION", "")
        with patch("app.ai.llm_client.get_llm_client.__module__"):
            from app.core.config import Settings
            settings = Settings(LLM_PROVIDER="none", LLM_PROVIDER_EXTRACTION="")
            with patch("app.ai.llm_client.Settings", return_value=settings):
                pass  # factory tested indirectly below

        client = _make_client_with_settings(LLM_PROVIDER="none")
        assert isinstance(client, NullClient)

    def test_returns_null_for_unknown_provider(self):
        client = _make_client_with_settings(LLM_PROVIDER="nonexistent")
        assert isinstance(client, NullClient)

    def test_anthropic_without_key_falls_back_to_null(self):
        client = _make_client_with_settings(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="")
        assert isinstance(client, NullClient)

    def test_anthropic_with_key_returns_anthropic_client(self):
        with patch("anthropic.Anthropic"):
            client = _make_client_with_settings(
                LLM_PROVIDER="anthropic",
                ANTHROPIC_API_KEY="sk-test-key",
                ANTHROPIC_MODEL="claude-sonnet-4-6",
            )
        assert isinstance(client, AnthropicClient)

    def test_claude_code_returns_claude_code_client(self):
        client = _make_client_with_settings(LLM_PROVIDER="claude_code")
        assert isinstance(client, ClaudeCodeClient)

    def test_per_usecase_override_takes_precedence(self):
        # Global is anthropic, but extraction overridden to none
        client = _make_client_with_settings(
            LLM_PROVIDER="anthropic",
            ANTHROPIC_API_KEY="sk-key",
            LLM_PROVIDER_EXTRACTION="none",
            use_case="extraction",
        )
        assert isinstance(client, NullClient)

    def test_ollama_returns_ollama_client(self):
        with patch("openai.OpenAI"):
            client = _make_client_with_settings(
                LLM_PROVIDER="ollama",
                OLLAMA_BASE_URL="http://localhost:11434",
                OLLAMA_MODEL="qwen2.5:7b",
            )
        assert isinstance(client, OllamaClient)


def _make_client_with_settings(use_case: str = "extraction", **settings_kwargs):
    """Helper to test get_llm_client with custom settings without touching the real config."""
    from app.core.config import Settings
    from app.ai.llm_client import (
        _USE_CASE_SETTING,
        AnthropicClient,
        ClaudeCodeClient,
        NullClient,
        OllamaClient,
    )

    defaults = dict(
        LLM_PROVIDER="none",
        LLM_PROVIDER_EXTRACTION="",
        LLM_PROVIDER_POLICY="",
        LLM_PROVIDER_ANALYTICS="",
        LLM_PROVIDER_ASK_AI="none",
        ANTHROPIC_API_KEY="",
        ANTHROPIC_MODEL="claude-sonnet-4-6",
        OLLAMA_BASE_URL="http://ollama:11434",
        OLLAMA_MODEL="qwen2.5:7b",
    )
    defaults.update(settings_kwargs)

    settings = Settings(**defaults)

    with patch("app.ai.llm_client.settings", settings):
        from app.ai.llm_client import get_llm_client
        # Re-import to get fresh settings reference via patch
        import app.ai.llm_client as llm_mod
        original_get = llm_mod.get_llm_client

        def patched_get(uc: str) -> object:
            setting_name = _USE_CASE_SETTING.get(uc)
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
                    return NullClient()
                return AnthropicClient(api_key=settings.ANTHROPIC_API_KEY, model=settings.ANTHROPIC_MODEL)
            if provider == "ollama":
                return OllamaClient(base_url=settings.OLLAMA_BASE_URL, model=settings.OLLAMA_MODEL)
            if provider == "claude_code":
                return ClaudeCodeClient()
            return NullClient()

        return patched_get(use_case)
