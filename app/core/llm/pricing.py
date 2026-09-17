from decimal import Decimal

from app.core.llm.schemas import LLMUsage

_MILLION = Decimal("1000000")
_PRICES: dict[str, tuple[Decimal, Decimal, Decimal]] = {
    "sabia-4-thinking": (Decimal("5"), Decimal("1.25"), Decimal("40")),
    "sabia-4": (Decimal("5"), Decimal("1.25"), Decimal("20")),
    "sabiazinho-4": (Decimal("1"), Decimal("0.25"), Decimal("4")),
    "sabia-4-thinking-br-sp": (Decimal("6.50"), Decimal("1.63"), Decimal("52")),
    "sabia-4-br-sp": (Decimal("6.50"), Decimal("1.63"), Decimal("26")),
    "sabiazinho-4-br-sp": (Decimal("1.30"), Decimal("0.33"), Decimal("5.20")),
}


def actual_cost_brl(model: str, usage: LLMUsage) -> Decimal | None:
    prices = _PRICES.get(model)
    if prices is None or usage.input_tokens is None or usage.output_tokens is None:
        return None
    input_price, cached_input_price, output_price = prices
    cached = min(usage.cached_input_tokens or 0, usage.input_tokens)
    uncached = usage.input_tokens - cached
    total = uncached * input_price + cached * cached_input_price
    total += usage.output_tokens * output_price
    return total / _MILLION


def maximum_cost_brl(*, model: str, input_text: str, max_output_tokens: int) -> Decimal | None:
    prices = _PRICES.get(model)
    if prices is None:
        return None
    input_price, _cached_input_price, output_price = prices
    # UTF-8 byte length deliberately overestimates the tokenizer output. A
    # fixed allowance covers the provider's message/instructions framing.
    input_token_upper_bound = len(input_text.encode("utf-8")) + 128
    return (input_token_upper_bound * input_price + max_output_tokens * output_price) / _MILLION
