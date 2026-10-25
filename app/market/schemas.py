"""Immutable validated records for market context. No network, no numpy."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping


def _is_finite(value: float | None) -> bool:
    """Return whether an optional numeric field is finite."""
    return value is None or math.isfinite(value)

SMA_STATUSES = ("above", "below", "unavailable")
FIELD_STATUSES = ("ok", "unavailable")
RETURN_KEYS = ("1d", "5d", "1m", "3m")
FUNDAMENTAL_KEYS = ("market_cap", "shares_outstanding", "short_interest_pct", "beta")


@dataclass(frozen=True)
class Quote:
    """Normalized latest quote for one ticker."""

    price: float | None
    previous_close: float | None
    change: float | None
    change_percent: float | None
    volume: float | None
    currency: str | None
    exchange: str | None
    as_of: str

    def __post_init__(self) -> None:
        numeric_values = (self.price, self.previous_close, self.change, self.change_percent, self.volume)
        if not all(_is_finite(value) for value in numeric_values):
            raise ValueError("quote values must be finite")
        if self.price is not None and self.price <= 0:
            raise ValueError("price must be positive")
        if self.price is None and self.previous_close is None:
            raise ValueError("quote requires a finite price or previous_close")
        if self.previous_close is not None and self.previous_close <= 0:
            raise ValueError("previous_close must be positive")
        if self.volume is not None and self.volume < 0:
            raise ValueError("volume must be non-negative")
        if not self.as_of:
            raise ValueError("as_of must be a non-empty string")

    def to_dict(self) -> dict[str, Any]:
        """Convert quote to a JSON-serializable dictionary."""
        return {
            "price": self.price,
            "previous_close": self.previous_close,
            "change": self.change,
            "change_percent": self.change_percent,
            "volume": self.volume,
            "currency": self.currency,
            "exchange": self.exchange,
            "as_of": self.as_of,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Quote:
        """Rebuild quote from its dictionary form, re-validating."""
        return cls(
            price=float(data["price"]) if data.get("price") is not None else None,
            previous_close=float(data["previous_close"]) if data.get("previous_close") is not None else None,
            change=float(data["change"]) if data.get("change") is not None else None,
            change_percent=float(data["change_percent"]) if data.get("change_percent") is not None else None,
            volume=float(data["volume"]) if data.get("volume") is not None else None,
            currency=str(data["currency"]) if data.get("currency") is not None else None,
            exchange=str(data["exchange"]) if data.get("exchange") is not None else None,
            as_of=str(data["as_of"]),
        )


@dataclass(frozen=True)
class CalculatedField:
    """One derived market statistic with full provenance."""

    value: float | None
    lookback: str
    benchmark: str | None
    status: str
    provider: str
    as_of: str

    def __post_init__(self) -> None:
        if self.status not in FIELD_STATUSES:
            raise ValueError(f"status must be one of {FIELD_STATUSES}")
        if self.status == "ok" and self.value is None:
            raise ValueError("value must be present when status is ok")
        if not _is_finite(self.value):
            raise ValueError("calculated field value must be finite")
        if not self.lookback or not self.provider or not self.as_of:
            raise ValueError("lookback, provider, and as_of must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        """Convert field to a JSON-serializable dictionary."""
        return {
            "value": self.value,
            "lookback": self.lookback,
            "benchmark": self.benchmark,
            "status": self.status,
            "provider": self.provider,
            "as_of": self.as_of,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CalculatedField:
        """Rebuild field from its dictionary form, re-validating."""
        return cls(
            value=float(data["value"]) if data.get("value") is not None else None,
            lookback=str(data["lookback"]),
            benchmark=str(data["benchmark"]) if data.get("benchmark") is not None else None,
            status=str(data["status"]),
            provider=str(data["provider"]),
            as_of=str(data["as_of"]),
        )


def _unavailable_field(lookback: str, benchmark: str | None, provider: str, as_of: str) -> CalculatedField:
    """Build the canonical unavailable field for a lookback label."""
    return CalculatedField(
        value=None, lookback=lookback, benchmark=benchmark,
        status="unavailable", provider=provider, as_of=as_of,
    )


@dataclass(frozen=True)
class MarketDataResult:
    """Compact market-context contract for the outer-agent get_market_data tool."""

    ticker: str
    period: str
    quote: Quote | None
    returns: dict[str, CalculatedField]
    volume_ratio_20d: CalculatedField | None
    sma_50_status: str
    sma_200_status: str
    atr_14: CalculatedField | None
    benchmark_return: CalculatedField | None
    fundamentals: dict[str, dict[str, Any]] | None
    provider: str
    as_of: str
    addv_20d: CalculatedField | None = None
    cap_tier: str = "unknown"

    def __post_init__(self) -> None:
        if not self.ticker or self.ticker != self.ticker.upper():
            raise ValueError("ticker must be a non-empty uppercase string")
        if self.sma_50_status not in SMA_STATUSES or self.sma_200_status not in SMA_STATUSES:
            raise ValueError(f"sma statuses must be one of {SMA_STATUSES}")
        for key in self.returns:
            if key not in RETURN_KEYS:
                raise ValueError(f"return keys must be among {RETURN_KEYS}")
        if self.fundamentals is not None:
            for key in self.fundamentals:
                if key not in FUNDAMENTAL_KEYS:
                    raise ValueError(f"fundamental keys must be among {FUNDAMENTAL_KEYS}")

    def to_dict(self) -> dict[str, Any]:
        """Convert result to a JSON-serializable dictionary."""
        return {
            "ticker": self.ticker,
            "period": self.period,
            "quote": self.quote.to_dict() if self.quote else None,
            "returns": {k: v.to_dict() for k, v in self.returns.items()},
            "volume_ratio_20d": self.volume_ratio_20d.to_dict() if self.volume_ratio_20d else None,
            "sma_50_status": self.sma_50_status,
            "sma_200_status": self.sma_200_status,
            "atr_14": self.atr_14.to_dict() if self.atr_14 else None,
            "benchmark_return": self.benchmark_return.to_dict() if self.benchmark_return else None,
            "fundamentals": self.fundamentals,
            "provider": self.provider,
            "as_of": self.as_of,
            "addv_20d": self.addv_20d.to_dict() if self.addv_20d else None,
            "cap_tier": self.cap_tier,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MarketDataResult:
        """Rebuild result from its dictionary form, re-validating."""
        quote = Quote.from_dict(data["quote"]) if data.get("quote") else None
        returns = {k: CalculatedField.from_dict(v) for k, v in data.get("returns", {}).items()}
        volume_ratio_20d = CalculatedField.from_dict(data["volume_ratio_20d"]) if data.get("volume_ratio_20d") else None
        atr_14 = CalculatedField.from_dict(data["atr_14"]) if data.get("atr_14") else None
        benchmark_return = CalculatedField.from_dict(data["benchmark_return"]) if data.get("benchmark_return") else None
        fundamentals = dict(data["fundamentals"]) if data.get("fundamentals") is not None else None
        addv_20d = CalculatedField.from_dict(data["addv_20d"]) if data.get("addv_20d") else None
        cap_tier = str(data.get("cap_tier", "unknown"))
        return cls(
            ticker=str(data["ticker"]),
            period=str(data.get("period", "6mo")),
            quote=quote,
            returns=returns,
            volume_ratio_20d=volume_ratio_20d,
            sma_50_status=str(data["sma_50_status"]),
            sma_200_status=str(data["sma_200_status"]),
            atr_14=atr_14,
            benchmark_return=benchmark_return,
            fundamentals=fundamentals,
            provider=str(data["provider"]),
            as_of=str(data["as_of"]),
            addv_20d=addv_20d,
            cap_tier=cap_tier,
        )


class MarketDataError(Exception):
    """Structured recoverable error for market providers."""

    def __init__(self, provider: str, message: str, recoverable: bool = True) -> None:
        super().__init__(f"[{provider}] {message} (recoverable={recoverable})")
        self.provider = provider
        self.message = message
        self.recoverable = recoverable


@dataclass(frozen=True)
class CompanyMultipleSnapshot:
    """One company's valuation multiples snapshot."""

    ticker: str
    company_name: str | None
    market_cap: float | None
    trailing_pe: float | None
    forward_pe: float | None
    ev_to_ebitda: float | None
    ev_to_sales: float | None
    price_to_book: float | None
    fcf_yield: float | None
    operating_margin: float | None
    revenue_growth: float | None
    as_of: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "market_cap": self.market_cap,
            "trailing_pe": self.trailing_pe,
            "forward_pe": self.forward_pe,
            "ev_to_ebitda": self.ev_to_ebitda,
            "ev_to_sales": self.ev_to_sales,
            "price_to_book": self.price_to_book,
            "fcf_yield": self.fcf_yield,
            "operating_margin": self.operating_margin,
            "revenue_growth": self.revenue_growth,
            "as_of": self.as_of,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CompanyMultipleSnapshot:
        return cls(
            ticker=str(data["ticker"]).upper(),
            company_name=str(data["company_name"]) if data.get("company_name") else None,
            market_cap=float(data["market_cap"]) if data.get("market_cap") is not None else None,
            trailing_pe=float(data["trailing_pe"]) if data.get("trailing_pe") is not None else None,
            forward_pe=float(data["forward_pe"]) if data.get("forward_pe") is not None else None,
            ev_to_ebitda=float(data["ev_to_ebitda"]) if data.get("ev_to_ebitda") is not None else None,
            ev_to_sales=float(data["ev_to_sales"]) if data.get("ev_to_sales") is not None else None,
            price_to_book=float(data["price_to_book"]) if data.get("price_to_book") is not None else None,
            fcf_yield=float(data["fcf_yield"]) if data.get("fcf_yield") is not None else None,
            operating_margin=float(data["operating_margin"]) if data.get("operating_margin") is not None else None,
            revenue_growth=float(data["revenue_growth"]) if data.get("revenue_growth") is not None else None,
            as_of=str(data.get("as_of", "")),
        )


