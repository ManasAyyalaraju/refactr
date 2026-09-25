'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import Header from '@/components/Header';
import Footer from '@/components/Footer';
import { useAuth } from '@/lib/supabase/auth-context';
import { createClient } from '@/lib/supabase/client';
import { listGeneratedResumes, GeneratedResumeRow } from '@/lib/supabase/resumes';
import { cleanJobTitle } from '@/lib/dashboard-stats';
import { ChevronRight } from 'lucide-react';

function scoreChip(score: number | null | undefined) {
  if (score === null || score === undefined) {
    return <span className="text-xs px-2.5 py-1 rounded-full bg-black/5 text-black/50">—</span>;
  }
  const color =
    score >= 80 ? 'bg-green-50 text-green-700 border-green-200' :
    score >= 60 ? 'bg-amber-50 text-amber-700 border-amber-200' :
    'bg-red-50 text-red-700 border-red-200';
  return <span className={`text-xs px-2.5 py-1 rounded-full border font-medium ${color}`}>{score}%</span>;
}

export default function TailoredHistoryPage() {
  const { user } = useAuth();
  const supabase = createClient();
  const [rows, setRows] = useState<GeneratedResumeRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    listGeneratedResumes(supabase, user.id).then((data) => {
      setRows(data.filter((r) => r.tailoring_options?.mode === 'tailor'));
      setLoading(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  return (
    <div className="min-h-screen flex flex-col">
      <Header />

      <main className="flex-1 py-16 px-6 md:px-10">
        <div className="container mx-auto max-w-4xl">
          <h1 className="font-bold text-[28px] sm:text-[36px] leading-[1.05] tracking-[-0.96px] text-black mb-10">
            Tailored Resumes
          </h1>

          <div className="bg-[#fffcfc] border border-black rounded">
            {loading ? (
              <p className="text-sm text-black/50 text-center py-16">Loading…</p>
            ) : rows.length === 0 ? (
              <div className="text-center py-16 px-6">
                <p className="text-sm text-black/50 mb-4">Tailor your first resume to see it here.</p>
                <Link
                  href="/tailor"
                  className="inline-flex items-center gap-2 bg-[#187fe7] hover:bg-[#146bc7] text-white font-medium text-[14px] px-5 py-2.5 rounded-[14px] transition-colors"
                >
                  Tailor a Resume
                </Link>
              </div>
            ) : (
              rows.map((row, i) => {
                const title = cleanJobTitle(row.job_title) ?? 'Untitled role';
                const score = row.tailoring_options?.compatibility?.score ?? row.tailoring_options?.score;
                const date = new Date(row.created_at).toLocaleDateString(undefined, {
                  year: 'numeric',
                  month: 'short',
                  day: 'numeric',
                });
                return (
                  <Link
                    key={row.id}
                    href={`/tailored/${row.id}`}
                    className={`flex items-center justify-between gap-4 px-6 py-4 hover:bg-black/[0.03] transition-colors ${
                      i !== rows.length - 1 ? 'border-b border-black/[0.19]' : ''
                    }`}
                  >
                    <div className="min-w-0">
                      <p className="font-semibold text-[15px] text-black truncate">{title}</p>
                      <p className="text-[13px] text-black/50 truncate">
                        {row.company ? `${row.company} · ` : ''}
                        {date}
                      </p>
                    </div>
                    <div className="flex items-center gap-3 flex-shrink-0">
                      {scoreChip(score)}
                      <ChevronRight className="w-4 h-4 text-black/40" />
                    </div>
                  </Link>
                );
              })
            )}
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
