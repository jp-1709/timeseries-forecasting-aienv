# Price Prediction Service

FastAPI-based commodity price prediction service using XGBoost models with geopolitical risk (GPR) data, weather, and inflation indicators.

## Features

- Real-time commodity price forecasting (Gold, Silver, Copper, Crude Oil, Natural Gas, Steel)
- Multi-horizon predictions (1, 7, 30, 60 days)
- Automatic daily GPR dataset updates
- External data sources: Yahoo Finance, FRED, Open-Meteo, GPR Index

## Quick Deploy to Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

### Manual Deployment

1. **Fork/Clone this repository**
2. **Go to [Render Dashboard](https://dashboard.render.com/)**
3. **Create New Web Service**
   - Connect your GitHub repository
   - Select this repo: `Arihant-Rock/Price-Prediction`
   - Render will auto-detect the Dockerfile

4. **Configure Environment Variables**
   - `DB_URI`: Your PostgreSQL connection string (optional if not using DB)
   - `FRED_API_KEY`: Already set to default (can update with your own)
   - `PORT`: Auto-set by Render

5. **Deploy**
   - Click "Create Web Service"
   - Render will build and deploy automatically

## Local Development

### Prerequisites

- Python 3.11+
- PostgreSQL (optional)

### Setup

```bash
# Clone repository
git clone https://github.com/Arihant-Rock/Price-Prediction.git
cd Price-Prediction

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn app.main:app --reload --port 8000
```

### Update GPR Data

```bash
python daily_update.py
```

## API Endpoints

- `GET /` - Health check
- `GET /forecast?commodities=gold,silver` - Get price forecasts
- `GET /price/history?commodity=gold&days=60` - Historical prices
- `GET /data/update?force=true` - Manually update GPR data
- `GET /data/status` - Check GPR dataset status

## Tech Stack

- **Framework**: FastAPI
- **ML Model**: XGBoost
- **Data Sources**: yfinance, FRED API, Open-Meteo, GPR Index
- **Database**: PostgreSQL (optional)
- **Deployment**: Docker, Render

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_URI` | PostgreSQL connection string | `postgresql+psycopg2://...` |
| `FRED_API_KEY` | FRED API key for inflation data | `eef937e...` |
| `PORT` | Server port | `8000` |

## License

MIT