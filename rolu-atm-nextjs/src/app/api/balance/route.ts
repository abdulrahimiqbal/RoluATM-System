import { NextRequest, NextResponse } from 'next/server';
import { verifyAuthToken } from '@/lib/auth';
import { getUserById, updateUserBalance } from '@/lib/database';
import { getWalletBalanceInUSDC } from '@/lib/blockchain';

export async function GET(request: NextRequest) {
  try {
    console.log('📊 Balance request received');
    
    const token = request.cookies.get('auth-token')?.value;
    if (!token) {
      console.log('❌ No auth token found');
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
    }

    console.log('🔍 Verifying auth token...');
    const decoded = verifyAuthToken(token);
    const user = await getUserById(decoded.userId);
    
    if (!user) {
      console.error('❌ User not found for ID:', decoded.userId);
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    // If user has a wallet address, fetch fresh balance from blockchain
    let currentBalance = user.balance;
    if (user.wallet_address) {
      try {
        console.log('🔄 Fetching fresh wallet balance for:', user.wallet_address);
        const freshBalance = await getWalletBalanceInUSDC(user.wallet_address);
        
        // Update the database with fresh balance
        await updateUserBalance(user.id, freshBalance);
        currentBalance = freshBalance;
        
        console.log('✅ Fresh balance updated:', freshBalance);
      } catch (error) {
        console.error('❌ Failed to fetch fresh balance, using cached:', error);
        // Use cached balance if blockchain fetch fails
      }
    }

    console.log('✅ Balance retrieved for user:', user.id, 'Balance:', currentBalance);

    return NextResponse.json({
      user: {
        id: user.id,
        verification_level: user.verification_level,
        nullifier_hash: user.nullifier_hash,
        wallet_address: user.wallet_address
      },
      balance: currentBalance
    });
  } catch (error) {
    console.error('❌ Balance fetch error:', error);
    return NextResponse.json({ error: 'Failed to fetch balance' }, { status: 500 });
  }
} 