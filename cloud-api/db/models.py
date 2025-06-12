"""
Database models for RoluATM Cloud API

SQLModel models for Neon Postgres database with World ID integration.
No local database emulation - connects directly to Neon.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel, Relationship


class TransactionStatus(str, Enum):
    """Transaction status enumeration"""
    PENDING = "pending"
    VERIFIED = "verified"
    DISPENSING = "dispensing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class User(SQLModel, table=True):
    """
    User model with World ID integration
    Stores nullifier hash for uniqueness, no credentials
    """
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    world_id_nullifier: str = Field(unique=True, index=True)
    verification_level: str = Field(default="orb")  # orb, device, etc.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Statistics
    total_transactions: int = Field(default=0)
    total_amount_usd: float = Field(default=0.0)
    last_transaction_at: Optional[datetime] = None
    
    # Relationships
    transactions: list["Transaction"] = Relationship(back_populates="user")


class Kiosk(SQLModel, table=True):
    """
    Kiosk registration and status tracking
    """
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
    """
    Transaction record with full audit trail
    """
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
    """
    Kiosk health monitoring logs
    """
    __tablename__ = "kiosk_health_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    kiosk_id: str = Field(index=True)
    
    # Status information
    overall_status: str  # healthy, degraded, offline
    hardware_status: str  # tflex status
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
    """
    World ID verification attempts and results
    """
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


# Database initialization
def create_db_and_tables(engine):
    """Create all database tables"""
    SQLModel.metadata.create_all(engine) 