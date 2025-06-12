import { useState, useEffect, useCallback } from 'react';
import { QRCodeGenerator } from '@worldcoin/minikit-js';
import { Coins, Wifi, WifiOff, AlertTriangle, CheckCircle } from 'lucide-react';
import { api, ApiError } from './lib/api';
import type { 
  AppState, 
  KioskStatus, 
  TransactionSession, 
  AmountOption,
  WorldIDPayload 
} from './types';
import WelcomeScreen from './components/WelcomeScreen';
import AmountSelector from './components/AmountSelector';
import WorldIDVerification from './components/WorldIDVerification';
import ProcessingScreen from './components/ProcessingScreen';
import DispensingScreen from './components/DispensingScreen';
import CompleteScreen from './components/CompleteScreen';
import ErrorScreen from './components/ErrorScreen';
import OfflineScreen from './components/OfflineScreen';

const AMOUNT_OPTIONS: AmountOption[] = [
  { value: 1, label: '$1.00', quarters: 4 },
  { value: 5, label: '$5.00', quarters: 20 },
  { value: 10, label: '$10.00', quarters: 40 },
  { value: 20, label: '$20.00', quarters: 80 },
  { value: 50, label: '$50.00', quarters: 200 },
  { value: 100, label: '$100.00', quarters: 400 },
];

