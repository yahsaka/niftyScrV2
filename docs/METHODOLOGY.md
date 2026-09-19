# Model and accounting methodology

This describes the code's research assumptions. It is not a claim of predictive performance or a guide to statutory brokerage/tax calculation.

## Universe and daily market data

`data/nifty500_tickers.csv` is the **same bundled stock list supplied in the original project**. Its historical name does not certify that its membership matches today's index. `EQUITY_L.csv` supplies additional exact identities. Symbols are canonical bare NSE symbols internally; provider suffixes are applied only at the provider boundary. Company/ISIN matching is explicit; unknown text is not converted to a guessed ticker.

The downloader uses Yahoo through yfinance with `auto_adjust=False`, `back_adjust=False`, `actions=True`, `repair=False`, daily interval, explicit timeouts and bounded retries. It requests three years, validates completed daily OHLC, warms indicators, and retains up to 520 sessions in one compressed snapshot. Indicators, scanner results, chart views, portfolio marks and simulated execution share that snapshot. The benchmark is `^NSEI`.

Provider OHLC is not a certified unadjusted, point-in-time tape. Historical Yahoo prices can already reflect splits. The yfinance API exposes adjustment/action/repair choices; the code makes its choices explicit rather than relying on defaults.[1] No paid feed, exchange holiday service or historical index-membership service is introduced.

## Indicator definitions and unchanged rules

Stock EMA uses an initial-window SMA seed followed by exponential weighting (`adjust=False`). RSI and ATR use explicitly implemented Wilder/RMA-style exponentially weighted calculations with alpha `1 / length`, minimum warm-up length and `adjust=True`; a flat RSI is defined as 50. MACD is the 12/26 seeded-EMA difference with a 9-session signal EMA. Indicator calculations use the provider `Adj Close / Close` ratio applied consistently to OHLC. ATR is also converted to provider-price units as `ATR_PRICE` for execution.

The original environment left technical-analysis dependencies unpinned and could select optional backends. These definitions fix that ambiguity. They are not a promise of bit-for-bit equivalence with every old pandas-ta/TA-Lib environment. Thresholds and six intended conditions are preserved:

| Condition | Awarded when |
|---|---|
| Above 200 EMA | Analysis close is strictly above its 200 EMA. |
| Fresh 200 EMA breakout | Previous analysis close was at/below its 200 EMA and the current close is above. |
| Above 50 EMA | Analysis close is strictly above its 50 EMA. |
| RSI zone | RSI is strictly above 60 and at/below 70. |
| Volume confirmation | Current volume strictly exceeds **2×** the 20-session mean, including the current session. |
| MACD crossover | Previous MACD was at/below signal and current MACD is above signal. |

A separate eligibility filter excludes a price more than the configured maximum above the 50 EMA (default 15%), before scoring. Watchlist threshold defaults to 3 and Qualified to 5 of 6. Breakout and above-EMA conditions overlap; they are not independent evidence. The application does not call this score a probability.

The benchmark regime retains the original 200-span `adjust=False` EWM convention, with a sufficient-history guard. Three valid closes below the index EMA classify Bearish; otherwise Bullish. Missing/insufficient index history is Unknown. Bearish/Unknown suspend long setup classification; they are not market forecasts.

## Freshness and next-open timing

IST weekdays before 16:15 expect the preceding weekday's completed bar. After that cutoff the current weekday is expected. Future/incomplete bars are rejected. This is a **conservative weekday heuristic, not an official exchange-holiday calendar**. Holidays, special sessions or late provider publication can produce a stale warning and block entries. No stale result silently becomes fresh.

A manual paper order can be staged after a completed signal exists and before the next expected weekday's 09:15 opening. The execution engine independently checks the actual next observed session's opening against the order's timezone-aware request timestamp. A late request is cancelled rather than retrospectively filled. Backtests explicitly use a historical EOD request timestamp.

The CLI/workflow can publish a stale-date observation when the provider has no newer completed day; the UI date/freshness warning remains authoritative. The pipeline refuses a benchmark date rollback. Stock refresh failures, missing/stale dates and insufficient warm-up are excluded from current screening and included in coverage warnings.

## Shared execution engine

`src/execution.py` is the only implementation of fills used by paper simulation and historical event studies. Orders progress from PENDING to OPEN and then CLOSED; cancellations and data reviews have explicit statuses. No record is treated as a broker order or confirmation.

