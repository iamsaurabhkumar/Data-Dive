import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/dashboard";

  // Public origin for the redirect. NEXT_PUBLIC_SITE_URL bypasses the internal Docker
  // address in production; locally we fall back to the request's own origin.
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || new URL(request.url).origin;

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(`${siteUrl}${next}`);
    }
  }

  // Return to home page on error using the correct domain
  return NextResponse.redirect(`${siteUrl}/?error=auth_callback_error`);
}