@dataclass(frozen=True)
class MultiplePercentileStat:
    """Historical distribution and percentile ranking for one valuation multiple."""

    metric_name: str
    current_value: float | None
    min_value: float | None
    max_value: float | None
    median_value: float | None
    percentile: float | None
    z_score: float | None
    lookback_periods: int
    regime: str  # 'discount', 'fair', 'premium', 'insufficient_history'
    status: str  # 'ok', 'unavailable'

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "current_value": self.current_value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "median_value": self.median_value,
            "percentile": self.percentile,
            "z_score": self.z_score,
            "lookback_periods": self.lookback_periods,
            "regime": self.regime,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MultiplePercentileStat:
        return cls(
            metric_name=str(data["metric_name"]),
            current_value=float(data["current_value"]) if data.get("current_value") is not None else None,
            min_value=float(data["min_value"]) if data.get("min_value") is not None else None,
            max_value=float(data["max_value"]) if data.get("max_value") is not None else None,
            median_value=float(data["median_value"]) if data.get("median_value") is not None else None,
            percentile=float(data["percentile"]) if data.get("percentile") is not None else None,
            z_score=float(data["z_score"]) if data.get("z_score") is not None else None,
            lookback_periods=int(data.get("lookback_periods", 0)),
            regime=str(data.get("regime", "insufficient_history")),
            status=str(data.get("status", "unavailable")),
        )


