from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

# ============================================================================
# Model Configurations - Optimized for Subtitle Translation
# ============================================================================

SUBTITLE_MODELS = {
    # TIER 1: Premium (Best quality, higher cost)
    "codex": {
        "id": "gpt-5.6-sol",
        "name": "GPT-5.6 Sol (Codex CLI)",
        "cost_per_1m_input": 0.0,
        "cost_per_1m_output": 0.0,
        "strengths": ["best Estonian", "no API cost", "configurable reasoning effort"],
        "tier": "premium",
        "recommended_for": ["films", "drama", "everything"],
        "supports_batch": True,
        "max_context": 272_000,
        "max_output": 128_000,
        "backend": "codex",
    },
    "claude": {
        "id": "opus",
        "name": "Opus 5 (Claude Code CLI)",
        "cost_per_1m_input": 0.0,
        "cost_per_1m_output": 0.0,
        "strengths": ["nuanced dialogue", "no API cost", "max reasoning effort"],
        "tier": "premium",
        "recommended_for": ["films", "drama", "complex dialogue"],
        "supports_batch": True,
        "max_context": 1_000_000,
        "max_output": 64_000,
        "backend": "claude",
    },
    "gpt-5.6-sol": {
        "id": "openai/gpt-5.6-sol",
        "name": "GPT-5.6 Sol",
        "cost_per_1m_input": 2.00,
        "cost_per_1m_output": 10.0,
        "strengths": ["same model as codex", "best Estonian", "1M+ context"],
        "tier": "premium",
        "recommended_for": ["films", "drama", "everything"],
        "supports_batch": True,
        "max_context": 1_050_000,
        "max_output": 128_000,
    },
    "gpt-5.5": {
        "id": "openai/gpt-5.5",
        "name": "GPT-5.5",
        "cost_per_1m_input": 5.00,
        "cost_per_1m_output": 30.0,
        "strengths": ["newest frontier model", "1M+ context", "best translation quality"],
        "tier": "premium",
        "recommended_for": ["films", "drama", "complex dialogue"],
        "supports_batch": True,
        "max_context": 1_050_000,
        "max_output": 128_000,
    },
    "gpt-5.4-pro": {
        "id": "openai/gpt-5.4-pro",
        "name": "GPT-5.4 Pro",
        "cost_per_1m_input": 2.50,
        "cost_per_1m_output": 20.0,
        "strengths": ["most advanced model", "best reasoning", "natural phrasing"],
        "tier": "premium",
        "recommended_for": ["films", "drama", "quality-first"],
    },
    "gpt-5.4": {
        "id": "openai/gpt-5.4",
        "name": "GPT-5.4",
        "cost_per_1m_input": 2.00,
        "cost_per_1m_output": 16.0,
        "strengths": ["latest frontier model", "1M+ context", "excellent reasoning"],
        "tier": "premium",
        "recommended_for": ["films", "drama", "complex dialogue"],
        "supports_batch": True,
        "max_context": 1_000_000,
        "max_output": 65_536,
    },
    "gpt-5.3": {
        "id": "openai/gpt-5.3-chat",
        "name": "GPT-5.3 Chat",
        "cost_per_1m_input": 1.75,
        "cost_per_1m_output": 14.0,
        "strengths": ["excellent quality", "consistent"],
        "tier": "premium",
        "recommended_for": ["films", "professional work"],
    },
    "gpt-5.2": {
        "id": "openai/gpt-5.2",
        "name": "GPT-5.2",
        "cost_per_1m_input": 1.75,
        "cost_per_1m_output": 14.0,
        "strengths": ["high quality", "reliable"],
        "tier": "premium",
        "recommended_for": ["films", "general"],
    },
    "gpt-5.1": {
        "id": "openai/gpt-5.1",
        "name": "GPT-5.1",
        "cost_per_1m_input": 1.25,
        "cost_per_1m_output": 10.0,
        "strengths": ["good quality", "consistent"],
        "tier": "premium",
        "recommended_for": ["films", "professional work"],
    },
    "gpt-5": {
        "id": "openai/gpt-5",
        "name": "GPT-5",
        "cost_per_1m_input": 1.25,
        "cost_per_1m_output": 10.0,
        "strengths": ["reliable", "proven"],
        "tier": "premium",
        "recommended_for": ["general", "films"],
    },
    "claude-opus": {
        "id": "anthropic/claude-opus-4",
        "name": "Claude Opus 4",
        "cost_per_1m_input": 15.0,
        "cost_per_1m_output": 75.0,
        "strengths": ["nuanced dialogue", "cultural context"],
        "tier": "premium",
        "recommended_for": ["complex dialogue", "literary"],
    },
    "gemini-pro": {
        "id": "google/gemini-3.1-pro-preview",
        "name": "Gemini 3.1 Pro Preview",
        "cost_per_1m_input": 2.0,
        "cost_per_1m_output": 12.0,
        "strengths": ["1M context", "batch translation", "great reasoning", "fast"],
        "tier": "premium",
        "recommended_for": ["films", "batch", "full-context"],
        "supports_batch": True,
        "max_context": 1_000_000,
        "max_output": 65_536,
    },
    # TIER 2: Value (Good quality, reasonable cost)
    "gpt-5.4-mini": {
        "id": "openai/gpt-5.4-mini",
        "name": "GPT-5.4 Mini",
        "cost_per_1m_input": 0.30,
        "cost_per_1m_output": 2.50,
        "strengths": ["latest mini model", "great quality/cost ratio"],
        "tier": "value",
        "recommended_for": ["tv shows", "general", "quality on a budget"],
    },
    "gpt-5.4-nano": {
        "id": "openai/gpt-5.4-nano",
        "name": "GPT-5.4 Nano",
        "cost_per_1m_input": 0.08,
        "cost_per_1m_output": 0.50,
        "strengths": ["cheapest latest-gen", "fast", "good for translation"],
        "tier": "value",
        "recommended_for": ["bulk", "simple content"],
    },
    "gpt-5-mini": {
        "id": "openai/gpt-5-mini",
        "name": "GPT-5 Mini",
        "cost_per_1m_input": 0.25,
        "cost_per_1m_output": 2.0,
        "strengths": ["good quality", "cost-effective"],
        "tier": "value",
        "recommended_for": ["tv shows", "general"],
    },
    "gpt-5-nano": {
        "id": "openai/gpt-5-nano",
        "name": "GPT-5 Nano",
        "cost_per_1m_input": 0.05,
        "cost_per_1m_output": 0.40,
        "strengths": ["very cheap", "fast", "good for translation"],
        "tier": "value",
        "recommended_for": ["bulk", "simple content"],
    },
    "gpt-4.1-mini": {
        "id": "openai/gpt-4.1-mini",
        "name": "GPT-4.1 Mini",
        "cost_per_1m_input": 0.40,
        "cost_per_1m_output": 1.60,
        "strengths": ["reliable", "fast"],
        "tier": "value",
        "recommended_for": ["general", "tv shows"],
    },
    "grok-3-mini": {
        "id": "x-ai/grok-3-mini",
        "name": "Grok 3 Mini",
        "cost_per_1m_input": 0.30,
        "cost_per_1m_output": 0.50,
        "strengths": ["fast", "good value"],
        "tier": "value",
        "recommended_for": ["general"],
    },
    # TIER 3: Budget (Lowest cost)
    "mistral-small": {
        "id": "mistralai/mistral-small-3.1-24b-instruct",
        "name": "Mistral Small 3.1",
        "cost_per_1m_input": 0.03,
        "cost_per_1m_output": 0.11,
        "strengths": ["cheapest capable", "fast"],
        "tier": "budget",
        "recommended_for": ["bulk", "budget projects"],
    },
    "deepseek": {
        "id": "deepseek/deepseek-chat-v3.1",
        "name": "DeepSeek Chat v3.1",
        "cost_per_1m_input": 0.10,
        "cost_per_1m_output": 1.0,
        "strengths": ["very cheap", "decent quality"],
        "tier": "budget",
        "recommended_for": ["bulk", "testing"],
    },
    "qwen-72b": {
        "id": "qwen/qwen-2.5-72b-instruct",
        "name": "Qwen 2.5 72B",
        "cost_per_1m_input": 0.35,
        "cost_per_1m_output": 0.40,
        "strengths": ["multilingual", "good value"],
        "tier": "budget",
        "recommended_for": ["multilingual content"],
    },
}

# Default model - Codex CLI (best Estonian, billed to the ChatGPT subscription)
DEFAULT_MODEL = "codex"


class SubtitleType(Enum):
    DIALOGUE = "dialogue"
    NARRATIVE = "narrative"
    SOUND_EFFECT = "sound_effect"
    UNKNOWN = "unknown"


@dataclass
class Subtitle:
    index: str
    timestamp: str
    text: str
    subtitle_type: SubtitleType | None = None
    translated_text: str | None = None
    line_count: int = 1


@dataclass
class TranslationStats:
    """Track translation statistics and costs"""

    total_subtitles: int = 0
    completed: int = 0
    failed: int = 0
    cached: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    start_time: datetime | None = None
    end_time: datetime | None = None
