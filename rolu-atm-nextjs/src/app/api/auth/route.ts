import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { verifySiweMessage } from '@worldcoin/minikit-js';
import { createJWTToken } from '@/lib/auth';
import { getUserByWalletAddress, createUser, updateUserBalance } from '@/lib/database';

export async function POST(request: NextRequest) {
  try {
    console.log('🔐 Auth request received');
    
    const { walletAuthPayload, nonce, walletAddress } = await request.json();
    
    console.log('📝 Wallet auth payload:', {
      status: walletAuthPayload?.status,
      address: walletAuthPayload?.address,
      message: walletAuthPayload?.message?.substring(0, 50) + '...',
      signature: walletAuthPayload?.signature?.substring(0, 20) + '...'
    });
    console.log('🔑 Nonce:', nonce);
    console.log('💰 Wallet address:', walletAddress);

    if (!walletAuthPayload || !nonce || !walletAddress) {
      console.error('❌ Missing required fields');
      return NextResponse.json({ error: 'Missing required fields' }, { status: 400 });
    }

    // Verify nonce matches the one we stored
    const cookieStore = await cookies();
    const storedNonce = cookieStore.get('siwe')?.value;
    if (nonce !== storedNonce) {
      console.error('❌ Invalid nonce');
      return NextResponse.json({ error: 'Invalid nonce' }, { status: 401 });
    }

    // Verify the SIWE message signature
    console.log('🔍 Verifying SIWE message...');
    try {
      const validMessage = await verifySiweMessage(walletAuthPayload, nonce);
      if (!validMessage.isValid) {
        console.error('❌ SIWE verification failed');
        return NextResponse.json({ error: 'Wallet authentication failed' }, { status: 401 });
      }
      console.log('✅ SIWE verification successful');
    } catch (error) {
      console.error('❌ SIWE verification error:', error);
      return NextResponse.json({ error: 'Wallet authentication failed' }, { status: 401 });
    }

    // Get or create user based on wallet address
    let user = await getUserByWalletAddress(walletAddress);
    
    if (!user) {
      console.log('👤 Creating new user for wallet:', walletAddress);
      
      // Fetch actual wallet balance from blockchain
      let actualBalance = 0;
      try {
        console.log('💰 Fetching wallet balance...');
        // For now, we'll use a mock balance - in production you'd call a blockchain RPC
        // const balance = await getWalletBalance(walletAddress);
        actualBalance = 150.50; // Mock balance - replace with actual blockchain call
        console.log('✅ Wallet balance fetched:', actualBalance);
      } catch (error) {
        console.error('❌ Failed to fetch wallet balance:', error);
        actualBalance = 100.00; // Fallback balance
      }
      
      user = await createUser({
        wallet_address: walletAddress,
        initial_balance: actualBalance,
      });
    } else {
      console.log('✅ Existing user found:', user.id);
      
      // Update balance with current wallet balance
      try {
        console.log('💰 Updating wallet balance...');
        // const balance = await getWalletBalance(walletAddress);
        const actualBalance = 175.25; // Mock updated balance
        await updateUserBalance(user.id, actualBalance);
        console.log('✅ Balance updated:', actualBalance);
      } catch (error) {
        console.error('❌ Failed to update wallet balance:', error);
      }
    }

    // Create JWT token
    const token = createJWTToken(user.id, walletAddress);
    
    // Set secure HTTP-only cookie
    cookieStore.set('auth-token', token, {
      httpOnly: true,
      secure: true,
      sameSite: 'strict',
      maxAge: 7 * 24 * 60 * 60, // 7 days
    });

    // Clear the nonce cookie
    cookieStore.delete('siwe');

    console.log('🎉 Authentication successful for user:', user.id);

    return NextResponse.json({
      message: 'Authentication successful',
      user: {
        id: user.id,
        wallet_address: user.wallet_address,
        balance: user.balance
      }
    });
  } catch (error) {
    console.error('❌ Auth error:', error);
    return NextResponse.json({ error: 'Authentication failed' }, { status: 500 });
  }
} 