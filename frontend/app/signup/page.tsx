'use client';

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import ErrorMessage from '@/components/ErrorMessage';
import AuthInput from '@/components/AuthInput';
import AuthProductGraphic from '@/components/AuthProductGraphic';
import GoogleSignInButton from '@/components/GoogleSignInButton';
import { createClient } from '@/lib/supabase/client';
import { stashPendingDisplayName } from '@/lib/supabase/auth-context';

function safeRedirectTarget(value: string | null): string {
  // Only allow same-site relative paths - reject absolute/protocol-relative URLs to avoid an open redirect.
  return value && value.startsWith('/') && !value.startsWith('//') ? value : '/dashboard';
}

export default function SignupPage() {
  return (
    <Suspense fallback={null}>
      <SignupForm />
    </Suspense>
  );
}

function SignupForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const supabase = createClient();
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [needsConfirmation, setNeedsConfirmation] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const redirectParam = searchParams.get('redirect');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    const { data, error: signUpError } = await supabase.auth.signUp({
      email,
      password,
    });

    if (signUpError) {
      setError(signUpError.message);
      setIsLoading(false);
      return;
    }

    if (data.user && data.session) {
      // We have a live session immediately — the profiles row already
      // exists (created by the on_auth_user_created trigger), just fill
      // in the display name.
      if (displayName.trim()) {
        await supabase
          .from('profiles')
          .update({ display_name: displayName.trim() })
          .eq('id', data.user.id);
      }
      router.push(safeRedirectTarget(redirectParam));
      router.refresh();
      return;
    }

    // Email confirmation is required — no session yet. Stash the display
    // name so it gets applied automatically on first login.
    if (displayName.trim()) {
      stashPendingDisplayName(email, displayName.trim());
    }
    setNeedsConfirmation(true);
    setIsLoading(false);
  };

  const handleGoogleSignedIn = () => {
    router.push(safeRedirectTarget(redirectParam));
    router.refresh();
  };

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-white">
      <div className="flex flex-col w-full md:flex-1 p-6 sm:p-8">
        <Link href="/" className="inline-flex items-center gap-2 shrink-0">
          <div className="relative w-8 h-[30px] shrink-0">
            <div className="absolute left-0 top-0 w-[23px] h-[21px] rounded-[3px] border-[2.5px] border-black bg-white" />
            <div className="absolute left-[7px] top-[6px] w-[23px] h-[21px] rounded-[3px] border-[2.5px] border-black bg-white" />
          </div>
          <span className="font-bold text-[32px] text-black">refactr</span>
        </Link>

        <div className="flex flex-1 flex-col items-center justify-center gap-8 px-0 sm:px-16 py-12">
          <h1 className="font-bold text-[32px] sm:text-[40px] leading-[1.1] tracking-[-1.6px] text-[#232323] text-center">
            Sign up
          </h1>

          {needsConfirmation ? (
            <div className="w-full max-w-[399px] bg-green-50 border border-green-200 text-green-700 rounded-lg p-4 text-sm text-center">
              We sent a confirmation link to <span className="font-semibold">{email}</span>.
              Click it to activate your account, then log in.
            </div>
          ) : (
            <>
              {error && (
                <div className="w-full max-w-[399px]">
                  <ErrorMessage message={error} />
                </div>
              )}

              <form onSubmit={handleSubmit} className="w-full max-w-[399px] flex flex-col gap-5">
                <AuthInput
                  id="displayName"
                  label="Your Name"
                  type="text"
                  required
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Jane Doe"
                />

                <AuthInput
                  id="email"
                  label="Email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                />

                <AuthInput
                  id="password"
                  label="Password"
                  type="password"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 6 characters"
                />

                <button
                  type="submit"
                  disabled={isLoading}
                  className={`w-full flex items-center justify-center px-2 py-4 rounded-[10px] font-semibold text-[18px] tracking-[-0.18px] transition-colors cursor-pointer ${
                    isLoading ? 'bg-gray-300 text-gray-500 cursor-not-allowed' : 'bg-[#187fe7] hover:bg-[#146bc7] text-white'
                  }`}
                >
                  {isLoading ? 'Creating account...' : 'Sign up'}
                </button>

                <div className="flex items-center gap-2.5 w-full">
                  <div className="flex-1 h-px bg-[#d9d9d9]" />
                  <span className="text-[16px] font-medium text-[#6e6e6e]">or</span>
                  <div className="flex-1 h-px bg-[#d9d9d9]" />
                </div>

                <GoogleSignInButton
                  redirectParam={redirectParam}
                  onSignedIn={handleGoogleSignedIn}
                  onError={setError}
                />
              </form>
            </>
          )}

          <p className="text-[18px] text-[#6c6c6c] text-center">
            Already have an account??{' '}
            <Link
              href={redirectParam ? `/login?redirect=${encodeURIComponent(redirectParam)}` : '/login'}
              className="font-semibold text-[#187fe7] underline"
            >
              Sign in
            </Link>
          </p>
        </div>
      </div>

      <div className="hidden md:flex w-[849px] max-w-[45vw] h-auto p-3 shrink-0">
        <div className="flex-1 rounded-2xl overflow-hidden">
          <AuthProductGraphic className="w-full h-full" />
        </div>
      </div>
    </div>
  );
}
