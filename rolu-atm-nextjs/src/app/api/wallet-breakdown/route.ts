import { NextRequest, NextResponse } from 'next/server';
import { verifyAuthToken } from '@/lib/auth';
import { getUserById } from '@/lib/database';
import { getWalletBreakdown } from '@/lib/blockchain';

export async function GET(request: NextRequest) {
  try {
    console.log('📊 Wallet breakdown request received');
    
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

    if (!user.wallet_address) {
      console.log('❌ No wallet address found for user');
      return NextResponse.json({ error: 'No wallet connected' }, { status: 400 });
    }

    console.log('🔄 Fetching wallet breakdown for:', user.wallet_address);
    const breakdown = await getWalletBreakdown(user.wallet_address);

    console.log('✅ Wallet breakdown retrieved:', breakdown);

    return NextResponse.json({
      wallet_address: user.wallet_address,
      breakdown: breakdown,
      total_usd: breakdown.reduce((sum, token) => sum + token.usdValue, 0)
    });
  } catch (error) {
    console.error('❌ Wallet breakdown error:', error);
    return NextResponse.json({ error: 'Failed to fetch wallet breakdown' }, { status: 500 });
  }
} 