@dataclass(frozen=True)
class PeerCompsResult:
    """Peer comparison matrix, rankings, and historical multiple distribution."""

    target_ticker: str
    peer_tickers: tuple[str, ...]
    target_multiples: CompanyMultipleSnapshot
    peer_multiples: tuple[CompanyMultipleSnapshot, ...]
    peer_medians: dict[str, float | None]
    target_peer_ranks: dict[str, int | None]
    target_peer_percentiles: dict[str, float | None]
    target_median_spreads: dict[str, float | None]
    historical_percentiles: dict[str, MultiplePercentileStat]
    provider: str
    as_of: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_ticker": self.target_ticker,
            "peer_tickers": list(self.peer_tickers),
            "target_multiples": self.target_multiples.to_dict(),
            "peer_multiples": [m.to_dict() for m in self.peer_multiples],
            "peer_medians": dict(self.peer_medians),
            "target_peer_ranks": dict(self.target_peer_ranks),
            "target_peer_percentiles": dict(self.target_peer_percentiles),
            "target_median_spreads": dict(self.target_median_spreads),
            "historical_percentiles": {k: v.to_dict() for k, v in self.historical_percentiles.items()},
            "provider": self.provider,
            "as_of": self.as_of,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PeerCompsResult:
        return cls(
            target_ticker=str(data["target_ticker"]).upper(),
            peer_tickers=tuple(str(t).upper() for t in data.get("peer_tickers", ())),
            target_multiples=CompanyMultipleSnapshot.from_dict(data["target_multiples"]),
            peer_multiples=tuple(CompanyMultipleSnapshot.from_dict(m) for m in data.get("peer_multiples", ())),
            peer_medians=dict(data.get("peer_medians", {})),
            target_peer_ranks=dict(data.get("target_peer_ranks", {})),
            target_peer_percentiles=dict(data.get("target_peer_percentiles", {})),
            target_median_spreads=dict(data.get("target_median_spreads", {})),
            historical_percentiles={k: MultiplePercentileStat.from_dict(v) for k, v in data.get("historical_percentiles", {}).items()},
            provider=str(data.get("provider", "hybrid")),
            as_of=str(data.get("as_of", "")),
        )
