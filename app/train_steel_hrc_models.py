"""
Script to train and save Steel HRC models for horizons [1, 7, 30, 60]
"""
import sys
import os

# Add parent directory to path to import from main
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import (
    COMMODITY_TICKERS, LOCATIONS, HORIZONS, MIN_TRAIN, XGB_CFG,
    fetch_yfinance, fetch_fred_inflation, load_gpr, fetch_multi_weather,
    make_features, add_direct_target, save_model
)
from xgboost import XGBRegressor
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("train_models")

def train_and_save_steel_hrc_models():
    """
    Train and save Steel HRC models for horizons [1, 7, 30, 60]
    """
    commodity = "steel_hrc"
    horizons = [1, 7, 30, 60]
    
    logger.info(f"Starting training for {commodity} models...")
    
    # Get date range (5 years of data)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=5 * 365)
    
    # Fetch price data
    ticker = COMMODITY_TICKERS[commodity]
    logger.info(f"Fetching price data for {commodity} (ticker: {ticker})...")
    df_price = fetch_yfinance(ticker, start_date, end_date)
    
    if df_price.empty or "close" not in df_price.columns:
        logger.error(f"No price data available for {commodity}")
        return False
    
    series = df_price["close"].astype(float).dropna()
    if series.empty or len(series) < MIN_TRAIN:
        logger.error(f"Not enough data for {commodity} (rows={len(series)}). Need >= {MIN_TRAIN}")
        return False
    
    logger.info(f"Price data: {len(series)} rows from {series.index.min()} to {series.index.max()}")
    
    # Fetch exogenous data
    logger.info("Fetching inflation data from FRED...")
    df_infl = fetch_fred_inflation(start_date, end_date)
    logger.info(f"Inflation rows: {len(df_infl)}" if not df_infl.empty else "Inflation empty")
    
    logger.info("Loading GPR data...")
    df_gpr = load_gpr("gpr.csv", start_date, end_date)
    logger.info(f"GPR rows: {len(df_gpr)}" if not df_gpr.empty else "GPR empty")
    
    # Combine exogenous data
    exog_base = pd.DataFrame()
    if not df_infl.empty:
        exog_base = df_infl.copy()
    if not df_gpr.empty:
        exog_base = exog_base.join(df_gpr, how="outer") if not exog_base.empty else df_gpr.copy()
    
    # Fetch weather data
    locs = LOCATIONS.get(commodity, [])
    weather_df = pd.DataFrame()
    if locs:
        start_str = series.index.min().strftime("%Y-%m-%d")
        end_str = series.index.max().strftime("%Y-%m-%d")
        logger.info(f"Fetching weather data for {len(locs)} locations...")
        weather_df = fetch_multi_weather(locs, start_str, end_str, years_limit=3)
        logger.info(f"Weather rows: {len(weather_df)}" if not weather_df.empty else "Weather empty")
    
    # Prepare exogenous features for the series
    exog_for_series = pd.DataFrame(index=series.index)
    if not exog_base.empty:
        exog_for_series = exog_for_series.join(exog_base.reindex(series.index).ffill(), how="left")
    if not weather_df.empty:
        exog_for_series = exog_for_series.join(weather_df.reindex(series.index).ffill(), how="left")
    if exog_for_series.isna().all(axis=None):
        exog_for_series = pd.DataFrame()
    
    # Build features
    logger.info("Building features...")
    base = make_features(series, exog_for_series)
    
    if base.empty:
        logger.error("Feature matrix is empty after alignment")
        return False
    
    logger.info(f"Feature matrix: {len(base)} rows, {len(base.columns)} columns")
    
    # Train and save models for each horizon
    saved_models = []
    for h in horizons:
        logger.info(f"\n{'='*60}")
        logger.info(f"Training model for horizon {h} days...")
        logger.info(f"{'='*60}")
        
        df_h = add_direct_target(base.copy(), h)
        feats = [c for c in df_h.columns if c not in ["y", "y_t+h"]]
        
        if len(df_h) < MIN_TRAIN or len(feats) == 0:
            logger.warning(f"Insufficient data for horizon {h}: {len(df_h)} rows, {len(feats)} features")
            continue
        
        logger.info(f"Training data: {len(df_h)} rows, {len(feats)} features")
        
        # Create and train model
        model = XGBRegressor(**XGB_CFG.get(h, XGB_CFG[1]))
        X_train = df_h[feats]
        y_train = df_h["y_t+h"]
        
        try:
            logger.info("Fitting model...")
            model.fit(X_train, y_train)
            logger.info("Model training completed successfully")
            
            # Save the model
            filepath = save_model(model, commodity, h)
            if filepath:
                saved_models.append(filepath)
                logger.info(f"✓ Model saved: {filepath}")
                
                # Calculate some metrics
                y_pred = model.predict(X_train)
                mae = np.mean(np.abs(y_train.values - y_pred))
                rmse = np.sqrt(np.mean((y_train.values - y_pred)**2))
                logger.info(f"  Training MAE: {mae:.4f}")
                logger.info(f"  Training RMSE: {rmse:.4f}")
            else:
                logger.error(f"Failed to save model for horizon {h}")
                
        except Exception as e:
            logger.error(f"Error training model for horizon {h}: {e}")
            continue
    
    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("Training Summary")
    logger.info(f"{'='*60}")
    logger.info(f"Commodity: {commodity.upper()}")
    logger.info(f"Horizons requested: {horizons}")
    logger.info(f"Models successfully saved: {len(saved_models)}")
    for fp in saved_models:
        logger.info(f"  - {fp}")
    
    return len(saved_models) == len(horizons)

if __name__ == "__main__":
    success = train_and_save_steel_hrc_models()
    if success:
        logger.info("\n✓ All models trained and saved successfully!")
        sys.exit(0)
    else:
        logger.error("\n✗ Some models failed to train or save")
        sys.exit(1)

