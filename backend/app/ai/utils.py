from typing import Any


def extract_completion_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content", "")
    return normalize_text_content(content, separator="\n")


def extract_stream_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""

    delta = choices[0].get("delta", {})
    if not isinstance(delta, dict):
        return ""

    return normalize_text_content(delta.get("content", ""), separator="")


def normalize_text_content(content: Any, separator: str) -> str:
    if isinstance(content, str):
        return content.strip() if separator else content
    if isinstance(content, list):
        fragments: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and item.get("text"):
                fragments.append(str(item["text"]))
        if separator:
            return separator.join(fragment.strip() for fragment in fragments if fragment).strip()
        return separator.join(fragments)
    return ""
