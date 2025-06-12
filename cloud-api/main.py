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
import json

import httpx
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request, StreamingResponse
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
                f"https://developer.worldcoin.org/api/v2/verify/{WORLD_ID_APP_ID}",
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


@app.get("/pay/{session_id}")
async def payment_interface(session_id: str, request: Request):
    """Generate World ID payment interface"""
    
    # For RoluATM, we're using External Integration, not Mini App
    # Generate the correct World ID verification URL
    
    world_id_verify_url = f"https://worldcoin.org/verify?app_id={WORLD_ID_APP_ID}&action={WORLD_ID_ACTION}&signal={session_id}"
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>RoluATM Payment</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 400px;
                margin: 50px auto;
                padding: 20px;
                text-align: center;
                background-color: #f5f5f5;
            }}
            .payment-container {{
                background: white;
                border-radius: 16px;
                padding: 40px 30px;
                box-shadow: 0 8px 25px rgba(0,0,0,0.1);
            }}
            .title {{
                font-size: 28px;
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 30px;
            }}
            .session-info {{
                background: #f8f9fa;
                padding: 20px;
                border-radius: 12px;
                margin-bottom: 30px;
                border: 1px solid #e9ecef;
            }}
            .session-label {{
                font-weight: 600;
                color: #6c757d;
                margin-bottom: 8px;
            }}
            .session-id {{
                font-family: 'Courier New', monospace;
                font-size: 16px;
                color: #495057;
                word-break: break-all;
            }}
            .verify-button {{
                background: linear-gradient(135deg, #000000, #333333);
                color: white;
                border: none;
                padding: 16px 32px;
                border-radius: 12px;
                font-size: 18px;
                font-weight: 600;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                margin: 20px 0;
                transition: all 0.3s ease;
                width: 80%;
                max-width: 280px;
            }}
            .verify-button:hover {{
                background: linear-gradient(135deg, #333333, #555555);
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            }}
            .instructions {{
                font-size: 16px;
                color: #6c757d;
                margin: 25px 0;
                line-height: 1.6;
            }}
            .qr-section {{
                margin-top: 30px;
                padding-top: 25px;
                border-top: 1px solid #e9ecef;
            }}
            .qr-text {{
                font-size: 14px;
                color: #6c757d;
                margin-bottom: 15px;
            }}
            .verify-url {{
                background: #f8f9fa;
                padding: 15px;
                border-radius: 8px;
                border: 1px solid #dee2e6;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                color: #495057;
                word-break: break-all;
                margin-top: 15px;
            }}
            .footer {{
                margin-top: 30px;
                font-size: 12px;
                color: #adb5bd;
            }}
        </style>
    </head>
    <body>
        <div class="payment-container">
            <div class="title">RoluATM Payment</div>
            
            <div class="session-info">
                <div class="session-label">Session:</div>
                <div class="session-id">{session_id}</div>
            </div>
            
            <div class="instructions">
                Scan with World App to verify your identity
            </div>
            
            <a href="{world_id_verify_url}" class="verify-button">
                Open in World App
            </a>
            
            <div class="qr-section">
                <div class="qr-text">Or scan this URL with World App:</div>
                <div class="verify-url">{world_id_verify_url}</div>
            </div>
            
            <div class="footer">
                Powered by World ID • Secure • Private
            </div>
        </div>
        
        <script>
            // Auto-refresh verification status
            let checkInterval;
            
            function checkVerificationStatus() {{
                fetch(`/verification-status/{session_id}`)
                    .then(response => response.json())
                    .then(data => {{
                        if (data.verified) {{
                            clearInterval(checkInterval);
                            window.location.href = `/payment-success/{session_id}`;
                        }}
                    }})
                    .catch(error => console.log('Checking verification status...'));
            }}
            
            // Check every 3 seconds
            checkInterval = setInterval(checkVerificationStatus, 3000);
            
            // Clean up on page unload
            window.addEventListener('beforeunload', () => {{
                if (checkInterval) clearInterval(checkInterval);
            }});
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


@app.get("/verification-status/{session_id}")
async def check_verification_status(session_id: str):
    """Check if World ID verification is complete for session"""
    if not DATABASE_CONNECTED:
        return {"verified": False, "error": "Database not available"}
    
    try:
        with Session(engine) as session:
            # Check if verification exists and is successful
            verification = session.exec(
                select(WorldIDVerification)
                .where(WorldIDVerification.session_id == session_id)
                .where(WorldIDVerification.is_verified == True)
            ).first()
            
            return {"verified": verification is not None}
    except Exception as e:
        logger.error(f"Error checking verification status: {e}")
        return {"verified": False, "error": str(e)}


@app.get("/payment-success/{session_id}")
async def payment_success(session_id: str):
    """Payment success page"""
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payment Verified - RoluATM</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 400px;
                margin: 50px auto;
                padding: 20px;
                text-align: center;
                background-color: #f5f5f5;
            }}
            .success-container {{
                background: white;
                border-radius: 16px;
                padding: 40px 30px;
                box-shadow: 0 8px 25px rgba(0,0,0,0.1);
            }}
            .success-icon {{
                font-size: 64px;
                color: #28a745;
                margin-bottom: 20px;
            }}
            .title {{
                font-size: 24px;
                font-weight: bold;
                color: #28a745;
                margin-bottom: 20px;
            }}
            .message {{
                font-size: 16px;
                color: #6c757d;
                line-height: 1.6;
                margin-bottom: 30px;
            }}
            .session-id {{
                background: #f8f9fa;
                padding: 15px;
                border-radius: 8px;
                font-family: 'Courier New', monospace;
                font-size: 14px;
                color: #495057;
                margin-bottom: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="success-container">
            <div class="success-icon">✅</div>
            <div class="title">Payment Verified!</div>
            <div class="message">
                Your World ID verification was successful.<br>
                Please proceed to the kiosk to collect your coins.
            </div>
            <div class="session-id">Session: {session_id}</div>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


@app.post("/verify-worldid")
async def verify_world_id_endpoint(request: VerifyWorldIDRequest, background_tasks: BackgroundTasks):
    """Verify World ID proof and process payment"""
    if not DATABASE_CONNECTED:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        with Session(engine) as session:
            # Verify the World ID proof
            is_verified = await verify_world_id(request.world_id_payload)
            
            # Create verification record
            verification = WorldIDVerification(
                session_id=request.session_id,
                nullifier_hash=request.world_id_payload.nullifier_hash,
                merkle_root=request.world_id_payload.merkle_root,
                proof=request.world_id_payload.proof,
                verification_level=request.world_id_payload.verification_level,
                is_verified=is_verified,
                verified_at=datetime.now(timezone.utc) if is_verified else None
            )
            
            session.add(verification)
            
            if is_verified:
                # Find or create user
                user = session.exec(
                    select(User).where(User.world_id_nullifier == request.world_id_payload.nullifier_hash)
                ).first()
                
                if not user:
                    user = User(
                        world_id_nullifier=request.world_id_payload.nullifier_hash,
                        verification_level=request.world_id_payload.verification_level
                    )
                    session.add(user)
                    session.flush()  # Get user ID
                
                # Calculate quarters (assuming $0.25 per quarter)
                quarters_requested = int(request.amount_usd / 0.25)
                
                # Create transaction
                transaction = Transaction(
                    session_id=request.session_id,
                    user_id=user.id,
                    amount_usd=request.amount_usd,
                    quarters_requested=quarters_requested,
                    status=TransactionStatus.VERIFIED,
                    verified_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
                    world_id_merkle_root=request.world_id_payload.merkle_root,
                    world_id_nullifier_hash=request.world_id_payload.nullifier_hash,
                    world_id_proof=request.world_id_payload.proof
                )
                
                session.add(transaction)
                
                # Update user stats
                user.total_transactions += 1
                user.total_amount_usd += request.amount_usd
                user.last_transaction_at = datetime.now(timezone.utc)
                
                session.commit()
                
                return {
                    "success": True,
                    "session_id": request.session_id,
                    "amount_usd": request.amount_usd,
                    "quarters": quarters_requested,
                    "expires_at": transaction.expires_at.isoformat()
                }
            else:
                session.commit()
                raise HTTPException(
                    status_code=400, 
                    detail="World ID verification failed"
                )
                
    except Exception as e:
        logger.error(f"World ID verification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/verify-withdrawal")
async def verify_withdrawal(request: WithdrawalLockRequest):
    """Verify withdrawal eligibility and lock coins"""
    if not DATABASE_CONNECTED:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        with Session(engine) as session:
            # Find verified transaction
            transaction = session.exec(
                select(Transaction)
                .where(Transaction.session_id == request.session_id)
                .where(Transaction.status == TransactionStatus.VERIFIED)
                .where(Transaction.expires_at > datetime.now(timezone.utc))
            ).first()
            
            if not transaction:
                raise HTTPException(
                    status_code=404, 
                    detail="No valid verified transaction found"
                )
            
            # Update transaction status
            transaction.status = TransactionStatus.DISPENSING
            transaction.quarters_dispensed = request.coins_needed
            session.add(transaction)
            session.commit()
            
            return {
                "success": True,
                "session_id": request.session_id,
                "amount_usd": transaction.amount_usd,
                "coins_approved": request.coins_needed
            }
            
    except Exception as e:
        logger.error(f"Withdrawal verification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/confirm-withdrawal")
async def confirm_withdrawal(request: WithdrawalSettleRequest):
    """Confirm successful coin dispensing"""
    if not DATABASE_CONNECTED:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        with Session(engine) as session:
            # Find dispensing transaction
            transaction = session.exec(
                select(Transaction)
                .where(Transaction.session_id == request.session_id)
                .where(Transaction.status == TransactionStatus.DISPENSING)
            ).first()
            
            if not transaction:
                raise HTTPException(
                    status_code=404, 
                    detail="No dispensing transaction found"
                )
            
            # Complete transaction
            transaction.status = TransactionStatus.COMPLETED
            transaction.quarters_dispensed = request.coins_dispensed
            transaction.dispensed_at = datetime.now(timezone.utc)
            transaction.completed_at = datetime.now(timezone.utc)
            
            session.add(transaction)
            session.commit()
            
            return {
                "success": True,
                "session_id": request.session_id,
                "coins_dispensed": request.coins_dispensed,
                "completed_at": transaction.completed_at.isoformat()
            }
            
    except Exception as e:
        logger.error(f"Withdrawal confirmation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/kiosk-health")
async def update_kiosk_health(request: KioskHealthUpdate, background_tasks: BackgroundTasks):
    """Update kiosk health status"""
    if not DATABASE_CONNECTED:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        with Session(engine) as session:
            # Create health log
            health_log = KioskHealthLog(
                kiosk_id=request.kiosk_id,
                overall_status=request.overall_status,
                hardware_status=request.hardware_status,
                cloud_status=request.cloud_status,
                tflex_connected=request.tflex_connected,
                tflex_port=request.tflex_port,
                coin_count=request.coin_count,
                error_details=request.error_details
            )
            
            session.add(health_log)
            
            # Update or create kiosk record
            kiosk = session.exec(
                select(Kiosk).where(Kiosk.kiosk_id == request.kiosk_id)
            ).first()
            
            if not kiosk:
                kiosk = Kiosk(
                    kiosk_id=request.kiosk_id,
                    serial_port=request.tflex_port,
                    last_health_status=request.overall_status,
                    last_seen_at=datetime.now(timezone.utc)
                )
                session.add(kiosk)
            else:
                kiosk.last_health_status = request.overall_status
                kiosk.last_seen_at = datetime.now(timezone.utc)
                kiosk.serial_port = request.tflex_port
                session.add(kiosk)
            
            session.commit()
            
            # Broadcast health update
            background_tasks.add_task(
                broadcast_kiosk_event,
                request.kiosk_id,
                "health_update",
                {
                    "status": request.overall_status,
                    "hardware": request.hardware_status,
                    "cloud": request.cloud_status,
                    "coins": request.coin_count
                }
            )
            
            return {
                "success": True,
                "kiosk_id": request.kiosk_id,
                "timestamp": health_log.timestamp.isoformat()
            }
            
    except Exception as e:
        logger.error(f"Kiosk health update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# SSE connections storage
sse_connections: dict = {}

class SSEConnection:
    def __init__(self, response):
        self.response = response
        self.active = True
    
    async def send(self, data):
        if not self.active:
            return
        
        try:
            formatted_data = f"event: {data.get('event', 'message')}\ndata: {json.dumps(data.get('data', {}))}\n\n"
            await self.response.send({"type": "http.response.body", "body": formatted_data.encode()})
        except:
            self.active = False


@app.get("/events/{kiosk_id}")
async def stream_kiosk_events(kiosk_id: str, request: Request):
    """Server-Sent Events stream for kiosk updates"""
    
    async def event_generator():
        # Initialize connection
        if kiosk_id not in sse_connections:
            sse_connections[kiosk_id] = []
        
        connection = SSEConnection(None)  # Will be set later
        sse_connections[kiosk_id].append(connection)
        
        sequence = 0
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                
                # Send heartbeat
                event_data = {
                    "event": "heartbeat",
                    "data": {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "kiosk_id": kiosk_id,
                        "sequence": sequence
                    }
                }
                
                yield f"event: heartbeat\ndata: {json.dumps(event_data['data'])}\n\n"
                
                # Send ping comment every 15 seconds
                yield f": ping - {datetime.now()}\n\n"
                
                sequence += 1
                await asyncio.sleep(15)
                
        except asyncio.CancelledError:
            pass
        finally:
            # Clean up connection
            if kiosk_id in sse_connections:
                try:
                    sse_connections[kiosk_id].remove(connection)
                except ValueError:
                    pass
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 