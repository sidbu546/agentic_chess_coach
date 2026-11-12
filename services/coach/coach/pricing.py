"""USD per 1M tokens (input, cached input, output) for cost logging.

Source: developers.openai.com/api/docs/pricing, standard tier, checked 2026-11-11.
Output includes reasoning tokens. Unknown models are logged with cost 0.
"""
from __future__ import annotations

from .llm.base import LLMUsage

PRICES: dict[str, tuple[float, float, float]] = {
    "gpt-6.1-sol": (2.00, 0.10, 10.00),
    "gpt-6-sol": (2.00, 0.20, 10.00),
    "gpt-6.1-terra": (1.00, 0.05, 5.00),
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-6-astra": (10.00, 1.00, 50.00),
}


def cost_usd(model: str, u: LLMUsage) -> float:
    price = PRICES.get(model)
    if price is None:
        return 0.0
    p_in, p_cached, p_out = price
    uncached = max(0, u.input_tokens - u.cached_tokens)
    return round((uncached * p_in + u.cached_tokens * p_cached + u.output_tokens * p_out) / 1_000_000, 6)
