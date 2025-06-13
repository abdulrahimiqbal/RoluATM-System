'use client';

import { ReactNode, useEffect } from 'react';
import { MiniKit } from '@worldcoin/minikit-js';

interface MiniKitProviderProps {
  children: ReactNode;
}

export default function MiniKitProvider({ children }: MiniKitProviderProps) {
  useEffect(() => {
    // Initialize World ID MiniKit with your app ID
    const appId = process.env.NEXT_PUBLIC_WORLD_ID_APP_ID as `app_${string}`;
    
    if (appId) {
      try {
        MiniKit.install(appId);
        console.log('✅ MiniKit initialized successfully');
      } catch (error) {
        console.error('❌ MiniKit initialization failed:', error);
      }
    } else {
      console.error('❌ NEXT_PUBLIC_WORLD_ID_APP_ID not configured');
    }
  }, []);

  return <>{children}</>;
} 