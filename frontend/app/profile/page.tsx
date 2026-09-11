'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import Footer from '@/components/Footer';
import Avatar, { AVATAR_COUNT } from '@/components/Avatar';
import { useAuth } from '@/lib/supabase/auth-context';
import { createClient } from '@/lib/supabase/client';
import { listBaseResumes, downloadBaseResume } from '@/lib/supabase/resumes';
import { reparseResume } from '@/lib/api';
import { Pencil, Check, X, Shuffle, LogOut } from 'lucide-react';

interface ReparseLogEntry {
  title: string;
  ok: boolean;
  message?: string;
}

function randomSeed(exclude?: number): number {
  let next = Math.floor(Math.random() * AVATAR_COUNT);
  if (exclude !== undefined && AVATAR_COUNT > 1) {
    while (next === exclude) next = Math.floor(Math.random() * AVATAR_COUNT);
  }
  return next;
}

export default function ProfilePage() {
  const router = useRouter();
  const { user, displayName, updateDisplayName, signOut } = useAuth();
  const supabase = createClient();
  const [createdAt, setCreatedAt] = useState<string | null>(null);
  const [avatarSeed, setAvatarSeed] = useState<number>(0);
  const [loading, setLoading] = useState(true);

  const [isEditing, setIsEditing] = useState(false);
  const [nameInput, setNameInput] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!user) return;
    supabase
      .from('profiles')
      .select('created_at, avatar_seed')
      .eq('id', user.id)
      .single()
      .then(async ({ data }) => {
        setCreatedAt(data?.created_at ?? null);
        if (data?.avatar_seed !== null && data?.avatar_seed !== undefined) {
          setAvatarSeed(data.avatar_seed);
        } else {
          // First visit - pick and persist a random avatar so it's stable from here on.
          const seed = randomSeed();
          setAvatarSeed(seed);
          await supabase.from('profiles').update({ avatar_seed: seed }).eq('id', user.id);
        }
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  const memberSince = createdAt
    ? new Date(createdAt).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      })
    : null;

  const shuffleAvatar = async () => {
    if (!user) return;
    const seed = randomSeed(avatarSeed);
    setAvatarSeed(seed);
    await supabase.from('profiles').update({ avatar_seed: seed }).eq('id', user.id);
  };

  const startEditing = () => {
    setNameInput(displayName || '');
    setError('');
    setIsEditing(true);
  };

  const cancelEditing = () => {
    setIsEditing(false);
    setError('');
  };

  const saveName = async () => {
    setIsSaving(true);
    setError('');
    const { error: saveError } = await updateDisplayName(nameInput);
    setIsSaving(false);
    if (saveError) {
      setError(saveError);
      return;
    }
    setIsEditing(false);
  };

  const handleSignOut = async () => {
    await signOut();
    router.push('/');
    router.refresh();
  };

  const [isReparsing, setIsReparsing] = useState(false);
  const [reparseStatus, setReparseStatus] = useState('');
  const [reparseLog, setReparseLog] = useState<ReparseLogEntry[]>([]);

  const handleReparseAll = async () => {
    if (!user) return;

    setIsReparsing(true);
    setReparseStatus('Loading your resumes...');
    setReparseLog([]);

    const resumes = await listBaseResumes(supabase, user.id);
    if (resumes.length === 0) {
      setReparseStatus('No saved resumes to reparse.');
      setIsReparsing(false);
      return;
    }

    const log: ReparseLogEntry[] = [];
    for (let i = 0; i < resumes.length; i++) {
      const resume = resumes[i];
      setReparseStatus(`Reparsing ${i + 1} of ${resumes.length}: ${resume.title}`);

      try {
        const pdfBlob = await downloadBaseResume(supabase, resume.storage_path);
        if (!pdfBlob) throw new Error('Could not download the saved PDF.');

        const result = await reparseResume(pdfBlob, resume.file_name ?? resume.title);
        if (!result.success) throw new Error(result.error || 'Reparse failed.');

        const { error: updateError } = await supabase
          .from('base_resumes')
          .update({
            parsed_data: result.data.resume,
            inferred_skills: result.data.inferred_skills,
          })
          .eq('id', resume.id);
        if (updateError) throw updateError;

        log.push({ title: resume.title, ok: true });
      } catch (err) {
        log.push({
          title: resume.title,
          ok: false,
          message: err instanceof Error ? err.message : 'Unknown error',
        });
      }
      setReparseLog([...log]);
    }

    const succeeded = log.filter((r) => r.ok).length;
    setReparseStatus(`Done — ${succeeded}/${resumes.length} reparsed successfully.`);
    setIsReparsing(false);
  };

  return (
    <div className="min-h-screen flex flex-col">
      <Header />

      <main className="flex-1 py-12 px-4">
        <div className="container mx-auto max-w-3xl">
          <h1 className="font-bold text-[32px] sm:text-[48px] leading-[1.05] tracking-[-0.96px] text-black mb-8">
            My Profile
          </h1>

          <div className="bg-[#fffcfc] border border-black rounded-[4px] p-6 sm:p-8">
            <div className="flex items-center justify-between gap-4 mb-2">
              <div className="flex items-center gap-4">
                <div className="relative shrink-0">
                  <Avatar seed={avatarSeed} className="w-[72px] h-[72px]" />
                  <button
                    type="button"
                    onClick={shuffleAvatar}
                    aria-label="Shuffle avatar"
                    title="Shuffle avatar"
                    className="absolute -bottom-1 -right-1 w-6 h-6 flex items-center justify-center rounded-full bg-black text-white hover:bg-[#187fe7] transition-colors cursor-pointer"
                  >
                    <Shuffle className="w-3 h-3" />
                  </button>
                </div>
                <div>
                  <p className="font-bold text-[18px] tracking-[-0.36px] text-black">
                    {loading ? '—' : displayName || 'No name set'}
                  </p>
                  <p className="text-[13px] tracking-[-0.26px] text-black">{user?.email}</p>
                </div>
              </div>

              <button
                type="button"
                onClick={handleSignOut}
                className="shrink-0 flex items-center gap-2 bg-[#fffcfc] rounded-[14px] px-6 py-3.5 text-[16px] text-black hover:bg-gray-50 transition-colors cursor-pointer"
              >
                <LogOut className="w-4 h-4" />
                Sign out
              </button>
            </div>

            <div className="mt-4">
              <div className="flex items-start justify-between border-t border-b border-black/[0.19] py-3 gap-4">
                <p className="font-semibold text-[14px] tracking-[-0.28px] text-black">Name</p>
                {isEditing ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={nameInput}
                      onChange={(e) => setNameInput(e.target.value)}
                      autoFocus
                      disabled={isSaving}
                      placeholder="Your name"
                      className="max-w-[200px] px-2.5 py-1 border border-gray-300 rounded-lg text-[14px] text-black focus:ring-2 focus:ring-[#187fe7] focus:border-[#187fe7] outline-none disabled:opacity-50"
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveName();
                        if (e.key === 'Escape') cancelEditing();
                      }}
                    />
                    <button
                      onClick={saveName}
                      disabled={isSaving}
                      aria-label="Save name"
                      className="p-1 rounded-lg text-green-600 hover:bg-green-50 transition-colors disabled:opacity-50 cursor-pointer"
                    >
                      <Check className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={cancelEditing}
                      disabled={isSaving}
                      aria-label="Cancel"
                      className="p-1 rounded-lg text-gray-500 hover:bg-gray-100 transition-colors disabled:opacity-50 cursor-pointer"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="text-[14px] tracking-[-0.28px] text-black">
                      {displayName || 'Not set'}
                    </span>
                    <button
                      onClick={startEditing}
                      aria-label="Edit name"
                      className="text-gray-400 hover:text-[#187fe7] transition-colors cursor-pointer"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}
              </div>
              {error && <p className="text-sm text-red-600 text-right pt-2">{error}</p>}

              <div className="flex items-start justify-between border-b border-black/[0.19] py-3 gap-4">
                <p className="font-semibold text-[14px] tracking-[-0.28px] text-black">Email</p>
                <p className="text-[14px] tracking-[-0.28px] text-black text-right">{user?.email}</p>
              </div>

              <div className="flex items-start justify-between border-b border-black/[0.19] py-3 gap-4">
                <p className="font-semibold text-[14px] tracking-[-0.28px] text-black">Member since</p>
                <p className="text-[14px] tracking-[-0.28px] text-black text-right">
                  {loading ? '—' : memberSince || 'Unknown'}
                </p>
              </div>
            </div>

            <div className="flex justify-end mt-5">
              <button
                type="button"
                title="Contact support to delete your account"
                className="bg-[#fb0000]/[0.17] text-[#fb0000] rounded-[14px] px-5 py-2.5 text-[14px] hover:bg-[#fb0000]/25 transition-colors cursor-pointer"
              >
                Delete Account
              </button>
            </div>
          </div>

          <div className="bg-[#fffcfc] border border-black rounded-[4px] p-6 sm:p-8 mt-6">
            <p className="font-bold text-[16px] tracking-[-0.32px] text-black mb-1">
              Developer / Testing Tools
            </p>
            <p className="text-[13px] tracking-[-0.26px] text-black/70 mb-4">
              Not a real product feature. Re-parses every saved resume to backfill inferred skills
              for resumes saved before that existed — the saved PDF files are left untouched.
            </p>
            <button
              type="button"
              onClick={handleReparseAll}
              disabled={isReparsing}
              className="bg-black text-white rounded-[14px] px-5 py-2.5 text-[14px] hover:bg-gray-800 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isReparsing ? 'Reparsing...' : 'Reparse All Resumes'}
            </button>

            {reparseStatus && (
              <p className="text-[13px] tracking-[-0.26px] text-black mt-3">{reparseStatus}</p>
            )}

            {reparseLog.length > 0 && (
              <ul className="mt-3 space-y-1">
                {reparseLog.map((entry, i) => (
                  <li
                    key={`${entry.title}-${i}`}
                    className={`text-[13px] tracking-[-0.26px] ${entry.ok ? 'text-green-700' : 'text-red-600'}`}
                  >
                    {entry.ok ? '✓' : '✗'} {entry.title}
                    {entry.message ? ` — ${entry.message}` : ''}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
