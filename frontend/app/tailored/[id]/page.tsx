'use client';

import { use, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import Header from '@/components/Header';
import Footer from '@/components/Footer';
import LoadingSpinner from '@/components/LoadingSpinner';
import TailoredResultView from '@/components/TailoredResultView';
import PdfPreview from '@/components/PdfPreview';
import { useAuth } from '@/lib/supabase/auth-context';
import { createClient } from '@/lib/supabase/client';
import { getGeneratedResume, downloadGeneratedResume, GeneratedResumeRow } from '@/lib/supabase/resumes';
import type { JobDescription } from '@/types/resume';

export default function TailoredResumeDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { user } = useAuth();
  const supabase = createClient();

  const [row, setRow] = useState<GeneratedResumeRow | null>(null);
  const [pdfUrl, setPdfUrl] = useState('');
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!user) return;
    let objectUrl = '';

    getGeneratedResume(supabase, id).then(async (result) => {
      if (!result) {
        setNotFound(true);
        setLoading(false);
        return;
      }
      setRow(result);

      const blob = await downloadGeneratedResume(supabase, result.pdf_storage_path);
      if (blob) {
        objectUrl = URL.createObjectURL(blob);
        setPdfUrl(objectUrl);
      }
      setLoading(false);
    });

    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, id]);

  const goBack = () => router.push('/tailored');

  if (loading || !user) {
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1 flex items-center justify-center">
          <LoadingSpinner message="Loading result..." />
        </main>
        <Footer />
      </div>
    );
  }

  if (notFound || !row) {
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1 flex flex-col items-center justify-center gap-4 py-20">
          <p className="text-black/50 text-[15px]">This tailored resume couldn&apos;t be found.</p>
          <button
            onClick={goBack}
            className="inline-flex items-center gap-2 bg-[#187fe7] hover:bg-[#146bc7] text-white font-medium px-6 py-3.5 rounded-[14px] shadow-[0px_4px_2px_rgba(0,0,0,0.25)] transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to history
          </button>
        </main>
        <Footer />
      </div>
    );
  }

  const compatibility = row.tailoring_options?.compatibility ?? null;
  const resumeSkills = row.tailoring_options?.resume_skills ?? [];

  if (!compatibility) {
    // Pre-Phase-1 row: only the PDF and basic metadata were ever saved.
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1 py-12 px-4">
          <div className="container mx-auto max-w-4xl space-y-6">
            <div>
              <h1 className="font-bold text-[28px] sm:text-[36px] leading-[1.05] tracking-[-0.96px] text-black mb-2">
                {row.job_title || 'Tailored Resume'}
              </h1>
              <p className="text-[15px] text-black/50">
                {row.company ? `${row.company} · ` : ''}
                {new Date(row.created_at).toLocaleDateString(undefined, {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </p>
            </div>

            <div className="bg-amber-500/10 border border-amber-500/25 text-amber-800 rounded p-4 text-[14px]">
              A detailed skill breakdown isn&apos;t available for this tailor — it was saved before we started
              tracking that. You can still preview and download the PDF below.
            </div>

            <div className="bg-[#fffcfc] border border-black rounded overflow-hidden">
              {pdfUrl ? (
                <PdfPreview url={pdfUrl} mode="scroll" className="w-full h-[850px]" />
              ) : (
                <p className="text-center text-black/40 text-[14px] py-20">Couldn&apos;t load the PDF preview.</p>
              )}
            </div>

            <button
              onClick={goBack}
              className="inline-flex items-center gap-2 border border-black text-black hover:bg-black/5 font-medium px-6 py-3.5 rounded-[14px] transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to history
            </button>
          </div>
        </main>
        <Footer />
      </div>
    );
  }

  const jobDescription: JobDescription = {
    title: row.job_title ?? undefined,
    company: row.company ?? undefined,
    must_have_skills: [...compatibility.matched_must_have, ...compatibility.missing_must_have],
    nice_to_have_skills: [...compatibility.matched_nice_to_have, ...compatibility.missing_nice_to_have],
    responsibilities: [],
    keywords: [],
    raw_text: row.job_description_snapshot ?? '',
  };

  return (
    <div className="min-h-screen flex flex-col">
      <Header />

      <main className="flex-1 py-12 px-4">
        <TailoredResultView
          resumeSkills={resumeSkills}
          jobDescription={jobDescription}
          compatibility={compatibility}
          pdfUrl={pdfUrl}
          heading={row.job_title || 'Tailored Resume'}
          subheading={
            row.company
              ? `${row.company} · ${new Date(row.created_at).toLocaleDateString()}`
              : new Date(row.created_at).toLocaleDateString()
          }
          primaryAction={{ label: 'Back to history', onClick: goBack, icon: ArrowLeft }}
        />
      </main>

      <Footer />
    </div>
  );
}
