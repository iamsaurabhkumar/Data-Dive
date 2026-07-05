import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/dashboard";

  // Force the origin to your public domain, bypassing the internal Docker IP
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://divesocialdata.com";

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
