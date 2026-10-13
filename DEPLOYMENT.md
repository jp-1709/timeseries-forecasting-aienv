# Render Deployment Guide

This guide will walk you through deploying the Price Prediction Service on Render, following the approach from the Medium article.

## Overview

Render is a cloud platform that makes it easy to deploy web services. This guide covers:
1. Setting up your Render account
2. Creating a PostgreSQL database
3. Deploying your web service
4. Configuring environment variables

## Step 1: Prepare Your Repository

1. **Ensure your code is on GitHub**
   - Push all your code to a GitHub repository
   - Make sure `render.yaml` is in the root directory
   - Verify `requirements.txt` includes all dependencies

2. **Verify your code structure**
   ```
   your-repo/
   ├── app/
   │   ├── main.py
   │   └── daily_update.py
   ├── requirements.txt
   ├── render.yaml
   └── README.md
   ```

## Step 2: Sign Up for Render

1. Go to [https://render.com](https://render.com)
2. Click "Get Started for Free"
3. Sign up using your GitHub account (recommended for easy repository access)

## Step 3: Create a PostgreSQL Database

1. In the Render dashboard, click the **"New +"** button
2. Select **"PostgreSQL"**
3. Configure your database:
   - **Name**: `price-prediction-db` (or your preferred name)
   - **Database**: `price_db` (or your preferred name)
   - **User**: `postgres` (default)
   - **Region**: Choose closest to your users
   - **PostgreSQL Version**: Latest stable
   - **Plan**: Free (for testing) or Starter/Standard (for production)
4. Click **"Create Database"**
5. **Important**: Copy the **Internal Database URL** - you'll need this for your web service
   - Format: `postgresql://postgres:password@hostname:5432/database_name`

## Step 4: Create a Web Service

1. In the Render dashboard, click **"New +"** button
2. Select **"Web Service"**
3. **Connect Repository**:
   - Click "Connect account" if not already connected
   - Authorize Render to access your GitHub repositories
   - Select the repository containing your price prediction service
4. **Configure Service**:
   - **Name**: `price-prediction-service` (or your preferred name)
   - **Region**: Same as your database (recommended)
   - **Branch**: `main` (or your default branch)
   - **Root Directory**: Leave empty (if code is in root) or specify if in subdirectory
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free (for testing) or Starter/Standard (for production)

## Step 5: Configure Environment Variables

1. In your web service settings, scroll to **"Environment Variables"** section
2. Click **"Add Environment Variable"** and add each of the following:

   | Key | Value | Description |
   |-----|-------|-------------|
   | `DB_URI` | Your PostgreSQL Internal Database URL from Step 3 | Database connection string. If Render provides `postgresql://`, change to `postgresql+psycopg2://` for SQLAlchemy compatibility |
   | `FRED_API_KEY` | Your FRED API key | Get from https://fred.stlouisfed.org/docs/api/api_key.html |
   | `FRED_SERIES_ID` | `T10YIE` | FRED series ID (default) |
   | `GPR_CSV_PATH` | `gpr.csv` | Path to GPR CSV file (default) |
   | `GPR_DATASET_URL` | `https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls` | GPR dataset URL (default) |

3. **Important Notes**:
   - `DB_URI` should use the **Internal Database URL** (not external) for better performance
   - If using the Internal URL, the format might be `postgresql://...` - you may need to change it to `postgresql+psycopg2://...` for SQLAlchemy
   - Keep your `FRED_API_KEY` secure - never commit it to your repository

## Step 6: Deploy

1. Review all settings
2. Click **"Create Web Service"**
3. Render will:
   - Clone your repository
   - Install dependencies from `requirements.txt`
   - Start your application
4. Monitor the **"Logs"** tab for build progress
5. Wait for deployment to complete (usually 2-5 minutes)

## Step 7: Verify Deployment

1. Once deployed, you'll see a URL like: `https://price-prediction-service.onrender.com`
2. Test your API:
   - Health check: Visit the root URL
   - Get forecast: `https://your-service.onrender.com/forecast?commodities=gold`
   - Check data status: `https://your-service.onrender.com/data/status`

## Step 8: Update Frontend (If Applicable)

If you have a frontend application that calls this API:

1. Update the API base URL in your frontend code:
   ```javascript
   const API_BASE_URL = 'https://your-service.onrender.com';
   ```

2. Ensure CORS is configured if needed (add CORS middleware to FastAPI)

## Troubleshooting

### Build Fails
- Check the build logs for specific errors
- Verify all dependencies are in `requirements.txt`
- Ensure Python version compatibility

### Service Won't Start
- Check start command is correct: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Verify environment variables are set correctly
- Check application logs for runtime errors

### Database Connection Issues
- Verify `DB_URI` uses the Internal Database URL
- Ensure database is in the same region as web service
- Check database credentials are correct

### Service Spins Down (Free Tier)
- Free tier services spin down after 15 minutes of inactivity
- First request after spin-down may take 30-60 seconds
- Consider upgrading to a paid plan for production

## Next Steps

1. **Set up automatic deployments**: Render automatically deploys on git push (if enabled)
2. **Monitor your service**: Use Render's metrics and logs
3. **Set up custom domain**: Add your own domain in service settings
4. **Configure alerts**: Set up email notifications for deployment status

## Cost Considerations

- **Free Tier**: 
  - Web services spin down after inactivity
  - PostgreSQL has 90-day retention limit
  - Good for development and testing
  
- **Paid Plans**:
  - Always-on services
  - Better performance
  - More resources
  - Recommended for production

## Additional Resources

- [Render Documentation](https://render.com/docs)
- [FastAPI Deployment Guide](https://fastapi.tiangolo.com/deployment/)
- [Render Community](https://community.render.com/)

