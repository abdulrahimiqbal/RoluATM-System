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

      // Check if MiniKit is installed (crucial for preventing browser redirects)
      if (!MiniKit.isInstalled()) {
        console.error('❌ MiniKit is not installed - app not running in World App');
        setError('Please open this app in World App to sign in');
        setIsLoading(false);
        return;
      }

      // World ID verification for authentication
      const verifyPayload = {
        action: "rolu-atm-signin",
        signal: "",
        verification_level: VerificationLevel.Orb, // or VerificationLevel.Device
      };

      console.log('📝 Requesting World ID verification...');
      const response = await MiniKit.commandsAsync.verify(verifyPayload);
      
      console.log('📋 World ID response:', response);

      if (response.finalPayload.status === "success") {
        console.log('✅ World ID verification successful');
        
        // Send to backend for user creation/authentication
        const authResponse = await fetch('/api/auth', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            worldIdProof: response.finalPayload,
            action: verifyPayload.action
          })
        });

        console.log('🔄 Backend auth response status:', authResponse.status);

        if (authResponse.ok) {
          console.log('🎉 Authentication successful, redirecting...');
          router.push('/balance');
        } else {
          const errorData = await authResponse.json();
          console.error('❌ Backend auth failed:', errorData);
          setError(errorData.message || 'Authentication failed');
        }
      } else {
        console.error('❌ World ID verification failed:', response.finalPayload);
        setError('World ID verification failed');
      }
    } catch (error) {
      console.error('❌ Sign-in error:', error);
      setError('Sign-in failed. Please try again.');
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
      </div>
    </div>
  );
}; 