function App() {
  const [state, setState] = useState<AppState>('welcome');
  const [status, setStatus] = useState<KioskStatus | null>(null);
  const [session, setSession] = useState<TransactionSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedAmount, setSelectedAmount] = useState<number>(0);

  // Health check and status monitoring
  const checkHealth = useCallback(async () => {
    try {
      const healthStatus = await api.getHealth();
      setStatus(healthStatus);
      
      // If we were offline and now we're back online, reset to welcome
      if (state === 'offline' && healthStatus.overall_status !== 'offline') {
        setState('welcome');
        setError(null);
      }
      
      // If we're healthy but in error state, reset
      if (state === 'error' && healthStatus.overall_status === 'healthy') {
        setState('welcome');
        setError(null);
      }
      
    } catch (err) {
      if (err instanceof ApiError && err.isOffline) {
        setState('offline');
        setError('Service is currently offline. Please try again later.');
      } else {
        console.error('Health check failed:', err);
        setStatus(null);
      }
    }
  }, [state]);

  // Periodic health monitoring
  useEffect(() => {
    // Initial check
    checkHealth();
    
    // Set up periodic monitoring
    const interval = setInterval(checkHealth, 5000);
    
    return () => clearInterval(interval);
  }, [checkHealth]);

  // Handle amount selection
  const handleAmountSelect = (amount: number) => {
    setSelectedAmount(amount);
    
    // Create transaction session
    const newSession: TransactionSession = {
      session_id: `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      amount_usd: amount,
      world_id_verified: false,
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(), // 10 minutes
      status: 'pending'
    };
    
    setSession(newSession);
    setState('world-id-verify');
  };

  // Handle World ID verification
  const handleWorldIDVerification = async (payload: WorldIDPayload) => {
    if (!session) return;

    setState('processing');
    
    try {
      // Verify with cloud API
      const response = await fetch(`${import.meta.env.VITE_CLOUD_API_URL}/verify-worldid`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: session.session_id,
          world_id_payload: payload,
          amount_usd: session.amount_usd
        })
      });

      if (!response.ok) {
        throw new Error('World ID verification failed');
      }

      // Update session
      const updatedSession = {
        ...session,
        world_id_verified: true,
        status: 'verified' as const
      };
      setSession(updatedSession);

      // Proceed to withdrawal
      await handleWithdrawal(updatedSession);

    } catch (err) {
      console.error('World ID verification failed:', err);
      setError(err instanceof Error ? err.message : 'Verification failed');
      setState('error');
    }
  };

  // Handle coin withdrawal
  const handleWithdrawal = async (verifiedSession: TransactionSession) => {
    try {
      setState('dispensing');
      
      const response = await api.withdraw({
        amount_usd: verifiedSession.amount_usd,
        session_id: verifiedSession.session_id
      });

      if (response.success) {
        const completedSession = {
          ...verifiedSession,
          status: 'completed' as const
        };
        setSession(completedSession);
        setState('complete');

        // Auto-reset to welcome after 10 seconds
        setTimeout(() => {
          setState('welcome');
          setSession(null);
          setSelectedAmount(0);
          setError(null);
        }, 10000);
      } else {
        throw new Error('Coin dispensing failed');
      }

    } catch (err) {
      console.error('Withdrawal failed:', err);
      if (err instanceof ApiError) {
        if (err.isOffline) {
          setState('offline');
          setError('Service is currently offline. Please try again later.');
        } else if (err.isHardwareError) {
          setError('Hardware error: ' + err.message);
          setState('error');
        } else {
          setError('Service error: ' + err.message);
          setState('error');
        }
      } else {
        setError(err instanceof Error ? err.message : 'Unknown error');
        setState('error');
      }
    }
  };

  // Handle reset/cancel
  const handleReset = () => {
    setState('welcome');
    setSession(null);
    setSelectedAmount(0);
    setError(null);
  };

  // Status indicator component
  const StatusIndicator = () => {
    if (!status) return null;

    const getStatusIcon = () => {
      switch (status.overall_status) {
        case 'healthy':
          return <Wifi className="w-5 h-5 text-success-600" />;
        case 'degraded':
          return <AlertTriangle className="w-5 h-5 text-warning-600" />;
        case 'offline':
          return <WifiOff className="w-5 h-5 text-error-600" />;
        default:
          return <WifiOff className="w-5 h-5 text-gray-400" />;
      }
    };

    return (
      <div className="absolute top-4 right-4 flex items-center gap-2 text-sm">
        {getStatusIcon()}
        <span className={`font-medium ${
          status.overall_status === 'healthy' ? 'text-success-600' :
          status.overall_status === 'degraded' ? 'text-warning-600' :
          'text-error-600'
        }`}>
          {status.overall_status}
        </span>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex flex-col">
      <StatusIndicator />
      
      {/* Header */}
      <header className="flex items-center justify-center py-6 bg-white shadow-sm">
        <div className="flex items-center gap-3">
          <Coins className="w-8 h-8 text-primary-600" />
          <h1 className="text-kiosk-2xl font-bold text-gray-900">RoluATM</h1>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-2xl">
          {state === 'welcome' && (
            <WelcomeScreen 
              onStart={() => setState('amount-select')} 
              status={status}
            />
          )}
          
          {state === 'amount-select' && (
            <AmountSelector
              options={AMOUNT_OPTIONS}
              selectedAmount={selectedAmount}
              onSelect={handleAmountSelect}
              onCancel={handleReset}
            />
          )}
          
          {state === 'world-id-verify' && session && (
            <WorldIDVerification
              session={session}
              onVerified={handleWorldIDVerification}
              onCancel={handleReset}
            />
          )}
          
          {state === 'processing' && (
            <ProcessingScreen message="Verifying your identity..." />
          )}
          
          {state === 'dispensing' && session && (
            <DispensingScreen 
              amount={session.amount_usd}
              quarters={session.amount_usd * 4}
            />
          )}
          
          {state === 'complete' && session && (
            <CompleteScreen 
              amount={session.amount_usd}
              quarters={session.amount_usd * 4}
              onContinue={handleReset}
            />
          )}
          
          {state === 'error' && (
            <ErrorScreen 
              error={error || 'An unknown error occurred'}
              onRetry={handleReset}
            />
          )}
          
          {state === 'offline' && (
            <OfflineScreen 
              onRetry={checkHealth}
            />
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="py-4 text-center text-gray-500 text-sm">
        <p>RoluATM v1.0.0 • World ID Required • $0.50 Transaction Fee</p>
      </footer>
    </div>
  );
}

export default App; 