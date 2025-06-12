import React from 'react';
import { Play, Coins } from 'lucide-react';
import type { KioskStatus } from '../types';

interface WelcomeScreenProps {
  onStart: () => void;
  status: KioskStatus | null;
}

const WelcomeScreen: React.FC<WelcomeScreenProps> = ({ onStart, status }) => {
  const isReady = status?.overall_status === 'healthy' && 
                  status?.hardware?.tflex_connected;

  return (
    <div className="kiosk-card text-center">
      <div className="mb-8">
        <Coins className="w-16 h-16 text-primary-600 mx-auto mb-4" />
        <h1 className="text-kiosk-3xl font-bold text-gray-900 mb-2">
          Welcome to RoluATM
        </h1>
        <p className="text-xl text-gray-600">
          Get cash instantly with World ID verification
        </p>
      </div>

      <div className="space-y-4 mb-8">
        <div className="bg-gray-50 rounded-lg p-4">
          <h3 className="font-semibold text-gray-900 mb-2">How it works:</h3>
          <ol className="text-left text-gray-700 space-y-1">
            <li>1. Select your amount ($1-$100)</li>
            <li>2. Verify with World ID</li>
            <li>3. Receive quarters + $0.50 fee</li>
          </ol>
        </div>
      </div>

      {!isReady && (
        <div className="bg-warning-50 border border-warning-200 rounded-lg p-4 mb-6">
          <p className="text-warning-800">
            {status?.overall_status === 'offline' 
              ? 'Service is currently offline. Please try again later.'
              : 'System initializing... Please wait.'
            }
          </p>
        </div>
      )}

      <button
        onClick={onStart}
        disabled={!isReady}
        className="btn-primary w-full text-kiosk-xl py-6 flex items-center justify-center gap-3"
      >
        <Play className="w-6 h-6" />
        Start Transaction
      </button>

      {status && (
        <div className="mt-6 text-sm text-gray-500">
          <p>Status: {status.overall_status}</p>
          <p>Coins available: {status.hardware.coin_count || 'Unknown'}</p>
        </div>
      )}
    </div>
  );
};

export default WelcomeScreen; 