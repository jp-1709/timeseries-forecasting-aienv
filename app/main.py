# forecasting.py
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import List, Optional
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from fredapi import Fred
from xgboost import XGBRegressor
from sqlalchemy import create_engine, text
import requests
import yfinance as yf
import os
import logging
import threading
from apscheduler.schedulers.background import BackgroundScheduler
 
# ---------------- CONFIG ----------------
DB_URI = "postgresql+psycopg2://postgres:Admin123@10.0.0.4:5432/price_db"
FRED_API_KEY = "eef937e67eb512ee84fb8e3bee979ed3"
FRED_SERIES_ID = "T10YIE"
GPR_CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gpr.csv")
GPR_DATASET_URL = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
 
COMMODITY_TICKERS = {
    "gold": "GC=F",
    "silver": "SI=F",
    "copper": "HG=F",
    "crudeoil_wti": "CL=F",
    "naturalgas": "NGZ25.NYM",
    "steel_hrc": "HRC=F"
}
 
LOCATIONS = {
    "gold": [{"country": "China", "lat": 35.0, "lon": 105.0},
             {"country": "Australia", "lat": -24.0, "lon": 133.0},
             {"country": "Russia", "lat": 61.5, "lon": 105.3},
             {"country": "South Africa", "lat": -29.0, "lon": 24.0}],
    "silver": [{"country": "Mexico", "lat": 23.6, "lon": -102.5},
               {"country": "Peru", "lat": -9.2, "lon": -75.0},
               {"country": "China", "lat": 35.0, "lon": 105.0}],
    "copper": [{"country": "Chile", "lat": -33.4, "lon": -70.7},
               {"country": "Peru", "lat": -9.2, "lon": -75.0}],
    "crudeoil_wti": [{"country": "US Gulf Coast", "lat": 29.7, "lon": -95.3},
                     {"country": "Saudi Arabia", "lat": 24.7, "lon": 46.7},
                     {"country": "Russia", "lat": 61.0, "lon": 60.0}],
    "naturalgas": [{"country": "US Northeast", "lat": 40.7, "lon": -74.0},
                   {"country": "Germany", "lat": 51.2, "lon": 10.5},
                   {"country": "UK", "lat": 55.0, "lon": -3.0},
                   {"country": "Russia", "lat": 61.5, "lon": 105.3}],
    "steel_hrc": [{"country": "US", "lat": 38.0, "lon": -97.0},
                  {"country": "China", "lat": 35.0, "lon": 105.0},
                  {"country": "Germany", "lat": 51.0, "lon": 10.0}]
}
 
HORIZONS = [1, 7, 30, 60]
MIN_TRAIN = 150
MODEL_NAME = "XGBoost"
 
XGB_CFG = {
    1:  dict(n_estimators=100, max_depth=4, learning_rate=0.08, subsample=0.9, colsample_bytree=0.9,
             reg_lambda=1.0, n_jobs=-1, random_state=42),
    7:  dict(n_estimators=200, max_depth=5, learning_rate=0.06, subsample=0.9, colsample_bytree=0.9,
             reg_lambda=1.0, n_jobs=-1, random_state=42),
    30: dict(n_estimators=300, max_depth=6, learning_rate=0.04, subsample=0.9, colsample_bytree=0.9,
             reg_lambda=2.0, n_jobs=-1, random_state=42),
    60: dict(n_estimators=350, max_depth=7, learning_rate=0.03, subsample=0.85, colsample_bytree=0.85,
             reg_lambda=3.0, n_jobs=-1, random_state=42),
}
 
engine = create_engine(DB_URI, echo=False)

# ---------------- GPR SCHEDULER ----------------
def _gpr_background_update():
    """Download fresh GPR data in a background thread (called by scheduler and startup)."""
    logger.info("[GPR Scheduler] Starting GPR dataset refresh...")
    success = download_gpr_data(GPR_DATASET_URL, GPR_CSV_PATH)
    if success:
        logger.info("[GPR Scheduler] GPR dataset refreshed successfully.")
    else:
        logger.warning("[GPR Scheduler] GPR dataset refresh failed.")

