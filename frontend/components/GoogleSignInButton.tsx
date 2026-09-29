'use client';

import { useEffect, useRef } from 'react';
import Script from 'next/script';
import GoogleIcon from '@/components/GoogleIcon';
import { createClient } from '@/lib/supabase/client';

// Sign in with Google via Google Identity Services, handing the ID token to
// Supabase. Google's popup then names refactrapp.com rather than the
// Supabase project domain that the signInWithOAuth redirect flow shows.
// Without NEXT_PUBLIC_GOOGLE_CLIENT_ID set, falls back to that redirect flow.
const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

interface GoogleCredentialResponse {
  credential: string;
}

interface GoogleIdentity {
  accounts: {
    id: {
      initialize(config: {
        client_id: string;
        callback: (response: GoogleCredentialResponse) => void;
        nonce: string;
        use_fedcm_for_button?: boolean;
      }): void;
      renderButton(parent: HTMLElement, options: Record<string, unknown>): void;
    };
  };
}

declare global {
  interface Window {
    google?: GoogleIdentity;
  }
}

async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

interface Props {
  // Where /auth/callback sends the user after the redirect-flow fallback.
  redirectParam: string | null;
  onSignedIn: () => void;
  onError: (message: string) => void;
}

export default function GoogleSignInButton({ redirectParam, onSignedIn, onError }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  // Kept in refs so the Google callback, registered once, sees the latest props.
  const onSignedInRef = useRef(onSignedIn);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    onSignedInRef.current = onSignedIn;
    onErrorRef.current = onError;
  });

  const renderGoogleButton = async () => {
    const container = containerRef.current;
    if (!GOOGLE_CLIENT_ID || !container || !window.google) return;

    // Google puts the hashed nonce in the ID token; Supabase checks it
    // against the raw one, so a captured token can't be replayed.
    const rawNonce = crypto.randomUUID();
    const hashedNonce = await sha256Hex(rawNonce);

    window.google.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
      nonce: hashedNonce,
      use_fedcm_for_button: true,
      callback: async ({ credential }) => {
        const { error } = await createClient().auth.signInWithIdToken({
          provider: 'google',
          token: credential,
          nonce: rawNonce,
        });
        if (error) onErrorRef.current(error.message);
        else onSignedInRef.current();
      },
    });

    container.replaceChildren();
    window.google.accounts.id.renderButton(container, {
      type: 'standard',
      theme: 'outline',
      size: 'large',
      text: 'continue_with',
      shape: 'rectangular',
      logo_alignment: 'center',
      width: Math.min(container.clientWidth, 400), // Google caps the width at 400px
    });
  };

  if (!GOOGLE_CLIENT_ID) {
    const handleRedirectSignIn = async () => {
      const redirectTo = `${window.location.origin}/auth/callback${
        redirectParam ? `?redirect=${encodeURIComponent(redirectParam)}` : ''
      }`;
      const { error } = await createClient().auth.signInWithOAuth({
        provider: 'google',
        options: { redirectTo },
      });
      if (error) onError(error.message);
    };

    return (
      <button
        type="button"
        onClick={handleRedirectSignIn}
        className="w-full h-[54px] flex items-center justify-center gap-2 px-2 rounded-[10px] border-2 border-[#e6e8e7] bg-white font-semibold text-[18px] tracking-[-0.18px] text-[#232323] shadow-[0px_1px_1px_rgba(0,0,0,0.03)] hover:bg-gray-50 transition-colors cursor-pointer"
      >
        Continue with Google
        <GoogleIcon className="w-6 h-6" />
      </button>
    );
  }

  return (
    <>
      {/* onReady also re-fires on each remount (e.g. /login -> /signup), once the script is cached. */}
      <Script src="https://accounts.google.com/gsi/client" strategy="afterInteractive" onReady={() => void renderGoogleButton()} />
      {/* Height matches Google's "large" button so the layout doesn't jump when it renders. */}
      <div ref={containerRef} className="w-full min-h-[44px] flex justify-center" />
    </>
  );
}
