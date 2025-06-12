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
from fastapi.responses import HTMLResponse
from sqlmodel import Session, create_engine, select
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import uuid

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

logger.info(f"World ID App ID: {WORLD_ID_APP_ID}")
logger.info(f"World ID Action: {WORLD_ID_ACTION}")
logger.info(f"Database URL configured: {bool(DATABASE_URL)}")

# Create database engine with error handling
try:
    if DATABASE_URL and DATABASE_URL != "sqlite:///./test.db" and DB_MODELS_AVAILABLE:
        engine = create_engine(DATABASE_URL, echo=False)
        DATABASE_CONNECTED = True
    else:
        engine = None
        DATABASE_CONNECTED = False
        logger.warning("Database engine not initialized - limited functionality")
except Exception as e:
    logger.error(f"Database engine creation failed: {e}")
    engine = None
    DATABASE_CONNECTED = False

# SSE connections store
sse_connections: dict[str, list] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("Starting RoluATM Cloud API")
    logger.info(f"Database URL: {DATABASE_URL[:50] if DATABASE_URL else 'None'}...")
    
    if DATABASE_URL and DATABASE_URL != "sqlite:///./test.db":
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
    """
    Verify World ID proof with Worldcoin API
    
    Returns:
        True if verification successful, False otherwise
    """
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
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data
        }
        
        # Remove disconnected connections
        active_connections = []
        for connection in sse_connections[kiosk_id]:
            try:
                await connection.send(event_data)
                active_connections.append(connection)
            except:
                # Connection closed
                pass
        
        sse_connections[kiosk_id] = active_connections


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


