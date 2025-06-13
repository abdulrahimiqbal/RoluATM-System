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
      console.log('🔐 Starting World ID sign-in...');
      console.log('🌍 MiniKit object:', MiniKit);
      console.log('🔍 Window object keys:', Object.keys(window));

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

      // World ID verification for authentication
      const verifyPayload = {
        action: "rolu-atm-signin",
        signal: "",
        verification_level: VerificationLevel.Orb,
      };

      console.log('📝 Verify payload:', verifyPayload);
      console.log('📝 Requesting World ID verification...');
      
      const response = await MiniKit.commandsAsync.verify(verifyPayload);
      
      console.log('📋 Raw World ID response:', response);
      console.log('📋 Response type:', typeof response);
      console.log('📋 Response keys:', Object.keys(response || {}));
      
      if (response?.finalPayload) {
        console.log('📋 Final payload:', response.finalPayload);
        console.log('📋 Final payload status:', response.finalPayload.status);
      }

      if (response?.finalPayload?.status === "success") {
        console.log('✅ World ID verification successful');
        console.log('🔑 Proof data:', {
          nullifier_hash: response.finalPayload.nullifier_hash,
          verification_level: response.finalPayload.verification_level,
          proof: response.finalPayload.proof?.substring(0, 50) + '...'
        });
        
        // Send to backend for user creation/authentication
        console.log('🔄 Sending to backend...');
        const authResponse = await fetch('/api/auth', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            worldIdProof: response.finalPayload,
            action: verifyPayload.action
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
        console.error('❌ World ID verification failed');
        console.error('❌ Response:', response);
        console.error('❌ Final payload:', response?.finalPayload);
        setError(`World ID verification failed: ${response?.finalPayload?.status || 'Unknown error'}`);
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
          '🌍 Sign In with World ID'
        )}
      </button>
      
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <p className="text-red-600 text-sm text-center">{error}</p>
        </div>
      )}

      <div className="text-xs text-gray-500 text-center">
        <p>Secure authentication using World ID</p>
        <p>Your identity is verified but remains private</p>
        <p className="mt-2 text-xs text-blue-500">Debug: Tap Eruda icon (bottom right) for console</p>
      </div>
    </div>
  );
}; 