_gpr_scheduler = BackgroundScheduler(daemon=True)
_gpr_scheduler.add_job(_gpr_background_update, 'interval', hours=24, id='gpr_daily')
_gpr_scheduler.start()

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("forecasting")
 
# ---------------- HELPERS ----------------
def ensure_datetime(obj):
    """Accept date/datetime/str and return pd.Timestamp"""
    if obj is None:
        return None
    return pd.to_datetime(obj)
 
def fetch_yfinance(ticker: str, start, end) -> pd.DataFrame:
    start = ensure_datetime(start)
    end = ensure_datetime(end)
   
    try:
        df = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                         end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                         interval="1d", progress=False, auto_adjust=False)
    except Exception as e:
        logger.warning(f"yfinance error for {ticker}: {e}")
        return pd.DataFrame()
   
    # Handle case where futures contract has insufficient data due to rollover
    if df is not None and not df.empty and len(df) < MIN_TRAIN:
        logger.warning(f"Insufficient data for {ticker} ({len(df)} rows), trying longer period...")
       
        # Try with max available period for this ticker
        try:
            df_max = yf.download(ticker, period="max", interval="1d", progress=False, auto_adjust=False)
            if df_max is not None and not df_max.empty:
                # Filter to requested date range or use all available data
                available_start = max(df_max.index.min(), start)
                df = df_max.loc[available_start:end] if available_start <= end else df_max
                logger.info(f"Retrieved {len(df)} rows using max period for {ticker}")
        except Exception as e2:
            logger.warning(f"Max period fallback failed for {ticker}: {e2}")
   
    if df is None or df.empty:
        return pd.DataFrame()
   
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns={"Close": "close", "Open": "open", "High": "high", "Low": "low", "Volume": "volume"})
    # ensure the columns exist; tolerantly select those available
    cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[cols].copy()
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    return df
 
def fetch_fred_inflation(start, end) -> pd.DataFrame:
    start = ensure_datetime(start)
    end = ensure_datetime(end)
    try:
        fred = Fred(api_key=FRED_API_KEY)
        s = fred.get_series(FRED_SERIES_ID,
                            observation_start=start.strftime("%Y-%m-%d"),
                            observation_end=end.strftime("%Y-%m-%d"))
    except Exception as e:
        logger.warning(f"FRED fetch failed: {e}")
        return pd.DataFrame()
    if s is None or len(s) == 0:
        return pd.DataFrame()
    df = s.rename("inflation").to_frame()
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    # resample daily and forward fill
    df = df.resample("D").ffill().bfill()
    return df
 