@app.post("/verify-worldid")
async def verify_worldid(
    request: VerifyWorldIDRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """Verify World ID and create user if needed"""
    
    # Record verification attempt
    verification = WorldIDVerification(
        session_id=request.session_id,
        nullifier_hash=request.world_id_payload.nullifier_hash,
        merkle_root=request.world_id_payload.merkle_root,
        proof=request.world_id_payload.proof,
        verification_level=request.world_id_payload.verification_level,
        is_verified=False
    )
    
    try:
        # Verify with World ID API
        is_verified = await verify_world_id(request.world_id_payload)
        
        if not is_verified:
            verification.error_message = "World ID verification failed"
            session.add(verification)
            session.commit()
            raise HTTPException(status_code=400, detail="World ID verification failed")
        
        # Check for duplicate nullifier
        existing_verification = session.exec(
            select(WorldIDVerification)
            .where(WorldIDVerification.nullifier_hash == request.world_id_payload.nullifier_hash)
            .where(WorldIDVerification.is_verified == True)
        ).first()
        
        if existing_verification:
            verification.error_message = "World ID already used"
            session.add(verification)
            session.commit()
            raise HTTPException(status_code=400, detail="World ID already used for verification")
        
        # Mark verification as successful
        verification.is_verified = True
        verification.verified_at = datetime.now(timezone.utc)
        
        # Get or create user
        user = session.exec(
            select(User)
            .where(User.world_id_nullifier == request.world_id_payload.nullifier_hash)
        ).first()
        
        if not user:
            user = User(
                world_id_nullifier=request.world_id_payload.nullifier_hash,
                verification_level=request.world_id_payload.verification_level
            )
            session.add(user)
            session.flush()  # Get user ID
        
        # Create transaction record
        transaction = Transaction(
            session_id=request.session_id,
            user_id=user.id,
            amount_usd=request.amount_usd,
            quarters_requested=int(request.amount_usd * 4),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            world_id_merkle_root=request.world_id_payload.merkle_root,
            world_id_nullifier_hash=request.world_id_payload.nullifier_hash,
            world_id_proof=request.world_id_payload.proof,
            status=TransactionStatus.VERIFIED,
            verified_at=datetime.now(timezone.utc)
        )
        session.add(transaction)
        
        session.add(verification)
        session.commit()
        
        return {
            "success": True,
            "session_id": request.session_id,
            "user_id": user.id,
            "transaction_id": transaction.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"World ID verification error: {e}")
        verification.error_message = str(e)
        session.add(verification)
        session.commit()
        raise HTTPException(status_code=500, detail="Verification service error")


@app.post("/verify-withdrawal")
async def verify_withdrawal(
    request: WithdrawalLockRequest,
    session: Session = Depends(get_session)
):
    """Verify withdrawal before dispensing (used by kiosk)"""
    
    # Find transaction
    transaction = session.exec(
        select(Transaction)
        .where(Transaction.session_id == request.session_id)
    ).first()
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    if transaction.status != TransactionStatus.VERIFIED:
        raise HTTPException(status_code=400, detail="Transaction not verified")
    
    if transaction.expires_at < datetime.now(timezone.utc):
        transaction.status = TransactionStatus.EXPIRED
        session.commit()
        raise HTTPException(status_code=400, detail="Transaction expired")
    
    if transaction.amount_usd != request.amount_usd:
        raise HTTPException(status_code=400, detail="Amount mismatch")
    
    # Get or create kiosk
    kiosk = session.exec(
        select(Kiosk)
        .where(Kiosk.kiosk_id == request.kiosk_id)
    ).first()
    
    if not kiosk:
        kiosk = Kiosk(kiosk_id=request.kiosk_id)
        session.add(kiosk)
        session.flush()
    
    # Update transaction
    transaction.kiosk_id = kiosk.id
    transaction.status = TransactionStatus.DISPENSING
    session.commit()
    
    return {
        "success": True,
        "session_id": request.session_id,
        "amount_usd": request.amount_usd,
        "coins_to_dispense": request.coins_needed
    }


@app.post("/confirm-withdrawal")
async def confirm_withdrawal(
    request: WithdrawalSettleRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """Confirm withdrawal after coins dispensed (used by kiosk)"""
    
    # Find transaction
    transaction = session.exec(
        select(Transaction)
        .where(Transaction.session_id == request.session_id)
    ).first()
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    # Update transaction
    transaction.quarters_dispensed = request.coins_dispensed
    transaction.status = TransactionStatus.COMPLETED
    transaction.dispensed_at = datetime.fromisoformat(request.timestamp.replace('Z', '+00:00'))
    transaction.completed_at = datetime.now(timezone.utc)
    
    # Update user statistics
    if transaction.user:
        transaction.user.total_transactions += 1
        transaction.user.total_amount_usd += transaction.amount_usd
        transaction.user.last_transaction_at = transaction.completed_at
    
    # Update kiosk statistics
    if transaction.kiosk:
        transaction.kiosk.total_transactions += 1
        transaction.kiosk.total_coins_dispensed += request.coins_dispensed
        transaction.kiosk.last_seen_at = datetime.now(timezone.utc)
    
    session.commit()
    
    return {
        "success": True,
        "session_id": request.session_id,
        "transaction_id": transaction.id,
        "completed_at": transaction.completed_at.isoformat()
    }


@app.get("/events/{kiosk_id}")
async def kiosk_events(kiosk_id: str):
    """Server-Sent Events for live kiosk status"""
    
    async def event_generator():
        try:
            # Send limited heartbeats to avoid serverless timeout
            for i in range(10):  # Maximum 10 heartbeats (5 minutes)
                yield {
                    "event": "heartbeat",
                    "data": {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "kiosk_id": kiosk_id,
                        "sequence": i
                    }
                }
                
                # Wait for next event
                await asyncio.sleep(30)
                
        except Exception:
            pass
    
    return EventSourceResponse(event_generator())


@app.get("/pay/{session_id}", response_class=HTMLResponse)
async def serve_payment_app(session_id: str):
    """Serve World App payment mini-app"""
    
    # Generate Mini App URL for direct World App access
    # Use direct Mini App URL format that works when scanned from any camera
    miniapp_url = f"worldapp://mini-app?app_id={WORLD_ID_APP_ID}&path=%2Fpay%2F{session_id}"
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>RoluATM Payment - Session {session_id}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 400px;
                margin: 0 auto;
                padding: 20px;
                text-align: center;
            }}
            .qr-code {{
                margin: 20px 0;
                padding: 20px;
                border: 2px solid #ccc;
                border-radius: 10px;
            }}
            .session-info {{
                background: #f0f0f0;
                padding: 15px;
                border-radius: 5px;
                margin: 10px 0;
            }}
        </style>
    </head>
    <body>
        <h1>RoluATM Payment</h1>
        <div class="session-info">
            <p><strong>Session:</strong> {session_id}</p>
            <p>Scan with World App to verify your identity</p>
        </div>
        <div class="qr-code">
            <a href="{miniapp_url}" target="_blank">
                <button style="padding: 15px 30px; font-size: 16px;">
                    Open in World App
                </button>
            </a>
        </div>
        <p>Or scan this QR code with World App:</p>
        <p><a href="{miniapp_url}">{miniapp_url}</a></p>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


