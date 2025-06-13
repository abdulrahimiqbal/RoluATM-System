import { NextRequest, NextResponse } from 'next/server';
import { verifyAuthToken } from '@/lib/auth';
import { getUserById } from '@/lib/database';

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

    console.log('✅ Balance retrieved for user:', user.id, 'Balance:', user.balance);

    return NextResponse.json({
      user: {
        id: user.id,
        verification_level: user.verification_level,
        nullifier_hash: user.nullifier_hash
      },
      balance: user.balance
    });
  } catch (error) {
    console.error('❌ Balance fetch error:', error);
    return NextResponse.json({ error: 'Failed to fetch balance' }, { status: 500 });
  }
} 