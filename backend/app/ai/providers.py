from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.ai import AiProvider


@dataclass(frozen=True)
class AiProviderProfile:
    provider: AiProvider
    display_name: str
    base_url_hint: str
    model_hint: str
    api_key_required: bool = True

    def build_chat_url(self, base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if normalized.endswith("/chat/completions"):
            return normalized
        return f"{normalized}/chat/completions"

    def build_headers(self, api_key: str | None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def build_payload(self, model: str, messages: list[dict[str, str]], *, stream: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if stream:
            payload["stream"] = True
        return payload

    def missing_config_fields(self, base_url: str | None, api_key: str | None, model: str | None) -> list[str]:
        missing = []
        if not base_url:
            missing.append("base_url")
        if not model:
            missing.append("model")
        if self.api_key_required and not api_key:
            missing.append("api_key")
        return missing

    def is_configured(self, base_url: str | None, api_key: str | None, model: str | None) -> bool:
        return not self.missing_config_fields(base_url, api_key, model)


PROVIDER_REGISTRY: dict[AiProvider, AiProviderProfile] = {
    AiProvider.OPENAI_COMPATIBLE: AiProviderProfile(
        provider=AiProvider.OPENAI_COMPATIBLE,
        display_name="OpenAI Compatible",
        base_url_hint="https://api.openai.com/v1",
        model_hint="gpt-4o-mini / gpt-4.1-mini",
    ),
    AiProvider.DEEPSEEK: AiProviderProfile(
        provider=AiProvider.DEEPSEEK,
        display_name="DeepSeek",
        base_url_hint="https://api.deepseek.com",
        model_hint="deepseek-chat",
    ),
    AiProvider.SILICONFLOW: AiProviderProfile(
        provider=AiProvider.SILICONFLOW,
        display_name="SiliconFlow",
        base_url_hint="https://api.siliconflow.cn/v1",
        model_hint="Qwen/Qwen2.5-72B-Instruct",
    ),
    AiProvider.OLLAMA: AiProviderProfile(
        provider=AiProvider.OLLAMA,
        display_name="Ollama",
        base_url_hint="http://localhost:11434/v1",
        model_hint="qwen2.5:7b / llama3.1:8b",
        api_key_required=False,
    ),
    AiProvider.CUSTOM: AiProviderProfile(
        provider=AiProvider.CUSTOM,
        display_name="Custom",
        base_url_hint="自定义 OpenAI-compatible 兼容地址",
        model_hint="填写兼容服务支持的模型名",
    ),
}


def get_provider_profile(provider: AiProvider | str) -> AiProviderProfile:
    provider_enum = provider if isinstance(provider, AiProvider) else AiProvider(provider)
    return PROVIDER_REGISTRY.get(provider_enum, PROVIDER_REGISTRY[AiProvider.OPENAI_COMPATIBLE])