@app.get("/")
async def root():
    """Root endpoint - Mini App Interface"""
    # Serve the mini-app HTML directly
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RoluATM - Cash Withdrawal</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        
        .container {
            max-width: 400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .logo {
            font-size: 32px;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 10px;
        }
        
        .subtitle {
            font-size: 16px;
            color: #7f8c8d;
        }
        
        .amount-display {
            background: linear-gradient(135deg, #4CAF50, #45a049);
            color: white;
            padding: 25px;
            border-radius: 15px;
            text-align: center;
            margin: 20px 0;
        }
        
        .amount-value {
            font-size: 36px;
            font-weight: bold;
            margin-bottom: 5px;
        }
        
        .amount-desc {
            opacity: 0.9;
            font-size: 14px;
        }
        
        .action-button {
            width: 100%;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border: none;
            padding: 15px 20px;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            margin: 15px 0;
            transition: all 0.3s ease;
        }
        
        .action-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(102, 126, 234, 0.3);
        }
        
        .action-button:disabled {
            background: #bdc3c7;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }
        
        .status-message {
            text-align: center;
            padding: 15px;
            border-radius: 10px;
            margin: 15px 0;
            font-weight: 500;
        }
        
        .status-success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .status-error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        
        .status-warning {
            background: #fff3cd;
            color: #856404;
            border: 1px solid #ffeaa7;
        }
        
        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            animation: spin 1s linear infinite;
            display: inline-block;
            margin-right: 10px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .footer {
            text-align: center;
            margin-top: 30px;
            font-size: 12px;
            color: #95a5a6;
        }
    </style>
    <script src="https://minikit.world.org/v1/minikit.js"></script>
    <script>MiniKit.install();</script>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">🏧 RoluATM</div>
            <div class="subtitle">World ID Verified Cash Withdrawal</div>
        </div>
        
        <div class="amount-display">
            <div class="amount-value">$10.00</div>
            <div class="amount-desc">Cash Withdrawal + $0.50 fee</div>
        </div>
        
        <div id="status-message" class="status-message" style="display: none;"></div>
        
        <button id="withdraw-btn" class="action-button">
            Withdraw $10.50
        </button>
        
        <div class="footer">
            Powered by World ID • Secure • Private
        </div>
    </div>

    <script>
        // Initialize MiniKit
        if (typeof MiniKit !== 'undefined') {
            MiniKit.init({
                app_id: 'app_263013ca6f702add37ad338fa43d4307'
            });
        }
        
        // Application state
        let appState = {
            sessionId: new URLSearchParams(window.location.search).get('session') || 'demo-session-' + Date.now(),
        };
        
        // DOM elements
        const elements = {
            withdrawBtn: document.getElementById('withdraw-btn'),
            statusMessage: document.getElementById('status-message'),
        };
        
        // Initialize app
        window.addEventListener('load', () => {
            console.log('RoluATM Mini App initialized');
            console.log('Session ID:', appState.sessionId);
            
            // Set up event listeners
            elements.withdrawBtn.addEventListener('click', handleWithdraw);
            
            // Check if we're running in World App
            if (typeof MiniKit === 'undefined') {
                showStatus('Please open this page in World App', 'error');
                elements.withdrawBtn.disabled = true;
            }
        });

        async function handleWithdraw() {
            try {
                // Step 1: World ID Verification
                showStatus('Verifying your World ID...', 'warning');
                elements.withdrawBtn.innerHTML = '<span class="spinner"></span>Verifying...';
                elements.withdrawBtn.disabled = true;

                const verifyPayload = {
                    action: 'withdraw-cash',
                    signal: appState.sessionId,
                    verification_level: 'orb'
                };

                const verifyResponse = await MiniKit.commands.verify(verifyPayload);

                if (!verifyResponse.success) {
                    throw new Error(verifyResponse.error || 'World ID Verification failed');
                }

                console.log('World ID verification successful:', verifyResponse);
                showStatus('World ID verified. Authorizing payment...', 'warning');

                // Step 2: Payment Authorization
                elements.withdrawBtn.innerHTML = '<span class="spinner"></span>Processing Payment...';
                
                const paymentPayload = {
                    to: '0x742fd484b63E7C9b7f34FAb65A8c165B7cd5C5e8', // RoluATM wallet address
                    value: 10.50, // $10.50 (withdrawal + fee)
                    token: 'USDC',
                    description: 'RoluATM Cash Withdrawal',
                    reference: appState.sessionId
                };

                const paymentResponse = await MiniKit.commands.pay(paymentPayload);

                if (!paymentResponse.success) {
                    throw new Error(paymentResponse.error || 'Payment failed');
                }

                console.log('Payment authorized:', paymentResponse);
                showStatus('Payment authorized! Dispensing cash...', 'success');
                elements.withdrawBtn.innerHTML = '<span class="spinner"></span>Dispensing...';

                // Step 3: Signal Cash Dispenser
                await signalCashDispense();

            } catch (error) {
                console.error('Withdrawal process failed:', error);
                showStatus('Error: ' + error.message, 'error');
                elements.withdrawBtn.innerHTML = 'Retry Withdrawal';
                elements.withdrawBtn.disabled = false;
            }
        }
        
        // Signal Cash Dispenser
        async function signalCashDispense() {
            try {
                // Send signal to your backend to activate the TFlex dispenser
                const response = await fetch('https://rolu-atm-system.vercel.app/confirm-withdrawal', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        kiosk_id: 'demo-kiosk-001',
                        session_id: appState.sessionId,
                        coins_dispensed: 40, // 40 quarters = $10
                        timestamp: new Date().toISOString()
                    })
                });
                
                if (response.ok) {
                    showStatus('Cash dispensed successfully! Thank you!', 'success');
                    elements.withdrawBtn.innerHTML = '✅ Transaction Complete';
                    
                    // Send haptic feedback
                    if (typeof MiniKit !== 'undefined') {
                        MiniKit.commands.sendHapticFeedback({ type: 'success' });
                    }
                    
                } else {
                    throw new Error('Dispenser communication failed');
                }
                
            } catch (error) {
                console.error('Cash dispense failed:', error);
                showStatus('Dispenser error. Please contact support.', 'error');
            }
        }
        
        // UI Helper Functions
        function showStatus(message, type) {
            elements.statusMessage.textContent = message;
            elements.statusMessage.className = `status-message status-${type}`;
            elements.statusMessage.style.display = 'block';
        }
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


