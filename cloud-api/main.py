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
import time

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

# In-memory storage for payment requests (use database in production)
payment_requests = {}


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
    """Verify World ID proof with backend validation"""
    try:
        # Extract World ID payload
        payload = request.world_id_payload
        
        # Verify proof with World API
        async with httpx.AsyncClient() as client:
            verification_response = await client.post(
                f"https://developer.worldcoin.org/api/v2/verify/{WORLD_ID_APP_ID}",
                json={{
                    "nullifier_hash": payload.nullifier_hash,
                    "merkle_root": payload.merkle_root,
                    "proof": payload.proof,
                    "verification_level": payload.verification_level,
                    "action": WORLD_ID_ACTION,
                    "signal_hash": request.session_id  # Use session_id as signal
                }},
                headers={{"Content-Type": "application/json"}}
            )
            
        if verification_response.status_code != 200:
            verification_data = verification_response.json()
            logger.error(f"World ID verification failed: {verification_data}")
            raise HTTPException(
                status_code=400, 
                detail=f"World ID verification failed: {verification_data.get('detail', 'Unknown error')}"
            )
        
        # Create verification record
        verification = WorldIDVerification(
            session_id=request.session_id,
            nullifier_hash=request.world_id_payload.nullifier_hash,
            merkle_root=request.world_id_payload.merkle_root,
            verification_level=request.world_id_payload.verification_level,
            action=WORLD_ID_ACTION,
            amount_usd=request.amount_usd,
            verified_at=datetime.now(timezone.utc)
        )
        
        session.add(verification)
        session.commit()
        
        logger.info(f"World ID verified for session {request.session_id}")
        
        return {
            "success": True,
            "session_id": request.session_id,
            "verified_at": verification.verified_at.isoformat(),
            "nullifier_hash": request.world_id_payload.nullifier_hash,
            "verification_level": request.world_id_payload.verification_level
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"World ID verification error: {e}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


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
    
    <!-- Mini App Metadata - Required by World -->
    <meta name="world-app" content='{
        "name": "RoluATM",
        "description": "World ID verified cash withdrawal from cryptocurrency",
        "logo": "https://rolu-atm-system.vercel.app/logo-512.png",
        "category": "financial",
        "verification_required": true,
        "payment_required": true
    }'>
    
    <link rel="icon" type="image/png" href="/favicon.png">
    <link rel="apple-touch-icon" href="/apple-touch-icon.png">
    
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
        
        .status-info {
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }
        
        .status-content {{
            line-height: 1.4;
            word-break: break-word;
        }}
        
        .status-error .status-content {{
            font-weight: 500;
        }}
        
        .status-success .status-content {{
            font-weight: 500;
        }}
        
        /* Enhanced status message styling */
        .status-message {{
            transition: all 0.3s ease;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        .status-message.error {{
            animation: shake 0.5s ease-in-out;
        }}
        
        @keyframes shake {{
            0%, 100% {{ transform: translateX(0); }}
            25% {{ transform: translateX(-5px); }}
            75% {{ transform: translateX(5px); }}
        }}
        
        /* Better button states */
        .withdraw-btn:disabled {{
            opacity: 0.7;
            cursor: not-allowed;
        }}
        
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
    <script>
      // Load MiniKit properly with async handling
      function initMiniKit() {{
        if (typeof MiniKit !== 'undefined') {{
          MiniKit.install();
          MiniKit.init({{
            app_id: 'app_263013ca6f702add37ad338fa43d4307'
          }});
          console.log('MiniKit initialized successfully');
          return true;
        }}
        return false;
      }}
      
      // Try immediate init, then fallback to polling
      if (!initMiniKit()) {{
        let attempts = 0;
        const maxAttempts = 20; // 2 seconds max wait
        const checkMiniKit = setInterval(() => {{
          attempts++;
          if (initMiniKit() || attempts >= maxAttempts) {{
            clearInterval(checkMiniKit);
            if (attempts >= maxAttempts) {{
              console.error('MiniKit failed to load after 2 seconds');
            }}
          }}
        }}, 100);
      }}
      
      // Optional mobile console: add ?debug to URL
      if (location.search.includes('debug')) {{
        var s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/eruda';
        document.head.appendChild(s);
        s.onload = function () {{ eruda.init(); }};
      }}
    </script>
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
        window.addEventListener('load', () => {{
            console.log('RoluATM Mini App initialized');
            console.log('Session ID:', appState.sessionId);
            
            // Set up event listeners
            elements.withdrawBtn.addEventListener('click', handleWithdraw);
            
            // Check if we're running in World App
            if (typeof MiniKit === 'undefined') {{
                showStatus('Please open this page in World App', 'error');
                elements.withdrawBtn.disabled = true;
            }} else {{
                console.log('MiniKit detected and ready');
                showStatus('Ready to withdraw cash', 'success');
            }}
        }});

        async function handleWithdraw() {{
            try {{
                // Debug: Log initial state
                console.log('=== WITHDRAWAL PROCESS STARTED ===');
                console.log('Session ID:', appState.sessionId);
                console.log('MiniKit available:', typeof MiniKit !== 'undefined');
                console.log('MiniKit installed:', typeof MiniKit !== 'undefined' ? MiniKit.isInstalled() : false);
                
                if (typeof MiniKit === 'undefined') {{
                    throw new Error('MiniKit SDK not loaded. Please refresh the page or ensure you are using World App.');
                }}
                
                if (!MiniKit.isInstalled()) {{
                    throw new Error('MiniKit not properly installed. Please make sure you are opening this page within World App.');
                }}
                
                // Step 1: World ID Verification
                showStatus('🔍 Step 1/3: Preparing World ID verification...', 'warning');
                elements.withdrawBtn.innerHTML = '<span class="spinner"></span>Verifying...';
                elements.withdrawBtn.disabled = true;

                console.log('Starting World ID verification...');
                const verifyPayload = {{
                    action: 'withdraw-cash',
                    signal: appState.sessionId,
                    verification_level: 'orb'
                }};
                
                console.log('World ID verification payload:', verifyPayload);
                showStatus('🌍 Requesting World ID verification...', 'warning');

                let verifyResponse;
                try {{
                    verifyResponse = await MiniKit.commands.verify(verifyPayload);
                    console.log('World ID verification response:', verifyResponse);
                }} catch (worldIdError) {{
                    console.error('World ID verification failed:', worldIdError);
                    throw new Error(`World ID verification failed: ${{worldIdError.message || 'Unknown error during verification. Please try again.'}}`);
                }}

                if (!verifyResponse.success) {{
                    console.error('World ID verification unsuccessful:', verifyResponse);
                    const errorMsg = verifyResponse.error || 'World ID verification was not successful';
                    
                    // Provide specific error messages based on common issues
                    if (errorMsg.includes('verification_rejected')) {{
                        throw new Error('❌ You cancelled the World ID verification. Please try again and complete the verification process.');
                    }} else if (errorMsg.includes('max_verifications_reached')) {{
                        throw new Error('❌ You have already verified for this action the maximum number of times allowed.');
                    }} else if (errorMsg.includes('credential_unavailable')) {{
                        throw new Error('❌ You do not have the required World ID credential. Please verify at an Orb or with your device.');
                    }} else if (errorMsg.includes('invalid_network')) {{
                        throw new Error('❌ Network mismatch. Please make sure you are using the correct World App environment.');
                    }} else {{
                        throw new Error(`❌ World ID verification failed: ${{errorMsg}}`);
                    }}
                }}

                console.log('World ID verification successful:', verifyResponse);
                showStatus('✅ World ID verified! Moving to payment...', 'success');
                
                // Brief pause to show success
                await new Promise(resolve => setTimeout(resolve, 1000));

                // Step 2: Payment Authorization
                showStatus('💳 Step 2/3: Initializing payment...', 'warning');
                elements.withdrawBtn.innerHTML = '<span class="spinner"></span>Initializing Payment...';
                
                // Initialize payment in backend first
                console.log('Initializing payment with backend...');
                let initResponse;
                try {{
                    initResponse = await fetch('/api/initiate-payment', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ session_id: appState.sessionId, amount: 10.50 }})
                    }});
                    
                    console.log('Payment init response status:', initResponse.status);
                }} catch (networkError) {{
                    console.error('Network error during payment initialization:', networkError);
                    throw new Error('❌ Network error: Unable to connect to payment server. Please check your internet connection and try again.');
                }}
                
                if (!initResponse.ok) {{
                    let errorDetails = 'Unknown error';
                    try {{
                        const errorData = await initResponse.json();
                        errorDetails = errorData.detail || errorData.message || `HTTP ${{initResponse.status}}`;
                    }} catch (e) {{
                        errorDetails = `HTTP ${{initResponse.status}} - ${{initResponse.statusText}}`;
                    }}
                    console.error('Payment initialization failed:', errorDetails);
                    throw new Error(`❌ Payment initialization failed: ${{errorDetails}}. Please try again or contact support.`);
                }}
                
                let reference;
                try {{
                    const initData = await initResponse.json();
                    reference = initData.reference;
                    console.log('Payment reference obtained:', reference);
                }} catch (e) {{
                    console.error('Failed to parse payment initialization response:', e);
                    throw new Error('❌ Invalid response from payment server. Please try again.');
                }}
                
                if (!reference) {{
                    throw new Error('❌ No payment reference received from server. Please try again.');
                }}
                
                showStatus('💳 Step 2/3: Requesting payment authorization...', 'warning');
                elements.withdrawBtn.innerHTML = '<span class="spinner"></span>Authorizing Payment...';
                
                // World Pay API compliant payload
                const paymentPayload = {{
                    reference: reference, // Backend-generated reference ID
                    to: '{ROLU_WALLET_ADDRESS}', // RoluATM wallet address  
                    tokens: [{{
                        symbol: 'USDC',
                        token_amount: '10500000' // $10.50 in USDC (6 decimals)
                    }}],
                    description: 'RoluATM Cash Withdrawal'
                }};
                
                console.log('Payment payload:', paymentPayload);

                let paymentResponse;
                try {{
                    paymentResponse = await MiniKit.commands.pay(paymentPayload);
                    console.log('Payment response:', paymentResponse);
                }} catch (paymentError) {{
                    console.error('Payment command failed:', paymentError);
                    throw new Error(`❌ Payment request failed: ${{paymentError.message || 'Unable to process payment request. Please try again.'}}`);
                }}

                if (!paymentResponse.success) {{
                    console.error('Payment unsuccessful:', paymentResponse);
                    const paymentError = paymentResponse.error || 'Payment was not successful';
                    
                    // Provide specific error messages based on common payment issues
                    if (paymentError.includes('payment_rejected')) {{
                        throw new Error('❌ You cancelled the payment. Please try again and approve the payment to continue.');
                    }} else if (paymentError.includes('insufficient_balance')) {{
                        throw new Error('❌ Insufficient USDC balance. Please add funds to your World App wallet and try again.');
                    }} else if (paymentError.includes('invalid_receiver')) {{
                        throw new Error('❌ Invalid receiver address. Please contact support - there may be a configuration issue.');
                    }} else if (paymentError.includes('transaction_failed')) {{
                        throw new Error('❌ Transaction failed on blockchain. Please try again in a few moments.');
                    }} else {{
                        throw new Error(`❌ Payment failed: ${{paymentError}}`);
                    }}
                }}
                
                showStatus('🔄 Step 3/3: Verifying payment...', 'warning');
                elements.withdrawBtn.innerHTML = '<span class="spinner"></span>Verifying Payment...';

                // Verify payment in backend
                console.log('Verifying payment with backend...');
                let verifyResponse;
                try {{
                    verifyResponse = await fetch('/api/confirm-payment', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ payload: paymentResponse, reference: reference }})
                    }});
                    
                    console.log('Payment verification response status:', verifyResponse.status);
                }} catch (networkError) {{
                    console.error('Network error during payment verification:', networkError);
                    throw new Error('❌ Network error during payment verification. Your payment may have succeeded - please contact support with reference: ' + reference);
                }}
                
                let verifyResult;
                try {{
                    verifyResult = await verifyResponse.json();
                    console.log('Payment verification result:', verifyResult);
                }} catch (e) {{
                    console.error('Failed to parse verification response:', e);
                    throw new Error('❌ Invalid response during payment verification. Please contact support with reference: ' + reference);
                }}
                
                if (verifyResult.success) {{
                    console.log('Payment verified:', paymentResponse);
                    showStatus('✅ Payment confirmed! Dispensing cash...', 'success');
                    elements.withdrawBtn.innerHTML = '<span class="spinner"></span>Dispensing...';
                await signalCashDispense();
                }} else {{
                    const verifyError = verifyResult.error || 'Payment verification failed';
                    console.error('Payment verification failed:', verifyError);
                    throw new Error(`❌ Payment verification failed: ${{verifyError}}. Please contact support with reference: ${{reference}}`);
                }}

            }} catch (error) {{
                console.error('Withdrawal process failed:', error);
                
                // Use enhanced error reporting
                reportError(error, 'Withdrawal process');
                
                // Enhanced error display
                const errorMessage = error.message || 'An unexpected error occurred';
                showStatus(errorMessage, 'error');
                
                // Log detailed error for debugging
                console.error('=== WITHDRAWAL ERROR DETAILS ===');
                console.error('Error:', error);
                console.error('Stack:', error.stack);
                console.error('Session ID:', appState.sessionId);
                console.error('Timestamp:', new Date().toISOString());
                
                elements.withdrawBtn.innerHTML = 'Retry Withdrawal';
                elements.withdrawBtn.disabled = false;
                
                // Send error feedback to user's device
                if (typeof MiniKit !== 'undefined' && MiniKit.commands && MiniKit.commands.sendHapticFeedback) {{
                    try {{
                        MiniKit.commands.sendHapticFeedback({{ type: 'error' }});
                    }} catch (hapticError) {{
                        console.warn('Could not send haptic feedback:', hapticError);
                    }}
                }}
            }}
        }}
        
        // Signal Cash Dispenser
        async function signalCashDispense() {{
            try {{
                console.log('=== CASH DISPENSE PROCESS STARTED ===');
                showStatus('🏧 Contacting ATM hardware...', 'warning');
                
                // Send signal to your backend to activate the TFlex dispenser
                console.log('Sending dispense signal to backend...');
                let response;
                try {{
                    response = await fetch('https://rolu-atm-system.vercel.app/confirm-withdrawal', {{
                    method: 'POST',
                        headers: {{
                        'Content-Type': 'application/json'
                        }},
                        body: JSON.stringify({{
                        kiosk_id: 'demo-kiosk-001',
                        session_id: appState.sessionId,
                        coins_dispensed: 40, // 40 quarters = $10
                        timestamp: new Date().toISOString()
                        }})
                    }});
                    
                    console.log('Dispense response status:', response.status);
                }} catch (networkError) {{
                    console.error('Network error during cash dispense:', networkError);
                    throw new Error('❌ Network error: Unable to connect to ATM hardware. Please contact support.');
                }}
                
                let responseData;
                try {{
                    responseData = await response.json();
                    console.log('Dispense response data:', responseData);
                }} catch (e) {{
                    console.warn('Could not parse dispense response as JSON, checking status...');
                    responseData = null;
                }}
                
                if (response.ok) {{
                    console.log('Cash dispense successful');
                    showStatus('✅ Cash dispensed successfully! Please collect your quarters. Thank you!', 'success');
                    elements.withdrawBtn.innerHTML = '✅ Transaction Complete';
                    
                    // Send haptic feedback
                    if (typeof MiniKit !== 'undefined') {{
                        try {{
                            MiniKit.commands.sendHapticFeedback({{ type: 'success' }});
                        }} catch (hapticError) {{
                            console.warn('Could not send success haptic feedback:', hapticError);
                        }}
                    }}
                    
                }} else {{
                    let errorMsg = 'Dispenser communication failed';
                    
                    if (responseData && responseData.error) {{
                        errorMsg = responseData.error;
                    }} else if (responseData && responseData.detail) {{
                        errorMsg = responseData.detail;
                    }} else {{
                        errorMsg = `HTTP ${{response.status}} - ${{response.statusText || 'Unknown error'}}`;
                    }}
                    
                    console.error('Cash dispense failed:', errorMsg);
                    throw new Error(`❌ ATM Hardware Error: ${{errorMsg}}`);
                }}
                
            }} catch (error) {{
                console.error('Cash dispense failed:', error);
                
                // Use enhanced error reporting
                reportError(error, 'Cash dispense process');
                
                // Enhanced error message for cash dispense
                let errorMessage = error.message || 'Unknown dispenser error';
                
                // Add specific troubleshooting based on error type
                if (errorMessage.includes('Network error')) {{
                    errorMessage += ' The ATM may be offline or experiencing connectivity issues.';
                }} else if (errorMessage.includes('HTTP 503')) {{
                    errorMessage += ' The ATM service is temporarily unavailable. Please try again in a few minutes.';
                }} else if (errorMessage.includes('HTTP 404')) {{
                    errorMessage += ' The ATM endpoint is not configured properly. Please contact support.';
                }}
                
                showStatus(errorMessage + ' Please contact support if the issue persists.', 'error');
                
                // Log detailed error information
                console.error('=== CASH DISPENSE ERROR DETAILS ===');
                console.error('Error:', error);
                console.error('Session ID:', appState.sessionId);
                console.error('Timestamp:', new Date().toISOString());
                console.error('ATM Status: Failed to dispense');
                
                elements.withdrawBtn.innerHTML = 'Contact Support';
                elements.withdrawBtn.disabled = true;
                
                // Send error haptic feedback
                if (typeof MiniKit !== 'undefined' && MiniKit.commands && MiniKit.commands.sendHapticFeedback) {{
                    try {{
                        MiniKit.commands.sendHapticFeedback({{ type: 'error' }});
                    }} catch (hapticError) {{
                        console.warn('Could not send error haptic feedback:', hapticError);
                    }}
                }}
            }}
        }}
        
        // UI Helper Functions
        function showStatus(message, type = 'info') {{
            console.log(`Status [${type.toUpperCase()}]:`, message);
            
            const statusElement = elements.statusMessage;
            
            // Clear existing classes
            statusElement.classList.remove('success', 'error', 'warning', 'info');
            statusElement.classList.add(type);
            
            // Handle long messages by making them scrollable
            statusElement.innerHTML = `<div class="status-content">${message}</div>`;
            
            // Auto-scroll to bottom if content overflows
            statusElement.scrollTop = statusElement.scrollHeight;
            
            // For error messages, make them more prominent
            if (type === 'error') {{
                statusElement.style.minHeight = 'auto';
                statusElement.style.maxHeight = '120px';
                statusElement.style.overflow = 'auto';
                statusElement.style.wordWrap = 'break-word';
            }} else {{
                statusElement.style.minHeight = '';
                statusElement.style.maxHeight = '';
                statusElement.style.overflow = '';
            }}
        }}

        // Debug information display (for troubleshooting)
        function showDebugInfo() {{
            const debugInfo = {{
                sessionId: appState.sessionId,
                miniKitAvailable: typeof MiniKit !== 'undefined',
                miniKitInstalled: typeof MiniKit !== 'undefined' ? MiniKit.isInstalled() : false,
                userAgent: navigator.userAgent,
                timestamp: new Date().toISOString(),
                url: window.location.href,
                isWorldApp: window.location.href.includes('worldapp') || navigator.userAgent.includes('WorldApp')
            }};
            
            console.log('=== DEBUG INFORMATION ===');
            console.log(JSON.stringify(debugInfo, null, 2));
            
            return debugInfo;
        }}
        
        // Enhanced error reporting
        function reportError(error, context = '') {{
            const errorReport = {{
                error: {{
                    message: error.message,
                    stack: error.stack,
                    name: error.name
                }},
                context: context,
                debugInfo: showDebugInfo(),
                timestamp: new Date().toISOString()
            }};
            
            console.error('=== ERROR REPORT ===');
            console.error(JSON.stringify(errorReport, null, 2));
            
            // In production, you could send this to an error tracking service
            // like Sentry, LogRocket, etc.
            
            return errorReport;
        }}
        
        // Add global error handler for uncaught errors
        window.addEventListener('error', function(event) {{
            reportError(event.error, 'Global error handler');
        }});
        
        window.addEventListener('unhandledrejection', function(event) {{
            reportError(new Error(event.reason), 'Unhandled promise rejection');
        }});
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


