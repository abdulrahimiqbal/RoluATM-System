#!/usr/bin/env python3
"""
Database Initialization Script for RoluATM
Creates all necessary tables in fresh Neon database
"""

import os
import logging
from sqlmodel import create_engine, SQLModel

# Import models from main.py
from main import (
    User, Kiosk, Transaction, KioskHealthLog, 
    WorldIDVerification, TransactionStatus
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_database():
    """Initialize database with all tables"""
    
    # Get database URL
    database_url = os.getenv("NEON_DATABASE_URL")
    if not database_url:
        logger.error("NEON_DATABASE_URL environment variable not found")
        return False
    
    try:
        # Create engine
        engine = create_engine(database_url, echo=True)
        logger.info("✓ Database engine created")
        
        # Create all tables
        SQLModel.metadata.create_all(engine)
        logger.info("✓ All tables created successfully")
        
        # Test connection
        from sqlmodel import Session, select
        with Session(engine) as session:
            result = session.exec(select(1)).first()
            logger.info(f"✓ Database connection test successful: {result}")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Database initialization failed: {e}")
        return False

if __name__ == "__main__":
    logger.info("Starting database initialization...")
    success = init_database()
    if success:
        logger.info("🎉 Database initialization completed successfully!")
    else:
        logger.error("❌ Database initialization failed!")
        exit(1) 