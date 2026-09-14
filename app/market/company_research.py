"""Wall Street consensus benchmark tool: get_company_research.

Black-box dependency: ranaroussi/yfinance public API behind testable seams
(`Ticker.analyst_price_targets`, `Ticker.recommendations`, `Ticker.earnings_estimate`,
`Ticker.revenue_estimate`, `Ticker.calendar`). No donor code copied. Output is
secondary research data for the expectation-gap comparison, never a recommendation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from app.market.schemas import MarketDataError
from app.market.providers.finnhub import FinnhubClient

logger = logging.getLogger(__name__)

PROVIDER_NAME = "yfinance"


@dataclass(frozen=True)
class ConsensusValue:
    """One consensus number with provenance and availability."""

    value: float | None
    status: str
    provider: str
    as_of: str

    def __post_init__(self) -> None:
        if self.status not in ("ok", "unavailable"):
            raise ValueError("status must be ok or unavailable")
        if self.status == "ok" and self.value is None:
            raise ValueError("value must be present when status is ok")

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-safe dict."""
        return {"value": self.value, "status": self.status, "provider": self.provider, "as_of": self.as_of}

    @classmethod
    def from_dict(cls, data: MappingLike) -> ConsensusValue:
        """Rebuild from dict, re-validating."""
        return cls(
            value=float(data["value"]) if data.get("value") is not None else None,
            status=str(data["status"]),
            provider=str(data["provider"]),
            as_of=str(data["as_of"]),
        )


class MappingLike(dict):
    """dict alias allowing .get() in from_dict helpers."""


def _value_or_unavailable(raw: Any, provider: str, as_of: str) -> ConsensusValue | None:
    """Wrap a raw number into ConsensusValue; None when input missing."""
    if raw is None:
        return None
    try:
        return ConsensusValue(value=float(raw), status="ok", provider=provider, as_of=as_of)
    except (TypeError, ValueError):
        return ConsensusValue(value=None, status="unavailable", provider=provider, as_of=as_of)


@dataclass(frozen=True)
class PriceTargets:
    """Analyst price-target range."""

    low: ConsensusValue | None
    mean: ConsensusValue | None
    high: ConsensusValue | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-safe dict."""
        return {
            "low": self.low.to_dict() if self.low else None,
            "mean": self.mean.to_dict() if self.mean else None,
            "high": self.high.to_dict() if self.high else None,
        }

    @classmethod
    def from_dict(cls, data: MappingLike) -> PriceTargets:
        """Rebuild from dict, re-validating."""
        def _cv(key: str) -> ConsensusValue | None:
            raw = data.get(key)
            return ConsensusValue.from_dict(raw) if raw else None
        return cls(low=_cv("low"), mean=_cv("mean"), high=_cv("high"))


@dataclass(frozen=True)
class RatingsSnapshot:
    """Consensus buy/hold/sell counts."""

    buy: int | None
    hold: int | None
    sell: int | None
    strong_buy: int | None
    strong_sell: int | None
    total: int | None
    status: str
    provider: str
    as_of: str

    def __post_init__(self) -> None:
        for name in ("buy", "hold", "sell", "strong_buy", "strong_sell", "total"):
            v = getattr(self, name)
            if v is not None and v < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.status not in ("ok", "unavailable"):
            raise ValueError("status must be ok or unavailable")

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-safe dict."""
        return {
            "buy": self.buy, "hold": self.hold, "sell": self.sell,
            "strong_buy": self.strong_buy, "strong_sell": self.strong_sell,
            "total": self.total, "status": self.status,
            "provider": self.provider, "as_of": self.as_of,
        }

    @classmethod
    def from_dict(cls, data: MappingLike) -> RatingsSnapshot:
        """Rebuild from dict, re-validating."""
        return cls(
            buy=int(data["buy"]) if data.get("buy") is not None else None,
            hold=int(data["hold"]) if data.get("hold") is not None else None,
            sell=int(data["sell"]) if data.get("sell") is not None else None,
            strong_buy=int(data["strong_buy"]) if data.get("strong_buy") is not None else None,
            strong_sell=int(data["strong_sell"]) if data.get("strong_sell") is not None else None,
            total=int(data["total"]) if data.get("total") is not None else None,
            status=str(data["status"]),
            provider=str(data["provider"]),
            as_of=str(data["as_of"]),
        )