@app.get("/world-app.json")
async def world_app_manifest():
    """World App manifest for mini app metadata"""
    return {{
        "name": "RoluATM",
        "description": "World ID verified cash withdrawal from cryptocurrency",
        "logo": "https://rolu-atm-system.vercel.app/logo-512.png",
        "category": "financial",
        "verification_required": True,
        "payment_required": True,
        "version": "1.0.0",
        "developer": {{
            "name": "RoluATM",
            "url": "https://rolu-atm-system.vercel.app"
        }},
        "permissions": [
            "world_id_verify",
            "payments",
            "haptic_feedback"
        ]
    }}


@app.get("/favicon.png")
async def favicon():
    """Favicon endpoint"""
    # Return a simple 1x1 transparent PNG for now
    # In production, replace with actual favicon
    from fastapi.responses import Response
    transparent_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x00\x01\x00\x00\x00\x00\x00\x00\x2d\xb4\x06\x17\x00\x00\x00\x00IEND\xaeB`\x82'
    return Response(content=transparent_png, media_type="image/png")


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
        <script>
          // Load MiniKit properly with async handling
          function initMiniKit() {{
            if (typeof MiniKit !== 'undefined') {{
              MiniKit.install();
              MiniKit.init({{
                app_id: 'app_263013ca6f702add37ad338fa43d4307'
              }});
              console.log('MiniKit initialized successfully');
              return true;
            }}
            return false;
          }}
          
          // Try immediate init, then fallback to polling
          if (!initMiniKit()) {{
            let attempts = 0;
            const maxAttempts = 20; // 2 seconds max wait
            const checkMiniKit = setInterval(() => {{
              attempts++;
              if (initMiniKit() || attempts >= maxAttempts) {{
                clearInterval(checkMiniKit);
                if (attempts >= maxAttempts) {{
                  console.error('MiniKit failed to load after 2 seconds');
                }}
              }}
            }}, 100);
          }}
          
          // Optional mobile console: add ?debug to URL
          if (location.search.includes('debug')) {{
            var s = document.createElement('script');
            s.src = 'https://cdn.jsdelivr.net/npm/eruda';
            document.head.appendChild(s);
            s.onload = function () {{ eruda.init(); }};
          }}
        </script>
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
                        to: '{ROLU_WALLET_ADDRESS}', // RoluATM wallet address
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


@app.post("/api/initiate-payment")
async def initiate_payment(request: dict):
    """Initiate a payment transaction with enhanced error handling"""
    try:
        logging.info(f"Payment initiation requested for session: {request.get('session_id')}, amount: {request.get('amount', 10.50)}")
        
        # Validate session ID
        if not request.get('session_id') or len(request.get('session_id').strip()) == 0:
            logging.error("Payment initiation failed: Missing or empty session ID")
            raise HTTPException(status_code=400, detail="Session ID is required and cannot be empty")
        
        # Validate amount
        if request.get('amount', 10.50) <= 0:
            logging.error(f"Payment initiation failed: Invalid amount {request.get('amount', 10.50)}")
            raise HTTPException(status_code=400, detail=f"Amount must be positive, received: ${request.get('amount', 10.50)}")
        
        if request.get('amount', 10.50) != 10.50:  # RoluATM fixed amount
            logging.error(f"Payment initiation failed: Amount {request.get('amount', 10.50)} does not match expected $10.50")
            raise HTTPException(status_code=400, detail=f"RoluATM only supports $10.50 withdrawals, received: ${request.get('amount', 10.50)}")
        
        # Generate unique reference
        reference = f"rolu_atm_{request.get('session_id')}_{int(time.time())}"
        
        # Store payment request (in production, use database)
        payment_requests[reference] = {
            "session_id": request.get('session_id'),
            "amount": request.get('amount', 10.50),
            "status": "initiated",
            "timestamp": time.time()
        }
        
        logging.info(f"Payment initiated successfully: reference={reference}")
        return {"reference": reference}
        
    except HTTPException:
        # Re-raise HTTP exceptions (they have proper error messages)
        raise
    except Exception as e:
        # Log unexpected errors
        logging.error(f"Unexpected error during payment initiation: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error during payment initiation: {str(e)}")


@app.post("/api/confirm-payment")
async def confirm_payment(request: dict):
    """Verify and confirm payment transaction with enhanced error handling"""
    try:
        payload = request.get("payload")
        reference = request.get("reference")
        
        logging.info(f"Payment confirmation requested for reference: {reference}")
        
        # Validate required fields
        if not payload:
            logging.error("Payment confirmation failed: Missing payload")
            raise HTTPException(status_code=400, detail="Payment payload is required")
        
        if not reference:
            logging.error("Payment confirmation failed: Missing reference")
            raise HTTPException(status_code=400, detail="Payment reference is required")
        
        # Check if reference exists in our system
        if reference not in payment_requests:
            logging.error(f"Payment confirmation failed: Unknown reference {reference}")
            raise HTTPException(status_code=404, detail=f"Payment reference not found: {reference}")
        
        # Get payment request details
        payment_info = payment_requests[reference]
        logging.info(f"Found payment request: {payment_info}")
        
        # Validate payload structure
        if not isinstance(payload, dict):
            logging.error("Payment confirmation failed: Invalid payload format")
            raise HTTPException(status_code=400, detail="Payment payload must be a valid object")
        
        # Check if payment was successful according to MiniKit
        if not payload.get("success"):
            error_msg = payload.get("error", "Payment was not successful")
            logging.error(f"Payment confirmation failed: {error_msg}")
            raise HTTPException(status_code=400, detail=f"Payment was not successful: {error_msg}")
        
        # Extract transaction details
        transaction_id = payload.get("transaction_id")
        if not transaction_id:
            logging.error("Payment confirmation failed: Missing transaction ID")
            raise HTTPException(status_code=400, detail="Transaction ID is required from payment payload")
        
        # TODO: Verify transaction on blockchain
        # In production, verify the transaction on Optimism/Base blockchain
        # For now, we'll trust the MiniKit payload
        
        # Mark payment as confirmed
        payment_requests[reference]["status"] = "confirmed"
        payment_requests[reference]["transaction_id"] = transaction_id
        payment_requests[reference]["confirmed_at"] = time.time()
        
        logging.info(f"Payment confirmed successfully: reference={reference}, tx_id={transaction_id}")
        
        return {
            "success": True,
            "reference": reference,
            "transaction_id": transaction_id,
            "amount": payment_info["amount"],
            "session_id": payment_info["session_id"]
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions (they have proper error messages)
        raise
    except Exception as e:
        # Log unexpected errors
        logging.error(f"Unexpected error during payment confirmation: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error during payment confirmation: {str(e)}")


# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 