def download_gpr_data(url: str = GPR_DATASET_URL, output_path: str = GPR_CSV_PATH) -> bool:
    """
    Download GPR data from URL and save as CSV
   
    Args:
        url: URL to download the Excel file from
        output_path: Path to save the CSV file
   
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Downloading GPR data from {url}")
       
        # Download the Excel file
        response = requests.get(url, timeout=30)
        response.raise_for_status()
       
        # Read Excel file from memory using BytesIO
        from io import BytesIO
        df = pd.read_excel(BytesIO(response.content))
       
        # Basic validation
        if df.empty:
            logger.error("Downloaded GPR data is empty")
            return False
       
        # Check if required columns exist (flexible column names)
        date_col = None
        gpr_col = None

        for col in df.columns:
            col_lower = str(col).lower().strip()
            if date_col is None and 'date' in col_lower:
                date_col = col
            if gpr_col is None and 'gpr' in col_lower and 'date' not in col_lower:
                gpr_col = col

        # Fallback: use column position if name-based detection failed
        if date_col is None:
            date_col = df.columns[0]
            logger.warning(f"Date column not found by name, using first column: {date_col!r}")
        if gpr_col is None:
            for col in df.columns:
                if col != date_col and pd.api.types.is_numeric_dtype(df[col]):
                    gpr_col = col
                    break
            if gpr_col is None and len(df.columns) > 1:
                gpr_col = df.columns[1]
            logger.warning(f"GPR column not found by name, using column: {gpr_col!r}")

        if date_col is None or gpr_col is None:
            logger.error(f"Required columns not found. Available: {list(df.columns)}")
            return False
       
        # Standardize column names
        df = df.rename(columns={date_col: 'date', gpr_col: 'gpr_index'})
       
        # Keep only required columns
        df = df[['date', 'gpr_index']].copy()
       
        # Clean and validate data
        df = df.dropna()
       
        # Try to parse dates
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date'])
       
        if df.empty:
            logger.error("No valid data after cleaning")
            return False
       
        # Save as CSV
        df.to_csv(output_path, index=False)
        logger.info(f"GPR data saved successfully with {len(df)} rows to {output_path}")
       
        return True
       
    except Exception as e:
        logger.error(f"Failed to download GPR data: {e}")
        return False
 
def load_gpr(csv_path: str, start, end) -> pd.DataFrame:
    """
    Load GPR data from the CSV file (no inline download – updates happen via scheduler).

    Args:
        csv_path: Path to GPR CSV file
        start: Start date for filtering
        end: End date for filtering

    Returns:
        DataFrame with GPR data indexed by date
    """
    start = ensure_datetime(start)
    end = ensure_datetime(end)

    if not os.path.exists(csv_path):
        logger.warning(f"GPR CSV not found at {csv_path}. Run /data/update or wait for the scheduler.")
        return pd.DataFrame()

    # Warn if stale but do NOT block the request with a synchronous download
    file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(csv_path))
    if file_age > timedelta(hours=25):
        logger.warning(f"GPR CSV is {file_age} old – scheduler should refresh it shortly.")

    # Load the data
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        logger.warning(f"Failed to read GPR CSV: {e}")
        return pd.DataFrame()
   
    if "date" not in df.columns:
        logger.warning("GPR CSV missing 'date' column")
        return pd.DataFrame()
   
    df['date'] = pd.to_datetime(df['date'])
    mask = (df['date'] >= start) & (df['date'] <= end)
    df = df.loc[mask].copy()
   
    if df.empty:
        return pd.DataFrame()
   
    df.set_index('date', inplace=True)
    df = df.ffill().bfill()
    return df
 
def fetch_weather(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    """
    Fetch daily weather variables from Open-Meteo archive API.
    Returns DataFrame indexed by date (DatetimeIndex).
    """
    url = (
        f"https://archive-api.open-meteo.com/v1/archive?"
        f"latitude={lat}&longitude={lon}&start_date={start}&end_date={end}"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
        "&timezone=UTC"
    )
    try:
        r = requests.get(url, timeout=20)
    except Exception as e:
        logger.debug(f"Weather request failed ({lat},{lon}): {e}")
        return pd.DataFrame()
    if r.status_code != 200:
        logger.debug(f"Weather API returned status {r.status_code} for {lat},{lon}")
        return pd.DataFrame()
    try:
        payload = r.json()
    except Exception:
        logger.debug("Weather API returned non-JSON payload")
        return pd.DataFrame()
    daily = payload.get("daily", {})
    if not daily:
        return pd.DataFrame()
    df = pd.DataFrame(daily)
    if "time" not in df.columns:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["time"])
    df.set_index("date", inplace=True)
    df = df.drop(columns=["time"], errors="ignore")
    return df
 
def fetch_multi_weather(locs: List[dict], start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch weather for multiple locations and average by date.
    Limit the historical requests to last 3 years to avoid huge payloads.
    """
    # enforce strings in YYYY-MM-DD
    try:
        req_start = pd.to_datetime(start_date).date()
    except Exception:
        req_start = datetime.now().date() - timedelta(days=365)
    max_start = datetime.now().date() - timedelta(days=3*365)
    start_dt = max(req_start, max_start)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = pd.to_datetime(end_date).strftime("%Y-%m-%d")
 
    dfs = []
    for loc in locs:
        d = fetch_weather(loc["lat"], loc["lon"], start_str, end_str)
        if not d.empty:
            dfs.append(d)
    if not dfs:
        return pd.DataFrame()
    df_all = pd.concat(dfs, axis=0)
    df_mean = df_all.groupby(level=0).mean().sort_index()
    return df_mean
 