@dataclass(frozen=True)
class EstimateRow:
    """One forward-period consensus estimate."""

    metric: Literal["eps", "revenue"]
    period: str
    avg: float | None
    low: float | None
    high: float | None
    growth: float | None
    n_analysts: int | None
    provider: str
    as_of: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-safe dict."""
        return {
            "metric": self.metric, "period": self.period,
            "avg": self.avg, "low": self.low, "high": self.high,
            "growth": self.growth, "n_analysts": self.n_analysts,
            "provider": self.provider, "as_of": self.as_of,
        }

    @classmethod
    def from_dict(cls, data: MappingLike) -> EstimateRow:
        """Rebuild from dict, re-validating."""
        return cls(
            metric=str(data["metric"]),
            period=str(data["period"]),
            avg=float(data["avg"]) if data.get("avg") is not None else None,
            low=float(data["low"]) if data.get("low") is not None else None,
            high=float(data["high"]) if data.get("high") is not None else None,
            growth=float(data["growth"]) if data.get("growth") is not None else None,
            n_analysts=int(data["n_analysts"]) if data.get("n_analysts") is not None else None,
            provider=str(data["provider"]),
            as_of=str(data["as_of"]),
        )


@dataclass(frozen=True)
class CompanyResearchResult:
    """Normalized Wall Street consensus snapshot for one ticker."""

    ticker: str
    price_targets: PriceTargets | None
    ratings: RatingsSnapshot | None
    eps_estimates: tuple[EstimateRow, ...]
    revenue_estimates: tuple[EstimateRow, ...]
    next_earnings_date: str | None
    provider: str
    as_of: str

    def __post_init__(self) -> None:
        if not self.ticker or self.ticker != self.ticker.upper():
            raise ValueError("ticker must be non-empty uppercase")
        if self.metric_seen(self.eps_estimates, "eps") or self.metric_seen(self.revenue_estimates, "revenue"):
            raise ValueError("estimate rows must match their metric grouping")

    @staticmethod
    def metric_seen(rows: tuple[EstimateRow, ...], metric: str) -> bool:
        """Return True when a row carries the wrong metric label."""
        return any(row.metric != metric for row in rows)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-safe dict."""
        return {
            "ticker": self.ticker,
            "price_targets": self.price_targets.to_dict() if self.price_targets else None,
            "ratings": self.ratings.to_dict() if self.ratings else None,
            "eps_estimates": [r.to_dict() for r in self.eps_estimates],
            "revenue_estimates": [r.to_dict() for r in self.revenue_estimates],
            "next_earnings_date": self.next_earnings_date,
            "provider": self.provider,
            "as_of": self.as_of,
        }

    @classmethod
    def from_dict(cls, data: MappingLike) -> CompanyResearchResult:
        """Rebuild from dict, re-validating."""
        price_targets = PriceTargets.from_dict(data["price_targets"]) if data.get("price_targets") else None
        ratings = RatingsSnapshot.from_dict(data["ratings"]) if data.get("ratings") else None
        eps = tuple(EstimateRow.from_dict(r) for r in data.get("eps_estimates", []))
        rev = tuple(EstimateRow.from_dict(r) for r in data.get("revenue_estimates", []))
        return cls(
            ticker=str(data["ticker"]),
            price_targets=price_targets,
            ratings=ratings,
            eps_estimates=eps,
            revenue_estimates=rev,
            next_earnings_date=str(data["next_earnings_date"]) if data.get("next_earnings_date") else None,
            provider=str(data["provider"]),
            as_of=str(data["as_of"]),
        )


