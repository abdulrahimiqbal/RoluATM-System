import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

export async function GET(request: NextRequest) {
  try {
    console.log('🔑 Generating nonce for wallet authentication...');
    
    // Generate a secure nonce (at least 8 alphanumeric characters)
    const nonce = crypto.randomUUID().replace(/-/g, '');
    
    console.log('✅ Nonce generated:', nonce.substring(0, 8) + '...');
    
    // Store nonce in secure HTTP-only cookie
    const cookieStore = await cookies();
    cookieStore.set('siwe', nonce, { 
      secure: true,
      httpOnly: true,
      sameSite: 'strict',
      maxAge: 60 * 60 // 1 hour
    });
    
    return NextResponse.json({ nonce });
  } catch (error) {
    console.error('❌ Nonce generation error:', error);
    return NextResponse.json({ error: 'Failed to generate nonce' }, { status: 500 });
  }
} 