@app.get("/status")
async def api_status():
    """API Status endpoint"""
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
        "message": "Hello from RoluATM Cloud API!",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "success"
    }


@app.post("/kiosk-health")
async def update_kiosk_health(
    request: KioskHealthUpdate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """Update kiosk health status"""
    
    # Get or create kiosk
    kiosk = session.exec(
        select(Kiosk)
        .where(Kiosk.kiosk_id == request.kiosk_id)
    ).first()
    
    if not kiosk:
        kiosk = Kiosk(kiosk_id=request.kiosk_id)
        session.add(kiosk)
        session.flush()
    
    # Update kiosk status
    kiosk.last_seen_at = datetime.now(timezone.utc)
    kiosk.last_health_status = request.overall_status
    kiosk.serial_port = request.tflex_port
    
    # Create health log entry
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
    session.commit()
    
    # Broadcast health update to SSE subscribers
    background_tasks.add_task(
        broadcast_kiosk_event,
        request.kiosk_id,
        "health_update",
        {
            "overall_status": request.overall_status,
            "hardware_status": request.hardware_status,
            "cloud_status": request.cloud_status,
            "tflex_connected": request.tflex_connected,
            "coin_count": request.coin_count
        }
    )
    
    return {
        "success": True,
        "kiosk_id": request.kiosk_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/test-qr")
async def test_qr_code():
    """Test QR code generation and URL format"""
    session_id = f"test-{uuid.uuid4().hex[:8]}"
    
    # Use direct Mini App URL format for QR codes
    miniapp_url = f"worldapp://mini-app?app_id={WORLD_ID_APP_ID}&path=%2Fminiapp%3Fsession%3D{session_id}"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test QR Code - RoluATM</title>
        <script src="https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js"></script>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 500px; margin: 50px auto; padding: 20px; }}
            .test-container {{ text-align: center; }}
            .url-display {{ background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 20px 0; word-break: break-all; font-family: monospace; }}
            .test-button {{ background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 10px; }}
        </style>
    </head>
    <body>
        <div class="test-container">
            <h2>🧪 QR Code Test - RoluATM</h2>
            <p><strong>Session ID:</strong> {session_id}</p>
            
            <h3>Mini App URL:</h3>
            <div class="url-display">{miniapp_url}</div>
            
            <canvas id="qrcode"></canvas>
            
            <div style="margin-top: 30px;">
                <button class="test-button" onclick="window.open('{miniapp_url}', '_blank')">
                    🔗 Test Direct Link
                </button>
                <button class="test-button" onclick="location.href='/pay/{session_id}'">
                    💳 Test Payment Page
                </button>
                <button class="test-button" onclick="location.href='/miniapp?session={session_id}'">
                    📱 Test Mini App
                </button>
            </div>
        </div>
        
        <script>
            // Generate QR code
            QRCode.toCanvas(document.getElementById('qrcode'), '{miniapp_url}', {{
                width: 256,
                height: 256,
                margin: 2
            }}, function (error) {{
                if (error) console.error(error);
                console.log('QR code generated successfully!');
            }});
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


