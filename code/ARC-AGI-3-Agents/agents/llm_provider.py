"""LLM provider abstraction for ARC-AGI-3 agents.

Supports Claude API (development), OpenAI API (alternative), and
local models via llama-cpp-python (Kaggle submission).
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(Protocol):
    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse: ...


# ---------------------------------------------------------------------------
# Claude Provider
# ---------------------------------------------------------------------------

class ClaudeProvider:
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        import anthropic
        self.model = model
        self.client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        )

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        from .tool_interface import to_anthropic_tools

        system = ""
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                chat_messages.append(m)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system,
                messages=chat_messages,
                tools=to_anthropic_tools(tools),
                tool_choice={"type": "any"},
            )
        except Exception as e:
            logger.error(f"Claude API error: {e}")
            return LLMResponse(text=f"API error: {e}")

        result = LLMResponse(
            input_tokens=response.usage.input_tokens if response.usage else 0,
            output_tokens=response.usage.output_tokens if response.usage else 0,
        )

        for block in response.content:
            if block.type == "text":
                result.text += block.text
            elif block.type == "tool_use":
                result.tool_calls.append(ToolCall(
                    name=block.name,
                    arguments=block.input or {},
                ))

        return result


# ---------------------------------------------------------------------------
# OpenAI Provider
# ---------------------------------------------------------------------------

class OpenAIProvider:
    def __init__(self, model: str = "gpt-5.4-nano"):
        from openai import OpenAI
        self.model = model
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        from .tool_interface import to_openai_tools

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=to_openai_tools(tools),
                tool_choice="required",
            )
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return LLMResponse(text=f"API error: {e}")

        msg = response.choices[0].message
        result = LLMResponse(
            text=msg.content or "",
            input_tokens=response.usage.total_tokens if response.usage else 0,
        )

        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                result.tool_calls.append(ToolCall(
                    name=tc.function.name,
                    arguments=args,
                ))

        return result


# ---------------------------------------------------------------------------
# Local Model Provider (for Kaggle — llama-cpp-python)
# ---------------------------------------------------------------------------

class LocalProvider:
    def __init__(self, model_path: str = "models/qwen2.5-7b-instruct-q4_k_m.gguf"):
        try:
            from llama_cpp import Llama
            self.llm = Llama(
                model_path=model_path,
                n_ctx=4096,
                n_gpu_layers=-1,
                verbose=False,
            )
            self._available = True
        except ImportError:
            logger.warning("llama-cpp-python not installed. LocalProvider unavailable.")
            self._available = False
            self.llm = None

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        if not self._available:
            return LLMResponse(text="LocalProvider not available (install llama-cpp-python)")

        tool_desc = self._format_tools_for_prompt(tools)
        system_msg = ""
        user_msgs = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_msgs.append(m)

        prompt = self._build_chat_prompt(system_msg, tool_desc, user_msgs)

        try:
            output = self.llm(
                prompt,
                max_tokens=512,
                temperature=0.1,
                stop=["</tool_call>", "\n\nHuman:"],
            )
            text = output["choices"][0]["text"].strip()
        except Exception as e:
            logger.error(f"Local LLM error: {e}")
            return LLMResponse(text=f"Local LLM error: {e}")

        result = LLMResponse(
            text=text,
            input_tokens=output.get("usage", {}).get("prompt_tokens", 0),
            output_tokens=output.get("usage", {}).get("completion_tokens", 0),
        )

        tool_call = self._parse_tool_call(text)
        if tool_call:
            result.tool_calls.append(tool_call)

        return result

    def _format_tools_for_prompt(self, tools: list[dict]) -> str:
        lines = ["Available tools (respond with JSON tool call):"]
        for t in tools:
            params = t.get("parameters", {}).get("properties", {})
            param_str = ", ".join(f"{k}: {v.get('type', '?')}" for k, v in params.items())
            lines.append(f"- {t['name']}({param_str}): {t['description'][:80]}")
        lines.append('\nRespond with: {"tool": "tool_name", "arguments": {...}}')
        return "\n".join(lines)

    def _build_chat_prompt(self, system: str, tool_desc: str, messages: list[dict]) -> str:
        parts = [f"<|im_start|>system\n{system}\n\n{tool_desc}<|im_end|>"]
        for m in messages:
            role = m["role"]
            content = m["content"] if isinstance(m["content"], str) else json.dumps(m["content"])
            parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)

    def _parse_tool_call(self, text: str) -> Optional[ToolCall]:
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
            if "tool" in data:
                return ToolCall(name=data["tool"], arguments=data.get("arguments", {}))
            if "name" in data:
                return ToolCall(name=data["name"], arguments=data.get("arguments", {}))
        except (ValueError, json.JSONDecodeError):
            pass
        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_provider(provider_type: Optional[str] = None) -> LLMProvider:
    provider_type = provider_type or os.environ.get("LLM_PROVIDER", "claude")
    if provider_type == "claude":
        model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
        return ClaudeProvider(model=model)
    elif provider_type == "openai":
        model = os.environ.get("OPENAI_MODEL", "gpt-5.4-nano")
        return OpenAIProvider(model=model)
    elif provider_type == "local":
        path = os.environ.get("LOCAL_MODEL_PATH", "models/qwen2.5-7b-instruct-q4_k_m.gguf")
        return LocalProvider(model_path=path)
    else:
        raise ValueError(f"Unknown LLM provider: {provider_type}")