def _validate_ticker(ticker: str) -> str:
    """Normalize and validate a caller-supplied ticker."""
    clean = (ticker or "").strip().upper()
    if not clean or not clean.replace(".", "").replace("-", "").replace("^", "").isalnum():
        raise ValueError(f"invalid ticker: {ticker!r}")
    return clean


def _yf_price_targets(ticker: str) -> dict:
    """Seam over yfinance analyst_price_targets so tests can patch it."""
    import yfinance as yf

    return dict(getattr(yf.Ticker(ticker), "analyst_price_targets", None) or {})


def _yf_recommendations(ticker: str):
    """Seam over yfinance recommendations so tests can patch it."""
    import yfinance as yf

    frame = getattr(yf.Ticker(ticker), "recommendations", None)
    if frame is None or len(frame) == 0:
        return None
    return frame.iloc[0].to_dict()


def _yf_estimates(ticker: str, metric: str):
    """Seam over yfinance earnings/revenue estimates so tests can patch it."""
    import yfinance as yf

    t = yf.Ticker(ticker)
    frame = t.earnings_estimate if metric == "eps" else t.revenue_estimate
    if frame is None or len(frame) == 0:
        return {}
    return {str(idx): row.to_dict() for idx, row in frame.iterrows()}


def _yf_calendar(ticker: str) -> dict:
    """Seam over yfinance calendar so tests can patch it."""
    import yfinance as yf

    raw = getattr(yf.Ticker(ticker), "calendar", None)
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    return {}


def _map_price_targets(raw: dict, as_of: str) -> PriceTargets | None:
    """Map raw price-target dict; None when no coverage."""
    if not raw:
        return None
    return PriceTargets(
        low=_value_or_unavailable(raw.get("low"), PROVIDER_NAME, as_of),
        mean=_value_or_unavailable(raw.get("mean"), PROVIDER_NAME, as_of),
        high=_value_or_unavailable(raw.get("high"), PROVIDER_NAME, as_of),
    )


