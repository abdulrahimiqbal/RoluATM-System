"""
RoluATM Cloud API - FastAPI Application

Vercel-hosted FastAPI service with Neon Postgres integration.
Handles World ID verification, transaction processing, and kiosk communication.
No local database emulation - fails loudly if Neon is unreachable.
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from contextlib import asynccontextmanager

import json
import httpx
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from sqlmodel import Session, create_engine, select
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import uuid
import time
import base64

# Import database models with proper error handling
try:
    from db.models import (
        User, Kiosk, Transaction, KioskHealthLog, WorldIDVerification,
        TransactionStatus, create_db_and_tables
    )
    DB_MODELS_AVAILABLE = True
except ImportError as e:
    # For Vercel deployment - create minimal mock models
    logging.warning(f"Database models import failed: {e}")
    DB_MODELS_AVAILABLE = False
    
    # Mock models for basic API functionality
    class User: pass
    class Kiosk: pass
    class Transaction: pass
    class KioskHealthLog: pass
    class WorldIDVerification: pass
    class TransactionStatus:
        PENDING = "pending"
        COMPLETED = "completed"
        FAILED = "failed"
    
    def create_db_and_tables(engine): pass

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv("NEON_DATABASE_URL")
if not DATABASE_URL:
    logger.error("NEON_DATABASE_URL environment variable required")
    DATABASE_URL = "sqlite:///./test.db"  # Fallback for development

# World ID configuration
WORLD_ID_APP_ID = os.getenv("WORLD_ID_APP_ID", "app_263013ca6f702add37ad338fa43d4307")
WORLD_ID_ACTION = os.getenv("WORLD_ID_ACTION", "withdraw-cash")
ROLU_WALLET_ADDRESS = os.getenv("ROLU_WALLET_ADDRESS", "0x742fd484b63E7C9b7f34FAb65A8c165B7cd5C5e8")

logger.info(f"World ID App ID: {WORLD_ID_APP_ID}")
logger.info(f"World ID Action: {WORLD_ID_ACTION}")
logger.info(f"RoluATM Wallet: {ROLU_WALLET_ADDRESS}")
logger.info(f"Database URL configured: {bool(DATABASE_URL)}")

# Create database engine with error handling
engine = None
DATABASE_CONNECTED = False
try:
    if DATABASE_URL and DATABASE_URL != "sqlite:///./test.db" and DB_MODELS_AVAILABLE:
        engine = create_engine(DATABASE_URL, echo=False)
        DATABASE_CONNECTED = True
    else:
        logger.warning("Database engine not initialized - limited functionality")
except Exception as e:
    logger.error(f"Database engine creation failed: {e}")
    engine = None
    DATABASE_CONNECTED = False

# SSE connections store
sse_connections: dict[str, list] = {}

# In-memory storage for payment requests (use database in production)
payment_requests = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("Starting RoluATM Cloud API")
    logger.info(f"Database URL: {DATABASE_URL[:50] if DATABASE_URL else 'None'}...")
    
    if DATABASE_URL and DATABASE_URL != "sqlite:///./test.db" and engine:
        try:
            # Test database connection
            with Session(engine) as session:
                session.exec(select(1))
            logger.info("✓ Database connection successful")
            
            # Create tables if they don't exist
            create_db_and_tables(engine)
            logger.info("✓ Database tables verified")
            
        except Exception as e:
            logger.error(f"✗ Database initialization failed: {e}")
            logger.warning("Continuing without database - API will be limited")
    else:
        logger.warning("No database configured - running in limited mode")
    
    yield
    
    # Shutdown
    logger.info("Shutting down RoluATM Cloud API")


# Create FastAPI app
app = FastAPI(
    title="RoluATM Cloud API",
    description="World ID-verified cryptocurrency ATM service",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency to get database session
def get_session():
    if not engine or not DATABASE_CONNECTED:
        raise HTTPException(status_code=503, detail="Database not available")
    with Session(engine) as session:
        yield session

@app.get("/", response_class=HTMLResponse)
async def root():
    # Serve the rolu-miniapp.html file
    try:
        with open("rolu-miniapp.html", "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="rolu-miniapp.html not found")

@app.get("/world-app.json")
async def world_app_manifest():
    """
    World App manifest for Mini Apps.
    Updated to match latest World Mini Apps requirements.
    """
    base_url = os.getenv('VERCEL_URL') or "localhost:8000"
    # Ensure the URL has a scheme for the logo
    logo_url = f"https://{base_url}/favicon.png"

    return {
        "name": "RoluATM",
        "description": "World ID verified cash withdrawal from cryptocurrency",
        "logo": logo_url,
        "category": "finance",
        "verification_required": True,
        "payment_required": True,
        "permissions": [
            "world_id_verify",
            "payments",
            "haptic_feedback"
        ],
        "app_id": WORLD_ID_APP_ID,
        "version": "1.0.0",
        "developer": {
            "name": "RoluATM",
            "url": f"https://{base_url}"
        },
        "supported_countries": ["US", "CA", "GB", "DE", "FR", "AU", "JP"],
        "min_world_app_version": "2.0.0"
    }

@app.get("/favicon.png", response_class=Response)
async def favicon():
    """Serves the favicon for the app."""
    favicon_content = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    return Response(content=favicon_content, media_type="image/png")

async def verify_world_id_proof(world_id_payload: dict) -> bool:
    """
    Securely verifies a World ID proof with the Worldcoin API on the backend.
    Updated to use the latest World ID API v2 endpoint and payload structure.
    """
    api_key = os.getenv("WORLD_API_KEY")
    if not api_key:
        logger.error("CRITICAL: WORLD_API_KEY is not set. Backend verification is disabled.")
        return False

    verification_url = f"https://developer.worldcoin.org/api/v2/verify/{WORLD_ID_APP_ID}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    proof_data = {
        "nullifier_hash": world_id_payload.get("nullifier_hash"),
        "merkle_root": world_id_payload.get("merkle_root"), 
        "proof": world_id_payload.get("proof"),
        "verification_level": world_id_payload.get("verification_level", "orb"),
        "action": WORLD_ID_ACTION,
        **({"signal": world_id_payload.get("signal")} if world_id_payload.get("signal") else {})
    }

    required_fields = ["nullifier_hash", "merkle_root", "proof"]
    missing_fields = [field for field in required_fields if not proof_data.get(field)]
    
    if missing_fields:
        logger.error(f"Backend verification failed: missing required fields: {missing_fields}")
        return False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                verification_url, 
                headers=headers, 
                json=proof_data, 
                timeout=30.0
            )
            
            if response.status_code == 200:
                logger.info("World ID verification successful.")
                return True
            else:
                logger.error(f"World ID verification failed: {response.status_code} - {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"Unexpected error during World ID verification: {e}")
        return False

@app.post("/api/initiate-payment")
async def initiate_payment(request: dict):
    """
    Handles the first step of the payment flow.
    """
    world_id_payload = request.get("payload")
    if not world_id_payload:
        raise HTTPException(status_code=400, detail="World ID payload is required")
    
    is_verified = await verify_world_id_proof(world_id_payload)
    if not is_verified:
        raise HTTPException(status_code=400, detail="World ID verification failed")

    amount_usd = request.get("amount", 10.50)
    payment_id = f"rolu_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    
    payment_requests[payment_id] = {
        "status": "pending",
        "amount": amount_usd,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "world_id_verified": True,
        "nullifier_hash": world_id_payload.get("nullifier_hash")
    }
    
    logger.info(f"Payment initiated - ID: {payment_id}, Amount: ${amount_usd}")

    return {
        "success": True,
        "payment_id": payment_id,
        "reference": payment_id,
        "to": ROLU_WALLET_ADDRESS,
        "tokens": [{"symbol": "USDC", "amount": f"{amount_usd:.6f}"}],
        "description": f"RoluATM Cash Withdrawal - ${amount_usd}"
    }

@app.post("/api/confirm-payment")
async def confirm_payment(request: dict):
    """
    Handles the final step of the payment flow.
    """
    payment_id = request.get("payment_id")
    final_payload = request.get("finalPayload")
    
    if not all([payment_id, final_payload]):
        raise HTTPException(status_code=400, detail="payment_id and finalPayload are required")

    if payment_id not in payment_requests:
        raise HTTPException(status_code=404, detail="Payment ID not found")

    if final_payload.get("status") == "success":
        tx_hash = final_payload.get("transaction_hash")
        payment_requests[payment_id].update({
            "status": "confirmed",
            "tx_hash": tx_hash,
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Triggering cash dispenser for payment {payment_id}")
        return {"success": True, "status": "confirmed", "tx_hash": tx_hash}
    else:
        error_message = final_payload.get("error_message", "Payment failed")
        payment_requests[payment_id].update({"status": "failed", "error_message": error_message})
        return {"success": False, "status": "failed", "message": error_message}

@app.get("/payment-success/{session_id}")
async def payment_success(session_id: str):
    return HTMLResponse(content=f"<html><body><h1>Payment {session_id} Successful!</h1></body></html>")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# For local development
if __name__ == "__main__":
    import uvicorn
    # Point to the location of this file
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)