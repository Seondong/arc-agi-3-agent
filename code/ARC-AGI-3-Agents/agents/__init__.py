from typing import Any, Type, cast

from dotenv import load_dotenv

from .agent import Agent, Playback
from .recorder import Recorder
from .swarm import Swarm

load_dotenv()


def _optional_import(
    import_fn: Any,
    fallback_names: list[str],
) -> dict[str, Any]:
    try:
        return import_fn()
    except ModuleNotFoundError:
        return {name: None for name in fallback_names}


_langgraph_functional = _optional_import(
    lambda: __import__(
        "agents.templates.langgraph_functional_agent",
        fromlist=["LangGraphFunc", "LangGraphTextOnly"],
    ).__dict__,
    ["LangGraphFunc", "LangGraphTextOnly"],
)
LangGraphFunc = _langgraph_functional.get("LangGraphFunc")
LangGraphTextOnly = _langgraph_functional.get("LangGraphTextOnly")

_langgraph_random = _optional_import(
    lambda: __import__(
        "agents.templates.langgraph_random_agent",
        fromlist=["LangGraphRandom"],
    ).__dict__,
    ["LangGraphRandom"],
)
LangGraphRandom = _langgraph_random.get("LangGraphRandom")

_langgraph_thinking = _optional_import(
    lambda: __import__(
        "agents.templates.langgraph_thinking",
        fromlist=["LangGraphThinking"],
    ).__dict__,
    ["LangGraphThinking"],
)
LangGraphThinking = _langgraph_thinking.get("LangGraphThinking")

_claude_agent = _optional_import(
    lambda: __import__(
        "agents.templates.claude_agent",
        fromlist=["ClaudeLLM"],
    ).__dict__,
    ["ClaudeLLM"],
)
ClaudeLLM = _claude_agent.get("ClaudeLLM")

_llm_agents = _optional_import(
    lambda: __import__(
        "agents.templates.llm_agents",
        fromlist=["LLM", "FastLLM", "GuidedLLM", "ReasoningLLM"],
    ).__dict__,
    ["LLM", "FastLLM", "GuidedLLM", "ReasoningLLM"],
)
LLM = _llm_agents.get("LLM")
FastLLM = _llm_agents.get("FastLLM")
GuidedLLM = _llm_agents.get("GuidedLLM")
ReasoningLLM = _llm_agents.get("ReasoningLLM")

_smart_agent = _optional_import(
    lambda: __import__(
        "agents.templates.smart_agent",
        fromlist=["SmartAgent"],
    ).__dict__,
    ["SmartAgent"],
)
SmartAgent = _smart_agent.get("SmartAgent")

_multimodal = _optional_import(
    lambda: __import__(
        "agents.templates.multimodal",
        fromlist=["MultiModalLLM"],
    ).__dict__,
    ["MultiModalLLM"],
)
MultiModalLLM = _multimodal.get("MultiModalLLM")

_random_agent = _optional_import(
    lambda: __import__(
        "agents.templates.random_agent",
        fromlist=["Random"],
    ).__dict__,
    ["Random"],
)
Random = _random_agent.get("Random")

_reasoning_agent = _optional_import(
    lambda: __import__(
        "agents.templates.reasoning_agent",
        fromlist=["ReasoningAgent"],
    ).__dict__,
    ["ReasoningAgent"],
)
ReasoningAgent = _reasoning_agent.get("ReasoningAgent")

_smolagents = _optional_import(
    lambda: __import__(
        "agents.templates.smolagents",
        fromlist=["SmolCodingAgent", "SmolVisionAgent"],
    ).__dict__,
    ["SmolCodingAgent", "SmolVisionAgent"],
)
SmolCodingAgent = _smolagents.get("SmolCodingAgent")
SmolVisionAgent = _smolagents.get("SmolVisionAgent")

_cnn_agent = _optional_import(
    lambda: __import__(
        "agents.templates.cnn_agent",
        fromlist=["CNNAgent"],
    ).__dict__,
    ["CNNAgent"],
)
CNNAgent = _cnn_agent.get("CNNAgent")

_hybrid_agent = _optional_import(
    lambda: __import__(
        "agents.templates.hybrid_agent",
        fromlist=["MyAgent"],
    ).__dict__,
    ["MyAgent"],
)
HybridAgent = _hybrid_agent.get("MyAgent")

AVAILABLE_AGENTS: dict[str, Type[Agent]] = {
    cls.__name__.lower(): cast(Type[Agent], cls)
    for cls in Agent.__subclasses__()
    if cls.__name__ != "Playback"
}

# add all the recording files as valid agent names
for rec in Recorder.list():
    AVAILABLE_AGENTS[rec] = Playback

# update the agent dictionary to include subclasses of LLM class
if ReasoningAgent is not None:
    AVAILABLE_AGENTS["reasoningagent"] = ReasoningAgent
if ClaudeLLM is not None:
    AVAILABLE_AGENTS["claude"] = ClaudeLLM
if SmartAgent is not None:
    AVAILABLE_AGENTS["smart"] = SmartAgent
if CNNAgent is not None:
    AVAILABLE_AGENTS["cnn"] = CNNAgent
if HybridAgent is not None:
    AVAILABLE_AGENTS["hybrid"] = HybridAgent

__all__ = [
    "Swarm",
    "Agent",
    "Recorder",
    "Playback",
    "AVAILABLE_AGENTS",
]

for name, value in [
    ("Random", Random),
    ("LangGraphFunc", LangGraphFunc),
    ("LangGraphTextOnly", LangGraphTextOnly),
    ("LangGraphThinking", LangGraphThinking),
    ("LangGraphRandom", LangGraphRandom),
    ("LLM", LLM),
    ("FastLLM", FastLLM),
    ("ReasoningLLM", ReasoningLLM),
    ("GuidedLLM", GuidedLLM),
    ("ReasoningAgent", ReasoningAgent),
    ("SmolCodingAgent", SmolCodingAgent),
    ("SmolVisionAgent", SmolVisionAgent),
    ("MultiModalLLM", MultiModalLLM),
    ("ClaudeLLM", ClaudeLLM),
    ("SmartAgent", SmartAgent),
    ("CNNAgent", CNNAgent),
]:
    if value is not None:
        __all__.append(name)