# ---------------- FEATURE ENGINEERING ----------------
def make_features(series: pd.Series, exog_df: pd.DataFrame) -> pd.DataFrame:
    """
    series: pd.Series indexed by date (price)
    exog_df: DataFrame indexed by date (may be empty)
    returns: DataFrame of features (aligned and dropna)
    """
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
 
    df = pd.DataFrame({"y": series})
    # lags
    for l in [1,2,3,5,7,10,14,21,30]:
        df[f"lag_{l}"] = df["y"].shift(l)
    # rolling stats
    for w in [5,7,14,21,30]:
        df[f"roll_mean_{w}"] = df["y"].shift(1).rolling(w).mean()
        df[f"roll_std_{w}"]  = df["y"].shift(1).rolling(w).std()
    # EMAs
    for span in [10,20,30]:
        df[f"ema_{span}"] = df["y"].shift(1).ewm(span=span, adjust=False).mean()
 
    # join exogenous if provided
    if exog_df is not None and not exog_df.empty:
        ex = exog_df.reindex(df.index).ffill().bfill()
        df = df.join(ex, how="left")
 
    df = df.dropna()
    return df
 
def add_direct_target(df_feat: pd.DataFrame, horizon: int) -> pd.DataFrame:
    df = df_feat.copy()
    df["y_t+h"] = df["y"].shift(-horizon)
    return df.dropna()
 
# ---------------- FORECASTING ----------------
def forecast(series: pd.Series, exog_df: pd.DataFrame, horizons: List[int]) -> pd.DataFrame:
    """
    Returns DataFrame with columns:
    horizon, forecast_price, low_80, high_80, low_95, high_95
    Uses direct multi-horizon XGBoost for horizons > 1 and 1-day model for horizon==1.
    """
    base = make_features(series, exog_df)
    out_rows = []
    if base.empty:
        for h in horizons:
            out_rows.append({
                "horizon": h,
                "forecast_price": np.nan,
                "low_80": np.nan, "high_80": np.nan,
                "low_95": np.nan, "high_95": np.nan
            })
        return pd.DataFrame(out_rows)
 
    for h in horizons:
        df_h = add_direct_target(base.copy(), h)
        feats = [c for c in df_h.columns if c not in ["y", "y_t+h"]]
        if len(df_h) < MIN_TRAIN or len(feats) == 0:
            out_rows.append({
                "horizon": h,
                "forecast_price": np.nan,
                "low_80": np.nan, "high_80": np.nan,
                "low_95": np.nan, "high_95": np.nan
            })
            continue
 
        model = XGBRegressor(**XGB_CFG.get(h, XGB_CFG[1]))
        # train
        X_train = df_h[feats]
        y_train = df_h["y_t+h"]
        try:
            model.fit(X_train, y_train)
        except Exception as e:
            logger.warning(f"Model fit failed for horizon {h}: {e}")
            out_rows.append({
                "horizon": h,
                "forecast_price": np.nan,
                "low_80": np.nan, "high_80": np.nan,
                "low_95": np.nan, "high_95": np.nan
            })
            continue
 
        # last row features (from base) - ensure feats exist in base
        X_last = base.iloc[[-1]][feats]
        try:
            y_hat = float(model.predict(X_last)[0])
        except Exception as e:
            logger.warning(f"Prediction failed for horizon {h}: {e}")
            y_hat = np.nan
 
        # residuals for rough CI (in-sample)
        residuals = y_train.values - model.predict(X_train)
        sigma = np.nanstd(residuals)
        out_rows.append({
            "horizon": h,
            "forecast_price": y_hat,
            "low_80": (y_hat - 1.28 * sigma) if not np.isnan(y_hat) else np.nan,
            "high_80": (y_hat + 1.28 * sigma) if not np.isnan(y_hat) else np.nan,
            "low_95": (y_hat - 1.96 * sigma) if not np.isnan(y_hat) else np.nan,
            "high_95": (y_hat + 1.96 * sigma) if not np.isnan(y_hat) else np.nan
        })
 
    return pd.DataFrame(out_rows)
 
