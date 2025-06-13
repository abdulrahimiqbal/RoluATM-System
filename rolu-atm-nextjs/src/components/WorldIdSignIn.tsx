'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { MiniKit, VerificationLevel } from '@worldcoin/minikit-js';

export const WorldIdSignIn = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const router = useRouter();

  const handleSignIn = async () => {
    setIsLoading(true);
    setError('');

    try {
      console.log('🔐 Starting wallet authentication...');
      console.log('🌍 MiniKit object:', MiniKit);

      // Check if MiniKit is installed (crucial for preventing browser redirects)
      const isInstalled = MiniKit.isInstalled();
      console.log('📱 MiniKit.isInstalled():', isInstalled);
      
      if (!isInstalled) {
        console.error('❌ MiniKit is not installed - app not running in World App');
        console.log('🌐 User agent:', navigator.userAgent);
        console.log('🔗 Current URL:', window.location.href);
        setError('Please open this app in World App to sign in');
        setIsLoading(false);
        return;
      }

      // First get a nonce from our backend
      console.log('🔑 Getting nonce from backend...');
      const nonceResponse = await fetch('/api/nonce');
      if (!nonceResponse.ok) {
        throw new Error('Failed to get nonce');
      }
      const { nonce } = await nonceResponse.json();
      console.log('✅ Nonce received:', nonce);

      // Wallet authentication for both World ID and wallet access
      const walletAuthPayload = {
        nonce: nonce,
        requestId: '0',
        expirationTime: new Date(new Date().getTime() + 7 * 24 * 60 * 60 * 1000), // 7 days
        notBefore: new Date(new Date().getTime() - 24 * 60 * 60 * 1000), // 24 hours ago
        statement: 'Sign in to RoluATM for secure cash withdrawal using your World ID and wallet.',
      };

      console.log('📝 Wallet auth payload:', walletAuthPayload);
      console.log('📝 Requesting wallet authentication...');
      
      const response = await MiniKit.commandsAsync.walletAuth(walletAuthPayload);
      
      console.log('📋 Raw wallet auth response:', response);
      console.log('📋 Response type:', typeof response);
      console.log('📋 Response keys:', Object.keys(response || {}));
      
      if (response?.finalPayload) {
        console.log('📋 Final payload:', response.finalPayload);
        console.log('📋 Final payload status:', response.finalPayload.status);
      }

      if (response?.finalPayload?.status === "success") {
        console.log('✅ Wallet authentication successful');
        console.log('🔑 Wallet data:', {
          address: response.finalPayload.address,
          message: response.finalPayload.message?.substring(0, 100) + '...',
          signature: response.finalPayload.signature?.substring(0, 50) + '...'
        });

        // Get wallet address from MiniKit
        const walletAddress = response.finalPayload.address;
        console.log('💰 Wallet address from response:', walletAddress);
        
        // Send to backend for user creation/authentication
        console.log('🔄 Sending to backend...');
        const authResponse = await fetch('/api/auth', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            walletAuthPayload: response.finalPayload,
            nonce: nonce,
            walletAddress: walletAddress || response.finalPayload.address
          })
        });

        console.log('🔄 Backend auth response status:', authResponse.status);
        console.log('🔄 Backend auth response headers:', Object.fromEntries(authResponse.headers.entries()));

        if (authResponse.ok) {
          const authData = await authResponse.json();
          console.log('🎉 Authentication successful:', authData);
          console.log('🎉 Redirecting to balance page...');
          router.push('/balance');
        } else {
          const errorData = await authResponse.json();
          console.error('❌ Backend auth failed:', errorData);
          setError(errorData.message || 'Authentication failed');
        }
      } else {
        console.error('❌ Wallet authentication failed');
        console.error('❌ Response:', response);
        console.error('❌ Final payload:', response?.finalPayload);
        setError(`Wallet authentication failed: ${response?.finalPayload?.status || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('❌ Sign-in error:', error);
      console.error('❌ Error type:', typeof error);
      console.error('❌ Error message:', error instanceof Error ? error.message : String(error));
      console.error('❌ Error stack:', error instanceof Error ? error.stack : 'No stack trace');
      setError(`Sign-in failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <button
        onClick={handleSignIn}
        disabled={isLoading}
        className="w-full bg-indigo-600 text-white py-3 px-4 rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {isLoading ? (
          <div className="flex items-center justify-center space-x-2">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
            <span>Signing In...</span>
          </div>
        ) : (
          '🌍 Sign In with World ID & Wallet'
        )}
      </button>
      
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <p className="text-red-600 text-sm text-center">{error}</p>
        </div>
      )}

      <div className="text-xs text-gray-500 text-center">
        <p>Secure authentication using World ID and wallet</p>
        <p>Your identity is verified and wallet connected</p>
        <p className="mt-2 text-xs text-blue-500">Debug: Tap Eruda icon (bottom right) for console</p>
      </div>
    </div>
  );
}; 