def _map_ratings(raw: dict | None, as_of: str) -> RatingsSnapshot | None:
    """Map first-row recommendation counts; None when no coverage."""
    if not raw:
        return None
    counts = {k: raw.get(k) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")}
    numeric = {k: int(v) for k, v in counts.items() if isinstance(v, (int, float))}
    if not numeric:
        return None
    total = sum(numeric.values())
    return RatingsSnapshot(
        buy=numeric.get("buy"),
        hold=numeric.get("hold"),
        sell=numeric.get("sell"),
        strong_buy=numeric.get("strongBuy"),
        strong_sell=numeric.get("strongSell"),
        total=total,
        status="ok",
        provider=PROVIDER_NAME,
        as_of=as_of,
    )


def _map_estimates(raw: dict, metric: str, as_of: str) -> tuple[EstimateRow, ...]:
    """Map estimate frame rows into EstimateRow tuples."""
    rows: list[EstimateRow] = []
    for period, values in raw.items():
        if not isinstance(values, dict):
            continue
        n_analysts = values.get("numberOfAnalysts") or values.get("numberOfAnalystsEps") or values.get("numberOfAnalystsRevenue")
        rows.append(
            EstimateRow(
                metric=metric,
                period=str(period),
                avg=_num(values.get("avg")),
                low=_num(values.get("low")),
                high=_num(values.get("high")),
                growth=_num(values.get("growth")),
                n_analysts=int(n_analysts) if isinstance(n_analysts, (int, float)) else None,
                provider=PROVIDER_NAME,
                as_of=as_of,
            )
        )
    return tuple(rows)


def _num(raw: Any) -> float | None:
    """Coerce a raw number to float or None."""
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _map_calendar(raw: dict) -> str | None:
    """Extract first parseable earnings date string."""
    dates = raw.get("Earnings Date") or []
    if isinstance(dates, str):
        dates = [dates]
    for entry in dates:
        if entry:
            return str(entry)
    return None


def get_company_research(ticker: str) -> CompanyResearchResult:
    """Fetch Wall Street consensus data for the expectation-gap benchmark.

    :param ticker: Uppercase ticker symbol.
    :returns: CompanyResearchResult; sections with no institutional coverage
              are None/empty — never zeros or fabricated values.
    :raises ValueError: On invalid ticker.
    """
    clean_ticker = _validate_ticker(ticker)
    as_of = datetime.now(timezone.utc).isoformat()

    price_targets: PriceTargets | None = None
    ratings: RatingsSnapshot | None = None
    eps_estimates: tuple[EstimateRow, ...] = ()
    revenue_estimates: tuple[EstimateRow, ...] = ()
    next_earnings_date: str | None = None

    try:
        price_targets = _map_price_targets(_yf_price_targets(clean_ticker), as_of)
    except Exception as exc:
        logger.warning("price targets unavailable for %s: %s", clean_ticker, exc)

    try:
        ratings = _map_ratings(_yf_recommendations(clean_ticker), as_of)
    except Exception as exc:
        logger.warning("ratings unavailable for %s: %s", clean_ticker, exc)

    for metric, mapper, target in (
        ("eps", _yf_estimates, "eps"),
        ("revenue", _yf_estimates, "revenue"),
    ):
        try:
            rows = _map_estimates(mapper(clean_ticker, metric), metric, as_of)
            if metric == "eps":
                eps_estimates = rows
            else:
                revenue_estimates = rows
        except Exception as exc:
            logger.warning("%s estimates unavailable for %s: %s", metric, clean_ticker, exc)

    try:
        next_earnings_date = _map_calendar(_yf_calendar(clean_ticker))
    except Exception as exc:
        logger.warning("calendar unavailable for %s: %s", clean_ticker, exc)

    # Finnhub fallback (optional keyed provider): fill only sections yfinance
    # could not, preserving keyless behavior when FINNHUB_API_KEY is absent.
    if price_targets is None or ratings is None:
        try:
            fh = FinnhubClient()
            if fh.is_configured:
                if price_targets is None:
                    fh_target = fh.get_price_target(clean_ticker) or {}
                    price_targets = PriceTargets(
                        low=_value_or_unavailable(fh_target.get("targetLow"), "finnhub", as_of),
                        mean=_value_or_unavailable(fh_target.get("targetMean"), "finnhub", as_of),
                        high=_value_or_unavailable(fh_target.get("targetHigh"), "finnhub", as_of),
                    )
                if ratings is None:
                    trends = fh.get_recommendation_trends(clean_ticker)
                    if trends:
                        newest = trends[0]
                        counts = {
                            k: newest.get(k)
                            for k in ("strongBuy", "buy", "hold", "sell", "strongSell")
                        }
                        numeric = {k: int(v) for k, v in counts.items() if isinstance(v, (int, float))}
                        if numeric:
                            ratings = RatingsSnapshot(
                                buy=numeric.get("buy"),
                                hold=numeric.get("hold"),
                                sell=numeric.get("sell"),
                                strong_buy=numeric.get("strongBuy"),
                                strong_sell=numeric.get("strongSell"),
                                total=sum(numeric.values()),
                                status="ok",
                                provider="finnhub",
                                as_of=as_of,
                            )
        except MarketDataError as exc:
            logger.warning("finnhub fallback unavailable for %s: %s", clean_ticker, exc)

    return CompanyResearchResult(
        ticker=clean_ticker,
        price_targets=price_targets,
        ratings=ratings,
        eps_estimates=eps_estimates,
        revenue_estimates=revenue_estimates,
        next_earnings_date=next_earnings_date,
        provider=PROVIDER_NAME,
        as_of=as_of,
    )