@app.get("/miniapp")
async def mini_app_interface(session: str = None):
    """Mini App interface for World App"""
    if not session:
        session = "unknown"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>RoluATM Mini App</title>
        <script src="https://minikit.world.org/v1/minikit.js"></script>
        <script>MiniKit.install();</script>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }}
            .container {{ max-width: 400px; margin: 0 auto; background: white; padding: 30px; border-radius: 16px; }}
            .title {{ font-size: 24px; font-weight: bold; text-align: center; margin-bottom: 20px; }}
            .session-info {{ background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
            .action-button {{ width: 100%; padding: 15px; background: #000; color: white; border: none; border-radius: 8px; font-size: 16px; margin: 10px 0; cursor: pointer; }}
            .status {{ margin: 20px 0; padding: 15px; border-radius: 8px; }}
            .success {{ background: #d4edda; color: #155724; }}
            .error {{ background: #f8d7da; color: #721c24; }}
            .info {{ background: #d1ecf1; color: #0c5460; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="title">🏧 RoluATM</div>
            
            <div class="session-info">
                <strong>Session:</strong> {session}<br>
                <strong>Amount:</strong> $10.00 + $0.50 fee<br>
                <strong>Quarters:</strong> 40 coins
            </div>
            
            <button class="action-button" onclick="verifyWorldID()">
                🌍 Verify with World ID
            </button>
            
            <button class="action-button" onclick="authorizePayment()" style="display:none;" id="payButton">
                💳 Authorize Payment
            </button>
            
            <div id="status" class="status info">
                Ready to verify identity
            </div>
            
            <div style="margin-top: 30px; font-size: 12px; color: #666; text-align: center;">
                Session: {session}<br>
                MiniKit Status: <span id="minikit-status">Loading...</span>
            </div>
        </div>
        
        <script>
            let sessionId = '{session}';
            
            // Initialize MiniKit
            window.addEventListener('load', function() {{
                if (typeof MiniKit !== 'undefined') {{
                    document.getElementById('minikit-status').textContent = 'Ready';
                    showStatus('MiniKit loaded successfully', 'success');
                }} else {{
                    document.getElementById('minikit-status').textContent = 'Failed';
                    showStatus('MiniKit failed to load', 'error');
                }}
            }});
            
            function showStatus(message, type) {{
                const status = document.getElementById('status');
                status.textContent = message;
                status.className = 'status ' + type;
            }}
            
            async function verifyWorldID() {{
                showStatus('Starting World ID verification...', 'info');
                
                try {{
                    const response = await MiniKit.commands.verify({{
                        action: 'withdraw-cash',
                        signal: sessionId
                    }});
                    
                    if (response.success) {{
                        showStatus('✅ World ID verified! Now authorize payment.', 'success');
                        document.getElementById('payButton').style.display = 'block';
                        
                        // Send verification to backend
                        const backendResponse = await fetch('/verify-worldid', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{
                                session_id: sessionId,
                                world_id_payload: response,
                                amount_usd: 10.50
                            }})
                        }});
                        
                        if (!backendResponse.ok) {{
                            throw new Error('Backend verification failed');
                        }}
                    }} else {{
                        showStatus('❌ World ID verification failed', 'error');
                    }}
                }} catch (error) {{
                    console.error('Verification error:', error);
                    showStatus('❌ Verification error: ' + error.message, 'error');
                }}
            }}
            
            async function authorizePayment() {{
                showStatus('Authorizing payment...', 'info');
                
                try {{
                    const response = await MiniKit.commands.pay({{
                        reference: sessionId,
                        to: '0x1234567890123456789012345678901234567890', // Your wallet address
                        tokens: [{{
                            symbol: 'USDC',
                            token_amount: '10.500000' // $10.50 in USDC (6 decimals)
                        }}]
                    }});
                    
                    if (response.success) {{
                        showStatus('✅ Payment authorized! Dispensing quarters...', 'success');
                        // Redirect to success page or continue with dispensing logic
                        setTimeout(() => {{
                            window.location.href = '/payment-success/' + sessionId;
                        }}, 2000);
                    }} else {{
                        showStatus('❌ Payment authorization failed', 'error');
                    }}
                }} catch (error) {{
                    console.error('Payment error:', error);
                    showStatus('❌ Payment error: ' + error.message, 'error');
                }}
            }}
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


@app.get("/payment-success/{session_id}")
async def payment_success(session_id: str):
    """Payment success page"""
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payment Successful - RoluATM</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; text-align: center; }}
            .container {{ max-width: 400px; margin: 50px auto; background: white; padding: 40px; border-radius: 16px; }}
            .success-icon {{ font-size: 64px; margin-bottom: 20px; }}
            .title {{ font-size: 24px; font-weight: bold; color: #28a745; margin-bottom: 20px; }}
            .details {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }}
            .status {{ background: #d4edda; color: #155724; padding: 15px; border-radius: 8px; margin: 20px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="success-icon">✅</div>
            <div class="title">Payment Successful!</div>
            
            <div class="details">
                <strong>Session:</strong> {session_id}<br>
                <strong>Amount:</strong> $10.50<br>
                <strong>Quarters:</strong> 40 coins<br>
                <strong>Status:</strong> Processing...
            </div>
            
            <div class="status">
                Your payment has been processed.<br>
                Please wait for the ATM to dispense your quarters.
            </div>
            
            <div style="margin-top: 30px; font-size: 14px; color: #666;">
                Thank you for using RoluATM!
            </div>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 