# ---------------- SAVE ----------------
def save_predictions(db_engine, commodity: str, forecasts: pd.DataFrame, last_date: pd.Timestamp):
    """
    Save into predictions table: prediction_date, horizon, model_name, commodity, forecast_price, created_at
    Upserts by (prediction_date, horizon, model_name, commodity)
    """
    if forecasts is None or forecasts.empty:
        return
    with db_engine.begin() as conn:
        for _, row in forecasts.iterrows():
            if pd.isna(row.get("forecast_price", np.nan)):
                continue
            future_date = (pd.to_datetime(last_date) + pd.Timedelta(days=int(row["horizon"]))).to_pydatetime()
            try:
                conn.execute(text("""
                    INSERT INTO predictions (prediction_date, horizon, model_name, commodity, forecast_price, created_at)
                    VALUES (:prediction_date, :horizon, :model_name, :commodity, :forecast_price, :created_at)
                    ON CONFLICT (prediction_date, horizon, model_name, commodity)
                    DO UPDATE SET forecast_price = EXCLUDED.forecast_price,
                                  created_at = EXCLUDED.created_at
                """), {
                    "prediction_date": future_date,
                    "horizon": int(row["horizon"]),
                    "model_name": MODEL_NAME,
                    "commodity": commodity.lower(),
                    "forecast_price": float(row["forecast_price"]),
                    "created_at": datetime.now()
                })
            except Exception as e:
                logger.warning(f"DB insert failed for {commodity} horizon {row['horizon']}: {e}")
 
# ---------------- FASTAPI ----------------
app = FastAPI(title="Commodity Forecast API - XGBoost single-file")

# CORS so the browser-based frontend can call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """On startup: ensure GPR data exists; if missing or stale, trigger a background download."""
    needs_update = False
    if not os.path.exists(GPR_CSV_PATH):
        logger.info("[Startup] GPR CSV missing – triggering initial download.")
        needs_update = True
    else:
        age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(GPR_CSV_PATH))
        if age > timedelta(hours=25):
            logger.info(f"[Startup] GPR CSV is {age} old – triggering refresh.")
            needs_update = True
    if needs_update:
        t = threading.Thread(target=_gpr_background_update, daemon=True)
        t.start()

# Mount static files for dashboard (CSS, JS)
# Check multiple possible paths for the dashboard
# In Docker: /app/dashboard (container working directory is /app)
# Locally: ../dashboard (relative to app/main.py)
possible_dashboard_paths = [
    os.path.join(os.getcwd(), "dashboard"),  # Docker: /app/dashboard
    os.path.join(os.path.dirname(__file__), "..", "dashboard"),  # Local development
    "/app/dashboard"  # Absolute path in Docker
]

DASHBOARD_PATH = None
for path in possible_dashboard_paths:
    if os.path.exists(path):
        DASHBOARD_PATH = os.path.abspath(path)
        logger.info(f"Dashboard found at: {DASHBOARD_PATH}")
        break

if DASHBOARD_PATH:
    app.mount("/static", StaticFiles(directory=DASHBOARD_PATH), name="static")
else:
    logger.warning("Dashboard folder not found in any expected location")


@app.get("/")
def root():
    """
    Serve the Steel HRC Price Dashboard frontend
    """
    if DASHBOARD_PATH:
        dashboard_html = os.path.join(DASHBOARD_PATH, "index.html")
        if os.path.exists(dashboard_html):
            return FileResponse(dashboard_html, media_type="text/html")
    # Fallback to API info if dashboard not found
    return {
        "name": "Steel HRC Price Prediction API",
        "status": "online",
        "version": "1.0.0",
        "message": "Dashboard not found. Use /docs for API documentation."
    }


@app.get("/api/info")
def api_info():
    """
    API endpoint for health check and info
    """
    return {
        "name": "Steel HRC Price Prediction API",
        "status": "online",
        "version": "1.0.0",
        "endpoints": {
            "/price/history": "Get historical price data",
            "/forecast": "Get AI price predictions",
            "/data/status": "Get GPR dataset status",
            "/data/update": "Trigger GPR dataset update",
            "/docs": "API documentation (Swagger UI)"
        }
    }

