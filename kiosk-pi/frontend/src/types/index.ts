export interface KioskStatus {
  kiosk_id: string;
  timestamp: string;
  hardware: {
    tflex_connected: boolean;
    port: string;
    status: string;
    coin_count?: number;
  };
  cloud: {
    api_url: string;
    online: boolean;
    last_check: string | null;
  };
  overall_status: 'healthy' | 'degraded' | 'offline';
}

export interface WithdrawRequest {
  amount_usd: number;
  session_id: string;
}

export interface WithdrawResponse {
  success: boolean;
  coins_dispensed: number;
  amount_usd: number;
  timestamp: string;
}

export interface BalanceResponse {
  kiosk_id: string;
  timestamp: string;
  status: string;
  coin_count: number;
  available: boolean;
  quarter_value_usd: number;
}

export interface WorldIDPayload {
  merkle_root: string;
  nullifier_hash: string;
  proof: string;
  verification_level: string;
}

export interface TransactionSession {
  session_id: string;
  amount_usd: number;
  world_id_verified: boolean;
  created_at: string;
  expires_at: string;
  status: 'pending' | 'verified' | 'dispensing' | 'completed' | 'failed' | 'expired';
}

export interface AmountOption {
  value: number;
  label: string;
  quarters: number;
}

export interface ApiError {
  error: string;
  message: string;
  type: 'hardware' | 'cloud' | 'offline' | 'validation';
}

export type AppState = 
  | 'welcome'
  | 'amount-select'
  | 'world-id-verify'
  | 'processing'
  | 'dispensing'
  | 'complete'
  | 'error'
  | 'offline';

export interface AppContext {
  state: AppState;
  session: TransactionSession | null;
  status: KioskStatus | null;
  error: string | null;
} 