Default assumptions are: 20-session maximum hold, stop distance 2× signal ATR, 5 bps entry slippage, 5 bps exit slippage, and 20 bps modeled round-trip fee. Half the configured fee is applied to each side's **actual filled notional**, not subtracted twice from price and P&L. This fixes the old reporting convention and changes net results where the old convention was inconsistent.

At next-session open:

```text
entry = observed_open × (1 + entry_slippage)
stop = entry − ATR_multiplier × signal_ATR_in_execution_price_units
cash_per_share = entry × (1 + one_side_fee_rate)
modeled_stop_proceeds = stop × (1 − exit_slippage) × (1 − one_side_fee_rate)
risk_per_share = cash_per_share − modeled_stop_proceeds
quantity = floor(min(allocation / cash_per_share,
                     allocation × risk_percent / 100 / risk_per_share))
```

Negative/non-finite inputs, non-positive stops, no capacity for one share and excessive allocations are rejected/cancelled. Pending orders reserve their **full allocation**. There is no leverage or shorting, and at most one active/review-required position per ticker. A ticker/signal-session pair cannot be staged twice, even after cancellation or closure.

The entry session counts as session one and is checked for a stop. A low at/below the stop triggers exit; an opening gap at/below the stop uses the weaker opening price. Otherwise the modeled stop level is used. Exit slippage and fee are then applied. Stops take priority over a time exit on the same session; a time exit uses that session's close. These daily bars do not determine intraday liquidity, partial fills, price limits or fill feasibility. **Planned stop risk is not a guaranteed maximum loss.**

Processing advances chronologically through one account and stores the last processed session. Repeating identical data does not increment holding periods again. Missing required benchmark sessions while an order is active pause the whole update atomically. Missing data after it has already closed does not manufacture a continuing exposure or block that closed trade.

## Dividends, splits and revised data

A positive provider dividend observation is credited once on the ex-date only to a position held from an earlier session. Actual payment delays, withholding, taxes and reinvestment are not modeled. New ex-date buyers are not credited in this approximation.

A split on the prospective entry session cancels the entry. A split affecting an open position marks it REVIEW_REQUIRED, retains the original records, and removes confidence in its current equity valuation. A changed fingerprint for the **last processed** OHLC/action bar also triggers review. This is a targeted revision guard, **not an immutable audit of every earlier provider observation**.

Automatic share-unit reconciliation is not implemented. The owner can export and preserve the account, then archive it and start a separate corrected-engine account. Restarting is not a repair or validation of the affected history.

## Account performance versus event-study returns

The paper account keeps cash, reservations, filled quantities, entry/exit fees and dividend events. Closed P&L reconciles to its cash flows. Daily equity is cash plus currently marked open positions. Missing or review-required marks make the account equity **unvalued**, not “zero exposure.” Unrealized P&L uses entry basis and current marks, before possible future exit costs. The account chart does not sum trade percentages.

The Backtest screen is a **per-ticker event study**, not a pooled portfolio backtest. Each sample uses an independent ₹100,000 allocation and 2% modeled risk, with no same-ticker overlapping positions. Samples on different tickers may overlap and reuse hypothetical capital. The descriptive outputs are completed-trade counts, positive-return share, mean/median net trade returns, return distributions and a return-based profit factor. No loss denominator produces an undefined profit factor, not infinity.

Its benchmark comparison uses the index's matching next-open to exit-close windows, without benchmark fees or dividend reinvestment. The 70/30 chronological split is descriptive, not optimized walk-forward validation. Fee sensitivity holds slippage fixed and compares zero, baseline and double modeled fees. Incomplete trades, unsized entries, data errors and corporate-action cases are reported rather than filled with zero returns.

Using the bundled constituent list retrospectively introduces survivorship/selection bias. Signal thresholds are not claimed to be optimized. Daily execution approximations, provider revisions and the finite saved window limit conclusions.

## Portfolio assessment

Imported cost is quantity × average price. A holding's current value/P&L is shown only with a usable mark at the displayed snapshot date. Aggregate matched P&L compares priced holdings with **the cost of those same holdings**, not all portfolio cost against a partially priced value. Price and trend coverage are cost-weighted and separate. Industry concentration uses invested cost. Being above a 200 EMA is a trend observation, not a complete assessment of suitability, diversification or downside risk.

## References

[1] [Official yfinance download API](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html) and [upstream project](https://github.com/ranaroussi/yfinance). All implementation-specific statements above can be inspected in `src/` and the regression tests; no claim of verified current market performance is made.