@app.get("/price/history")
def get_price_history(commodity: str = Query(...), days: int = Query(60, ge=1, le=365)):
    """
    Return recent daily close prices for the requested commodity, for use in the
    Market Data chart on the frontend.
    """
    c = commodity.lower()
    if c not in COMMODITY_TICKERS:
        raise HTTPException(status_code=400, detail=f"Unknown commodity '{commodity}'")

    ticker = COMMODITY_TICKERS[c]
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)

    df_price = fetch_yfinance(ticker, start_date, end_date)
    if df_price.empty or "close" not in df_price.columns:
        raise HTTPException(status_code=404, detail="No price data available")

    series = df_price["close"].astype(float).dropna()
    if series.empty:
        raise HTTPException(status_code=404, detail="No price data available")

    points = [
        {"date": idx.date().isoformat(), "price": float(val)}
        for idx, val in series.items()
    ]

    return {
        "commodity": c.upper(),
        "points": points,
        "start_date": points[0]["date"],
        "end_date": points[-1]["date"],
        "rows": len(points),
    }
 
@app.get("/forecast")
def get_forecast(commodities: Optional[List[str]] = Query(None)):
    """
    Run forecasting pipeline for selected commodities (or all if none provided).
    Returns list of forecasts and also persists them to the 'predictions' table.
    """
    # 5 years of data as requested
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=5 * 365)
 
    # fetch exogenous: inflation + GPR
    logger.info("Fetching inflation from FRED...")
    df_infl = fetch_fred_inflation(start_date, end_date)
    logger.info(f"Inflation rows: {len(df_infl)}" if not df_infl.empty else "Inflation empty")
 
    logger.info("Loading GPR CSV...")
    df_gpr = load_gpr(GPR_CSV_PATH, start_date, end_date)
    logger.info(f"GPR rows: {len(df_gpr)}" if not df_gpr.empty else "GPR empty")
 
    # build exog_base (daily)
    exog_base = pd.DataFrame()
    if not df_infl.empty:
        exog_base = df_infl.copy()
    if not df_gpr.empty:
        exog_base = exog_base.join(df_gpr, how="outer") if not exog_base.empty else df_gpr.copy()
 
    selected = [s.lower() for s in commodities] if commodities else list(COMMODITY_TICKERS.keys())
    response = []
 
    for commodity in selected:
        if commodity not in COMMODITY_TICKERS:
            logger.info(f"Skipping unknown commodity {commodity}")
            continue
        ticker = COMMODITY_TICKERS[commodity]
        logger.info(f"Processing commodity: {commodity} (ticker={ticker})")
 
        # fetch price
        df_price = fetch_yfinance(ticker, start_date, end_date)
        if df_price.empty or "close" not in df_price.columns:
            logger.warning(f"No price data for {commodity}, skipping")
            continue
 
        series = df_price["close"].astype(float).dropna()
        if series.empty or len(series) < MIN_TRAIN:
            logger.warning(f"Not enough data for {commodity} (rows={len(series)}). Need >= {MIN_TRAIN}. Skipping.")
            continue
 
        # weather for commodity (averaged across locs)
        start_str = series.index.min().strftime("%Y-%m-%d")
        end_str = series.index.max().strftime("%Y-%m-%d")
        locs = LOCATIONS.get(commodity, [])
        weather_df = pd.DataFrame()
        if locs:
            logger.info(f"Fetching weather for {commodity} (avg {len(locs)} locs)...")
            weather_df = fetch_multi_weather(locs, start_str, end_str)
            if weather_df.empty:
                logger.info("Weather fetch returned empty (continuing without weather)")
 
        # construct exog aligned to series index
        exog_for_series = pd.DataFrame(index=series.index)
        if not exog_base.empty:
            exog_for_series = exog_for_series.join(exog_base.reindex(series.index).ffill().bfill(), how="left")
        if not weather_df.empty:
            exog_for_series = exog_for_series.join(weather_df.reindex(series.index).ffill().bfill(), how="left")
        if exog_for_series.isna().all(axis=None):
            exog_for_series = pd.DataFrame()  # let make_features ignore exog
 
        # forecast
        logger.info("Building features and training models...")
        fc = forecast(series, exog_for_series, HORIZONS)
 
        # save to DB
        try:
            save_predictions(engine, commodity, fc, series.index[-1])
            logger.info("Saved forecasts to DB")
        except Exception as e:
            logger.warning(f"Failed to save predictions for {commodity}: {e}")
 
        # prepare API response for this commodity
        preds = {}
        last_price = float(series.iloc[-1])
        for _, row in fc.iterrows():
            h = int(row["horizon"])
            pred_price = row.get("forecast_price", np.nan)
            if pd.isna(pred_price):
                continue
            change = ((pred_price - last_price) / last_price) * 100 if last_price != 0 else 0.0
            direction = "up" if change >= 0 else "down"
            preds[f"{h}_day"] = {
                "predicted_price": round(float(pred_price), 6),
                "change_percent": round(float(change), 4),
                "direction": direction,
                "confidence_intervals": {
                    "80": {
                        "low": None if pd.isna(row.get("low_80")) else round(float(row.get("low_80")), 4),
                        "high": None if pd.isna(row.get("high_80")) else round(float(row.get("high_80")), 4),
                    },
                    "95": {
                        "low": None if pd.isna(row.get("low_95")) else round(float(row.get("low_95")), 4),
                        "high": None if pd.isna(row.get("high_95")) else round(float(row.get("high_95")), 4),
                    }
                }
            }
 
        response.append({
            "commodity": commodity.upper(),
            "timestamp": series.index[-1].isoformat(),
            "current_price": round(last_price, 6),
            "predictions": preds,
            "rows_used": int(len(series)),
            "last_updated": datetime.now().isoformat()
        })
 
    return {"results": response}
 
