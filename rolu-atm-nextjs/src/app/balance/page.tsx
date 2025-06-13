'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { BalanceDisplay } from '@/components/BalanceDisplay';
import { WithdrawalForm } from '@/components/WithdrawalForm';

interface User {
  id: string;
  verification_level?: string;
  nullifier_hash?: string;
  wallet_address?: string;
}

export default function BalancePage() {
  const [user, setUser] = useState<User | null>(null);
  const [balance, setBalance] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const router = useRouter();

  useEffect(() => {
    fetchUserBalance();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchUserBalance = async () => {
    try {
      setIsLoading(true);
      console.log('📊 Fetching user balance...');
      
      const response = await fetch('/api/balance');
      console.log('📋 Balance response status:', response.status);
      
      if (response.status === 401) {
        console.log('🔒 Not authenticated, redirecting to sign-in');
        router.push('/');
        return;
      }
      
      if (response.ok) {
        const data = await response.json();
        console.log('✅ Balance data received:', data);
        setUser(data.user);
        setBalance(data.balance);
        setError('');
      } else {
        const errorData = await response.json();
        console.error('❌ Failed to fetch balance:', errorData);
        setError(errorData.message || 'Failed to load balance');
      }
    } catch (error) {
      console.error('❌ Balance fetch error:', error);
      setError('Network error. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSignOut = () => {
    // Clear authentication and redirect
    document.cookie = 'auth-token=; path=/; expires=Thu, 01 Jan 1970 00:00:01 GMT;';
    router.push('/');
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-green-50 to-emerald-100 flex items-center justify-center">
        <div className="bg-white rounded-xl shadow-lg p-8 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading your balance...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-red-50 to-pink-100 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white rounded-xl shadow-lg p-8 text-center">
          <div className="text-red-500 text-4xl mb-4">❌</div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">Error</h2>
          <p className="text-gray-600 mb-6">{error}</p>
          <button
            onClick={fetchUserBalance}
            className="bg-indigo-600 text-white px-6 py-2 rounded-lg hover:bg-indigo-700 transition-colors"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-green-50 to-emerald-100 p-4">
      <div className="max-w-md mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between bg-white rounded-xl shadow-lg p-4">
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 bg-indigo-600 rounded-full flex items-center justify-center">
              <span className="text-lg">🏧</span>
            </div>
            <div>
              <h1 className="text-lg font-semibold text-gray-900">RoluATM</h1>
              <p className="text-xs text-gray-500">World ID Balance</p>
            </div>
          </div>
          <button
            onClick={handleSignOut}
            className="text-gray-400 hover:text-gray-600 text-sm"
          >
            Sign Out
          </button>
        </div>

        {/* Balance Display */}
        <div className="bg-white rounded-xl shadow-lg p-6">
          <BalanceDisplay balance={balance} user={user} />
        </div>
        
        {/* Withdrawal Form */}
        <div className="bg-white rounded-xl shadow-lg p-6">
          <WithdrawalForm 
            balance={balance} 
            onWithdrawal={fetchUserBalance} 
          />
        </div>

        {/* Footer */}
        <div className="text-center text-xs text-gray-400 space-y-1">
          <p>🔒 Secured by World ID verification</p>
          <p>💰 Cash dispensed from verified ATM locations</p>
        </div>
      </div>
    </div>
  );
} 