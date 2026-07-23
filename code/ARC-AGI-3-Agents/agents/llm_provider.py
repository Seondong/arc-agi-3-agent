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
    """Local LLM provider using transformers + Qwen."""

    def __init__(self, model_name: str = "Qwen/Qwen3.5-0.8B"):
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            logger.info(f"Loading {model_name}...")
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name, dtype=torch.float16, device_map=device,
            )
            self.device = device
            self._available = True
            logger.info(f"Model loaded on {device}")
        except Exception as e:
            logger.warning(f"Failed to load local model: {e}")
            self._available = False
            self.model = None
            self.tokenizer = None

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        import torch

        if not self._available:
            return LLMResponse(text="LocalProvider not available")

        tool_desc = self._format_tools_for_prompt(tools)

        # Inject tool descriptions into system message
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                chat_messages.append({"role": "system", "content": m["content"] + "\n\n" + tool_desc})
            else:
                chat_messages.append(m)

        text = self.tokenizer.apply_chat_template(
            chat_messages, tokenize=False, add_generation_prompt=True,
        )
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=4096)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        try:
            with torch.no_grad():
                output = self.model.generate(
                    **inputs,
                    max_new_tokens=256,
                    temperature=0.7,
                    do_sample=True,
                    pad_token_id=self.tokenizer.eos_token_id,
                )
            response_text = self.tokenizer.decode(
                output[0][inputs["input_ids"].shape[1]:],
                skip_special_tokens=True,
            ).strip()
        except Exception as e:
            logger.error(f"Local LLM generation error: {e}")
            return LLMResponse(text=f"Generation error: {e}")

        result = LLMResponse(text=response_text)
        tool_call = self._parse_tool_call(response_text)
        if tool_call:
            result.tool_calls.append(tool_call)

        return result

    def _format_tools_for_prompt(self, tools: list[dict]) -> str:
        return """## How to respond
You MUST respond with EXACTLY one line in one of these formats:

OBSERVE
TEST ACTION1
TEST ACTION2
TEST ACTION3
TEST ACTION4
TEST ACTION5
TEST ACTION6 x y
EXECUTE RESET
EXECUTE ACTION1
EXECUTE ACTION2
EXECUTE ACTION3
EXECUTE ACTION4
EXECUTE ACTION5
EXECUTE ACTION6 x y
EXECUTE ACTION7
ANALYZE r0 r1 c0 c1

Examples:
- OBSERVE
- TEST ACTION6 62 33
- EXECUTE ACTION6 62 33
- EXECUTE ACTION1
- ANALYZE 24 35 55 63

OBSERVE = see current map and objects
TEST = try an action without committing (for exploration)
EXECUTE = commit an action for real
ANALYZE = zoom into a grid region

Reply with ONE line only. No explanation."""

    def _parse_tool_call(self, text: str) -> Optional[ToolCall]:
        import re

        # Take first non-empty line
        for line in text.strip().split("\n"):
            line = line.strip()
            if line:
                text = line
                break

        if text.upper().startswith("OBSERVE"):
            return ToolCall(name="observe", arguments={})

        # Extract all integers from the text
        nums = [int(x) for x in re.findall(r'\d+', text)]

        if text.upper().startswith("TEST"):
            # Find ACTION name
            action_match = re.search(r'ACTION(\d)', text, re.IGNORECASE)
            if not action_match:
                return ToolCall(name="test_action", arguments={"action": "ACTION1"})
            action = f"ACTION{action_match.group(1)}"
            args: dict = {"action": action}
            # For ACTION6, grab the next two numbers as x, y
            if action == "ACTION6":
                # Remove the "6" from ACTION6 in nums list
                coord_nums = [n for n in nums if n != int(action_match.group(1))]
                if len(coord_nums) >= 2:
                    args["x"] = coord_nums[0]
                    args["y"] = coord_nums[1]
            return ToolCall(name="test_action", arguments=args)

        if text.upper().startswith("EXECUTE"):
            action_match = re.search(r'(RESET|ACTION(\d))', text, re.IGNORECASE)
            if not action_match:
                return ToolCall(name="execute", arguments={"action": "ACTION5"})
            action = action_match.group(1).upper()
            args = {"action": action}
            if action == "ACTION6":
                coord_nums = [n for n in nums if n != 6]
                if len(coord_nums) >= 2:
                    args["x"] = coord_nums[0]
                    args["y"] = coord_nums[1]
            return ToolCall(name="execute", arguments=args)

        if text.upper().startswith("ANALYZE"):
            if len(nums) >= 4:
                return ToolCall(name="analyze_region", arguments={
                    "row_start": nums[0], "row_end": nums[1],
                    "col_start": nums[2], "col_end": nums[3],
                })

        # Fallback: try JSON
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
            if "tool" in data:
                return ToolCall(name=data["tool"], arguments=data.get("arguments", {}))
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
        model = os.environ.get("LOCAL_MODEL", "Qwen/Qwen3.5-0.8B")
        return LocalProvider(model_name=model)
    else:
        raise ValueError(f"Unknown LLM provider: {provider_type}")
