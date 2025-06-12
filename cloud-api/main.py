"""
RoluATM Cloud API - FastAPI Application with Embedded Models

Vercel-hosted FastAPI service with Neon Postgres integration.
Database models embedded to avoid import issues in serverless environment.
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from contextlib import asynccontextmanager
from enum import Enum

import httpx
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlmodel import Field, SQLModel, Relationship, Session, create_engine, select
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from dotenv import load_dotenv

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

logger.info(f"World ID App ID: {WORLD_ID_APP_ID}")
logger.info(f"World ID Action: {WORLD_ID_ACTION}")
logger.info(f"Database URL configured: {bool(DATABASE_URL)}")

# =============================================================================
# DATABASE MODELS (Embedded for Vercel compatibility)
# =============================================================================

class TransactionStatus(str, Enum):
    """Transaction status enumeration"""
    PENDING = "pending"
    VERIFIED = "verified"
    DISPENSING = "dispensing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class User(SQLModel, table=True):
    """User model with World ID integration"""
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    world_id_nullifier: str = Field(unique=True, index=True)
    verification_level: str = Field(default="orb")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Statistics
    total_transactions: int = Field(default=0)
    total_amount_usd: float = Field(default=0.0)
    last_transaction_at: Optional[datetime] = None
    
    # Relationships
    transactions: list["Transaction"] = Relationship(back_populates="user")


class Kiosk(SQLModel, table=True):
    """Kiosk registration and status tracking"""
    __tablename__ = "kiosks"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    kiosk_id: str = Field(unique=True, index=True)
    location_name: Optional[str] = None
    location_address: Optional[str] = None
    
    # Hardware info
    serial_port: str = Field(default="/dev/ttyACM0")
    firmware_version: Optional[str] = None
    
    # Status
    is_active: bool = Field(default=True)
    last_seen_at: Optional[datetime] = None
    last_health_status: Optional[str] = None
    
    # Statistics
    total_transactions: int = Field(default=0)
    total_coins_dispensed: int = Field(default=0)
    
    # Audit
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Relationships
    transactions: list["Transaction"] = Relationship(back_populates="kiosk")


class Transaction(SQLModel, table=True):
    """Transaction record with full audit trail"""
    __tablename__ = "transactions"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(unique=True, index=True)
    
    # Foreign keys
    user_id: Optional[int] = Field(foreign_key="users.id")
    kiosk_id: Optional[int] = Field(foreign_key="kiosks.id")
    
    # Transaction details
    amount_usd: float
    fee_usd: float = Field(default=0.50)
    quarters_requested: int
    quarters_dispensed: Optional[int] = None
    
    # Status and timing
    status: TransactionStatus = Field(default=TransactionStatus.PENDING)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    verified_at: Optional[datetime] = None
    dispensed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    expires_at: datetime
    
    # World ID verification
    world_id_merkle_root: Optional[str] = None
    world_id_nullifier_hash: Optional[str] = None
    world_id_proof: Optional[str] = None
    
    # Error tracking
    error_message: Optional[str] = None
    retry_count: int = Field(default=0)
    
    # Relationships
    user: Optional[User] = Relationship(back_populates="transactions")
    kiosk: Optional[Kiosk] = Relationship(back_populates="transactions")


class KioskHealthLog(SQLModel, table=True):
    """Kiosk health monitoring logs"""
    __tablename__ = "kiosk_health_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    kiosk_id: str = Field(index=True)
    
    # Status information
    overall_status: str
    hardware_status: str
    cloud_status: bool
    
    # Hardware details
    tflex_connected: bool
    tflex_port: str
    coin_count: Optional[int] = None
    
    # Timing
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Optional error details
    error_details: Optional[str] = None


class WorldIDVerification(SQLModel, table=True):
    """World ID verification attempts and results"""
    __tablename__ = "worldid_verifications"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    nullifier_hash: str = Field(index=True)
    
    # Verification data
    merkle_root: str
    proof: str
    verification_level: str
    
    # Result
    is_verified: bool
    error_message: Optional[str] = None
    
    # Timing
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    verified_at: Optional[datetime] = None
    
    # IP and user agent for security
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None


def create_db_and_tables(engine):
    """Create all database tables"""
    SQLModel.metadata.create_all(engine)

# =============================================================================
# DATABASE ENGINE SETUP
# =============================================================================

# Create database engine with error handling
try:
    if DATABASE_URL and DATABASE_URL != "sqlite:///./test.db":
        engine = create_engine(DATABASE_URL, echo=False)
        DATABASE_CONNECTED = True
        DB_MODELS_AVAILABLE = True
        logger.info("✓ Database engine created successfully")
    else:
        engine = None
        DATABASE_CONNECTED = False
        DB_MODELS_AVAILABLE = False
        logger.warning("Database engine not initialized - limited functionality")
except Exception as e:
    logger.error(f"Database engine creation failed: {e}")
    engine = None
    DATABASE_CONNECTED = False
    DB_MODELS_AVAILABLE = False

# SSE connections store
sse_connections: dict[str, list] = {}

# =============================================================================
# FASTAPI APPLICATION SETUP
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("Starting RoluATM Cloud API")
    
    if engine and DATABASE_CONNECTED:
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
    
    yield
    
    # Shutdown
    logger.info("Shutting down RoluATM Cloud API")


# Create FastAPI app
app = FastAPI(
    title="RoluATM Cloud API",
    description="World ID-verified cryptocurrency ATM service",
    version="1.0.0"
    # lifespan=lifespan  # Temporarily disabled for Vercel compatibility
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# DEPENDENCIES AND UTILITIES
# =============================================================================

# Dependency to get database session
def get_session():
    if not engine or not DATABASE_CONNECTED:
        raise HTTPException(status_code=503, detail="Database not available")
    with Session(engine) as session:
        yield session


# Pydantic models for API
class WorldIDPayload(BaseModel):
    merkle_root: str
    nullifier_hash: str
    proof: str
    verification_level: str


class VerifyWorldIDRequest(BaseModel):
    session_id: str
    world_id_payload: WorldIDPayload
    amount_usd: float


class WithdrawalLockRequest(BaseModel):
    kiosk_id: str
    session_id: str
    amount_usd: float
    coins_needed: int


class WithdrawalSettleRequest(BaseModel):
    kiosk_id: str
    session_id: str
    coins_dispensed: int
    timestamp: str


class KioskHealthUpdate(BaseModel):
    kiosk_id: str
    overall_status: str
    hardware_status: str
    cloud_status: bool
    tflex_connected: bool
    tflex_port: str
    coin_count: Optional[int] = None
    error_details: Optional[str] = None


async def verify_world_id(payload: WorldIDPayload) -> bool:
    """Verify World ID proof with Worldcoin API"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://developer.worldcoin.org/api/v1/verify",
                json={
                    "nullifier_hash": payload.nullifier_hash,
                    "merkle_root": payload.merkle_root,
                    "proof": payload.proof,
                    "verification_level": payload.verification_level,
                    "action": WORLD_ID_ACTION
                },
                headers={
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("success", False)
            else:
                logger.error(f"World ID verification failed: {response.status_code} {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"World ID verification error: {e}")
        return False


async def broadcast_kiosk_event(kiosk_id: str, event_type: str, data: dict):
    """Broadcast event to SSE subscribers for a kiosk"""
    if kiosk_id in sse_connections:
        event_data = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        active_connections = []
        for connection in sse_connections[kiosk_id]:
            try:
                await connection.send(event_data)
                active_connections.append(connection)
            except:
                # Connection closed
                pass
        
        sse_connections[kiosk_id] = active_connections

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    response = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "RoluATM Cloud API",
        "version": "1.0.0",
        "environment": {
            "has_database_url": bool(DATABASE_URL and DATABASE_URL != "sqlite:///./test.db"),
            "world_id_app_id": bool(WORLD_ID_APP_ID),
            "world_id_action": bool(WORLD_ID_ACTION)
        },
        "debug": {
            "db_models_available": DB_MODELS_AVAILABLE,
            "database_connected": DATABASE_CONNECTED,
            "engine_available": engine is not None
        }
    }
    
    if DATABASE_URL and DATABASE_URL != "sqlite:///./test.db" and engine and DATABASE_CONNECTED:
        try:
            # Test database connectivity
            with Session(engine) as session:
                session.exec(select(1))
            response["database"] = "connected"
        except Exception as e:
            logger.error(f"Health check database failed: {e}")
            response["database"] = f"error: {str(e)}"
            response["status"] = "degraded"
    else:
        response["database"] = "not_configured" if not DATABASE_URL else "not_connected"
        response["status"] = "limited"
    
    return response


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "RoluATM Cloud API",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "operational",
        "debug": {
            "db_models_available": DB_MODELS_AVAILABLE,
            "database_connected": DATABASE_CONNECTED,
            "engine_available": engine is not None
        }
    }


@app.get("/test")
async def test_endpoint():
    """Simple test endpoint for deployment verification"""
    return {
        "message": "Hello from RoluATM Cloud API with embedded models!",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "models_embedded": True
    }


# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 