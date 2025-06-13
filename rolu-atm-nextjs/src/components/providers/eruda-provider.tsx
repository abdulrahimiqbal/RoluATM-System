'use client';

import { useEffect } from 'react';

export default function ErudaProvider() {
  useEffect(() => {
    // Enable Eruda for debugging World ID verification issues
    // Remove this in production after debugging is complete
    import('eruda').then((eruda) => {
      eruda.default.init();
      console.log('🔧 Eruda debugging console activated');
      console.log('📱 Tap the Eruda icon (bottom right) to open debug console');
    }).catch((error) => {
      console.error('Failed to load Eruda:', error);
    });
  }, []);

  return null; // This component doesn't render anything
} 