@app.get("/data/update")
def update_gpr_dataset(force: bool = False):
    """
    Manually trigger GPR dataset update
   
    Args:
        force: Force update regardless of file age
   
    Returns:
        Update result with status
    """
    try:
        # Check if update is needed (unless forced)
        if not force and os.path.exists(GPR_CSV_PATH):
            file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(GPR_CSV_PATH))
            if file_age < timedelta(hours=23):
                return {
                    "success": True,
                    "message": f"Dataset is recent (age: {file_age}), skipping update. Use force=true to override.",
                    "timestamp": datetime.now().isoformat()
                }
       
        # Perform update
        success = download_gpr_data()
       
        if success:
            return {
                "success": True,
                "message": "GPR dataset updated successfully",
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "message": "Failed to update GPR dataset",
                "timestamp": datetime.now().isoformat()
            }
           
    except Exception as e:
        logger.error(f"Manual dataset update failed: {e}")
        return {
            "success": False,
            "message": f"Dataset update failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
 
@app.get("/data/status")
def get_dataset_status():
    """
    Get current status of the GPR dataset
   
    Returns:
        Dataset status information
    """
    try:
        status = {
            "gpr_file_exists": os.path.exists(GPR_CSV_PATH),
            "dataset_url": GPR_DATASET_URL,
            "timestamp": datetime.now().isoformat()
        }
       
        if status["gpr_file_exists"]:
            file_stat = os.stat(GPR_CSV_PATH)
            status["file_size_bytes"] = file_stat.st_size
            status["last_modified"] = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
           
            # Calculate file age
            file_age = datetime.now() - datetime.fromtimestamp(file_stat.st_mtime)
            status["file_age_hours"] = round(file_age.total_seconds() / 3600, 2)
            status["needs_update"] = file_age > timedelta(hours=24)
           
            # Try to read and get basic stats
            try:
                df = pd.read_csv(GPR_CSV_PATH)
                status["total_rows"] = len(df)
                if "date" in df.columns:
                    df['date'] = pd.to_datetime(df['date'])
                    status["date_range"] = {
                        "start": df['date'].min().isoformat(),
                        "end": df['date'].max().isoformat()
                    }
            except Exception as e:
                status["file_read_error"] = str(e)
       
        return status
       
    except Exception as e:
        return {
            "error": f"Failed to get dataset status: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
 
