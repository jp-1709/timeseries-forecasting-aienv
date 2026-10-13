#!/usr/bin/env python3
"""
Daily GPR Dataset Update Script
This script can be run as a cron job to update the GPR dataset daily
"""
 
import sys
import os
import logging
from datetime import datetime
 
# Add the current directory to Python path so we can import from app.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
 
# Import the download function from our main app  
from main import download_gpr_data, GPR_DATASET_URL, GPR_CSV_PATH
 
# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('gpr_update.log'),
        logging.StreamHandler()
    ]
)
 
logger = logging.getLogger(__name__)
 
def main():
    """Main function to update GPR dataset"""
    logger.info("Starting daily GPR dataset update")
   
    try:
        # Check if file exists and its age
        if os.path.exists(GPR_CSV_PATH):
            file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(GPR_CSV_PATH))
            logger.info(f"Current file age: {file_age}")
        else:
            logger.info("GPR file does not exist, will download")
       
        # Download the data
        success = download_gpr_data(GPR_DATASET_URL, GPR_CSV_PATH)
       
        if success:
            logger.info("GPR dataset update completed successfully")
            return 0
        else:
            logger.error("GPR dataset update failed")
            return 1
           
    except Exception as e:
        logger.error(f"Unexpected error during update: {e}")
        return 1
 
if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
 
