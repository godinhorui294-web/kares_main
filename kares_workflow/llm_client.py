"""
kares_workflow.llm_client — provider-agnostic LLM client (OpenAI-compatible
protocol).

Supports deepseek / dashscope(qwen) / moonshot(kimi), all accessed through
the openai SDK.
"""
from typing import List, Dict, Optional

try:
    from openai import OpenAI
    _HAS_OPENAI = True
except ImportError:  # pragma: no cover
    OpenAI = None
    _HAS_OPENAI = False

from . import config

# provider -> OpenAI-compatible base_url
_PROVIDER_BASE_URL = {
    "deepseek": "https://api.deepseek.com/v1",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "kimi": "https://api.moonshot.cn/v1",
    "openai": None,  # use the SDK default
}


class LLMClient:
    """Unified LLM call wrapper; picks the base_url per provider."""

    def __init__(self):
        if not _HAS_OPENAI:
            raise ImportError(
                "The openai package is not installed. Run: pip install openai"
            )
        self._clients = {}  # one client per provider

    def _get_client(self, provider: str):
        provider = provider.lower()
        if provider in self._clients:
            return self._clients[provider]
        api_key = config.get_api_key(provider)
        if not api_key:
            raise RuntimeError(
                f"No API key found for provider='{provider}'. "
                f"Set the corresponding _API_KEY in the root config.py or "
                f"via an environment variable."
            )
        base_url = _PROVIDER_BASE_URL.get(provider)
        client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
        self._clients[provider] = client
        return client

    def chat(self, messages: List[Dict], role: str = "generation",
             model_cfg: Optional[Dict] = None, max_retries: int = 2) -> str:
        """
        Call the LLM and return its text.

        Args:
            messages: OpenAI message list [{"role": "system"|"user"|"assistant", "content": "..."}]
            role: model role (generation/reflection/barrier); selects the model config
            model_cfg: explicit model config; overrides role
            max_retries: number of retries on failure
        """
        cfg = model_cfg or config.get_model_cfg(role)
        provider = cfg.get("provider", "deepseek")
        client = self._get_client(provider)
        model_name = cfg.get("model_name")
        temperature = cfg.get("temperature", 0.7)
        max_tokens = cfg.get("max_tokens", 16384)

        last_err = None
        for attempt in range(max_retries + 1):
            try:
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return resp.choices[0].message.content or ""
            except Exception as e:  # pragma: no cover
                last_err = e
                # simple backoff
                import time
                if attempt < max_retries:
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"LLM call failed (role={role}, model={model_name}): {last_err}")

    def chat_json(self, messages: List[Dict], role: str = "reflection",
                  model_cfg: Optional[Dict] = None) -> str:
        """Same as chat, but semantically for calls that expect JSON output (reflection/barrier)."""
        return self.chat(messages, role=role, model_cfg=model_cfg)
