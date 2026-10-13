"""
Backtesting utility for the Commodity Price Prediction service.

Usage example:
    python scripts/backtest.py --commodity steel_hrc --start 2023-01-01 --end 2024-01-01 --max-samples 30

This script reuses the feature engineering and forecasting logic from app.main
to run a rolling-origin backtest and report MAE / RMSE / MAPE and confidence
interval coverage for the selected commodity and horizons.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Ensure the project root is on the Python path so `app` can be imported.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.main import (  # type: ignore  # pylint: disable=import-error
    COMMODITY_TICKERS,
    GPR_CSV_PATH,
    HORIZONS,
    LOCATIONS,
    MIN_TRAIN,
    fetch_fred_inflation,
    fetch_multi_weather,
    fetch_yfinance,
    forecast,
    load_gpr,
)


@dataclass
class BacktestConfig:
    commodity: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    horizons: List[int]
    stride: int
    max_samples: Optional[int]


def parse_args() -> BacktestConfig:
    parser = argparse.ArgumentParser(description="Run rolling backtests for commodity forecasts.")
    parser.add_argument("--commodity", required=True, choices=COMMODITY_TICKERS.keys())
    parser.add_argument("--start", type=lambda s: datetime.fromisoformat(s), help="Backtest start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=lambda s: datetime.fromisoformat(s), help="Backtest end date (YYYY-MM-DD)")
    parser.add_argument("--horizons", type=int, nargs="+", default=HORIZONS, help="Forecast horizons to evaluate")
    parser.add_argument("--stride", type=int, default=5, help="Days between evaluation cutoffs (default=5)")
    parser.add_argument("--max-samples", type=int, help="Limit the number of evaluation cutoffs")
    args = parser.parse_args()

    return BacktestConfig(
        commodity=args.commodity,
        start_date=args.start,
        end_date=args.end,
        horizons=sorted(set(args.horizons)),
        stride=max(1, args.stride),
        max_samples=args.max_samples,
    )


def build_exogenous_frame(series_index: pd.DatetimeIndex, commodity: str) -> pd.DataFrame:
    """Construct exogenous dataframe aligned to the provided price index."""
    if series_index.empty:
        return pd.DataFrame()

    start_date = series_index.min().date()
    end_date = series_index.max().date()

    df_infl = fetch_fred_inflation(start_date, end_date)
    df_gpr = load_gpr(GPR_CSV_PATH, start_date, end_date)

    exog = pd.DataFrame(index=series_index)
    if not df_infl.empty:
        exog = exog.join(df_infl.reindex(series_index).ffill().bfill(), how="left")
    if not df_gpr.empty:
        exog = exog.join(df_gpr.reindex(series_index).ffill().bfill(), how="left")

    locs = LOCATIONS.get(commodity, [])
    if locs:
        weather_df = fetch_multi_weather(
            locs,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        )
        if not weather_df.empty:
            exog = exog.join(weather_df.reindex(series_index).ffill().bfill(), how="left")

    # If every column is NaN, return empty so the forecasting code skips exogenous vars.
    if exog.isna().all(axis=None):
        return pd.DataFrame()
    return exog


def generate_cutoffs(series: pd.Series, horizons: List[int], stride: int) -> pd.DatetimeIndex:
    """Return the list of cutoff dates that have enough history and future data for all horizons."""
    if series.empty:
        return pd.DatetimeIndex([])

    max_h = max(horizons)
    valid_range = series.index[MIN_TRAIN : len(series) - max_h]
    cutoffs = valid_range[::stride]
    return cutoffs


def run_backtest(cfg: BacktestConfig) -> Tuple[pd.DataFrame, pd.DataFrame]:
    ticker = COMMODITY_TICKERS[cfg.commodity]
    price_start = cfg.start_date.date() if cfg.start_date else None
    price_end = cfg.end_date.date() if cfg.end_date else datetime.utcnow().date()

    price_df = fetch_yfinance(ticker, price_start, price_end)
    if price_df.empty or "close" not in price_df:
        raise RuntimeError(f"No price data available for ticker {ticker}")

    series = price_df["close"].astype(float).dropna()
    if len(series) < MIN_TRAIN + max(cfg.horizons):
        raise RuntimeError("Not enough rows to run backtest with the requested horizons.")

    exog = build_exogenous_frame(series.index, cfg.commodity)
    cutoffs = generate_cutoffs(series, cfg.horizons, cfg.stride)

    if cfg.max_samples:
        cutoffs = cutoffs[: cfg.max_samples]

    records: List[Dict] = []

    for cutoff in cutoffs:
        window_series = series.loc[:cutoff]
        if len(window_series) < MIN_TRAIN:
            continue
        window_exog = exog.loc[:cutoff] if not exog.empty else pd.DataFrame()
        fc = forecast(window_series, window_exog, cfg.horizons)

        for _, row in fc.iterrows():
            horizon = int(row["horizon"])
            target_date = cutoff + pd.Timedelta(days=horizon)
            if target_date not in series.index:
                continue

            pred = row.get("forecast_price", np.nan)
            actual = float(series.loc[target_date])
            if pd.isna(pred):
                continue

            low_80 = row.get("low_80", np.nan)
            high_80 = row.get("high_80", np.nan)
            low_95 = row.get("low_95", np.nan)
            high_95 = row.get("high_95", np.nan)

            records.append(
                {
                    "commodity": cfg.commodity,
                    "cutoff_date": cutoff,
                    "target_date": target_date,
                    "horizon": horizon,
                    "prediction": float(pred),
                    "actual": actual,
                    "error": float(pred) - actual,
                    "abs_error": abs(float(pred) - actual),
                    "pct_error": abs(float(pred) - actual) / actual * 100 if actual != 0 else math.nan,
                    "low_80": low_80,
                    "high_80": high_80,
                    "low_95": low_95,
                    "high_95": high_95,
                    "covered_80": float(low_80 <= actual <= high_80) if not any(pd.isna([low_80, high_80])) else math.nan,
                    "covered_95": float(low_95 <= actual <= high_95) if not any(pd.isna([low_95, high_95])) else math.nan,
                }
            )

    if not records:
        raise RuntimeError("Backtest produced no samples. Try expanding the date range or reducing horizons.")

    detail_df = pd.DataFrame(records)
    summary_df = (
        detail_df.groupby("horizon")
        .agg(
            samples=("prediction", "count"),
            mae=("abs_error", "mean"),
            rmse=("error", lambda s: math.sqrt(np.mean(np.square(s)))),
            mape=("pct_error", "mean"),
            coverage_80=("covered_80", "mean"),
            coverage_95=("covered_95", "mean"),
        )
        .round({"mae": 4, "rmse": 4, "mape": 2, "coverage_80": 3, "coverage_95": 3})
        .reset_index()
    )
    return detail_df, summary_df


def main():
    cfg = parse_args()
    detail_df, summary_df = run_backtest(cfg)

    print("\nBacktest summary metrics (by horizon):\n")
    print(summary_df.to_string(index=False))
    print("\nSample rows:\n")
    print(detail_df.head().to_string(index=False))

    output_dir = REPO_ROOT / "backtest_outputs"
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    detail_path = output_dir / f"{cfg.commodity}_detail_{timestamp}.csv"
    summary_path = output_dir / f"{cfg.commodity}_summary_{timestamp}.json"

    detail_df.to_csv(detail_path, index=False)
    summary_path.write_text(summary_df.to_json(orient="records", indent=2))

    manifest = {
        "commodity": cfg.commodity,
        "start": detail_df["cutoff_date"].min().isoformat(),
        "end": detail_df["cutoff_date"].max().isoformat(),
        "samples": int(len(detail_df)),
        "detail_csv": str(detail_path),
        "summary_json": str(summary_path),
    }
    manifest_path = output_dir / f"{cfg.commodity}_manifest_{timestamp}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    print(f"\nDetailed rows saved to {detail_path}")
    print(f"Summary metrics saved to {summary_path}")
    print(f"Run manifest saved to {manifest_path}")


if __name__ == "__main__":
    main()

