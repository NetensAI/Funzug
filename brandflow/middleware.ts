import { NextRequest, NextResponse } from 'next/server';
import { jwtVerify } from 'jose';
export async function middleware(req:NextRequest) {
  const automation = req.nextUrl.pathname === '/api/automation/scan' && req.headers.get('x-automation-key') === process.env.AUTOMATION_KEY;
  const draftIngest = req.nextUrl.pathname === '/api/integrations/funzug/drafts' || req.nextUrl.pathname === '/api/integrations/funzug/publications' || req.nextUrl.pathname === '/api/integrations/funzug/outcomes' || req.nextUrl.pathname === '/api/integrations/funzug/native-handoff' || req.nextUrl.pathname === '/api/integrations/funzug/native-package';
  const open = req.nextUrl.pathname === '/login' || req.nextUrl.pathname === '/api/login' || req.nextUrl.pathname === '/api/health' || automation || draftIngest;
  if (!open) {
    const token = req.cookies.get('session')?.value;
    if (!token) return NextResponse.redirect(new URL('/login',req.url));
    try { await jwtVerify(token,new TextEncoder().encode(process.env.AUTH_SECRET)); }
    catch { const res=NextResponse.redirect(new URL('/login',req.url)); res.cookies.delete('session'); return res; }
  }
  return NextResponse.next();
}
export const config = { matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'] };
