'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import Header from '@/components/Header';
import Footer from '@/components/Footer';
import LoadingSpinner from '@/components/LoadingSpinner';
import PdfPreview from '@/components/PdfPreview';
import { useAuth } from '@/lib/supabase/auth-context';
import { createClient } from '@/lib/supabase/client';
import { listBaseResumes, downloadBaseResume, listGeneratedResumes, BaseResumeRow, GeneratedResumeRow } from '@/lib/supabase/resumes';
import { downloadPDF } from '@/lib/api';
import DashboardStats from '@/components/DashboardStats';
import SkillsInsights from '@/components/SkillsInsights';
import { Plus, Download, ChevronDown, X } from 'lucide-react';

export default function DashboardPage() {
  const { user } = useAuth();
  const supabase = createClient();
  const [resumes, setResumes] = useState<BaseResumeRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedResumeId, setSelectedResumeId] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [generatedResumes, setGeneratedResumes] = useState<GeneratedResumeRow[]>([]);
  const [statsLoading, setStatsLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    listBaseResumes(supabase, user.id).then((rows) => {
      setResumes(rows);
      setSelectedResumeId(rows[0]?.id ?? null);
      setLoading(false);
    });
    listGeneratedResumes(supabase, user.id).then((rows) => {
      setGeneratedResumes(rows);
      setStatsLoading(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  const selectedResume = resumes.find((r) => r.id === selectedResumeId) ?? null;

  const handleDownload = async () => {
    if (!previewUrl || !selectedResume) return;
    const blob = await fetch(previewUrl).then((res) => res.blob());
    downloadPDF(blob, selectedResume.file_name ?? selectedResume.title);
  };

  useEffect(() => {
    if (!selectedResume) return;

    let objectUrl = '';
    setPreviewLoading(true);

    downloadBaseResume(supabase, selectedResume.storage_path).then((blob) => {
      if (blob) {
        objectUrl = URL.createObjectURL(blob);
        setPreviewUrl(objectUrl);
      }
      setPreviewLoading(false);
    });

    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedResume?.id]);

  useEffect(() => {
    if (!expanded) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setExpanded(false);
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [expanded]);

  return (
    <div className="min-h-screen flex flex-col">
      <Header />

      <main className="flex-1 py-16 px-6 md:px-10">
        <div className="container mx-auto max-w-6xl">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-6 mb-10 sm:mb-16">
            <h1 className="font-bold text-[28px] sm:text-[36px] md:text-[44px] lg:text-[48px] leading-[1.05] tracking-[-0.96px] text-black">
              Resume Board
            </h1>
            <div className="flex items-center gap-3 flex-shrink-0 self-start">
              <Link
                href="/tailored"
                className="inline-flex items-center gap-2 text-black font-medium text-[16px] px-6 py-3.5 rounded-[14px] border border-black hover:bg-black/5 transition-colors"
              >
                Tailored History
              </Link>
              <Link
                href="/resumes/new"
                className="inline-flex items-center gap-2 bg-[#187fe7] hover:bg-[#146bc7] text-white font-medium text-[16px] px-6 py-3.5 rounded-[14px] shadow-[0px_4px_2px_rgba(0,0,0,0.25)] transition-colors"
              >
                Add New Resume
                <Plus className="w-4 h-4" />
              </Link>
            </div>
          </div>

          <div className="flex flex-col lg:flex-row gap-8">
            {/* Left: resume view */}
            <div className="w-full lg:w-[360px] flex-shrink-0 flex flex-col gap-8">
              <div className="bg-[#fffcfc] border border-black rounded">
                <div className="flex items-center justify-between border-b border-black px-4 h-[50px] sm:h-[58px]">
                  {loading ? (
                    <span className="text-sm text-black/50">Loading…</span>
                  ) : resumes.length > 0 ? (
                    <div className="relative">
                      <select
                        value={selectedResumeId ?? ''}
                        onChange={(e) => setSelectedResumeId(e.target.value)}
                        className="appearance-none bg-transparent text-[14px] font-medium text-black pr-6 focus:outline-none cursor-pointer max-w-[160px] truncate"
                      >
                        {resumes.map((resume) => (
                          <option key={resume.id} value={resume.id}>
                            {resume.file_name ?? resume.title}
                          </option>
                        ))}
                      </select>
                      <ChevronDown className="w-3.5 h-3.5 text-black absolute right-0 top-1/2 -translate-y-1/2 pointer-events-none" />
                    </div>
                  ) : (
                    <span className="text-sm text-black/50">No resumes yet</span>
                  )}

                  <button
                    onClick={handleDownload}
                    disabled={!previewUrl}
                    className="inline-flex items-center gap-1.5 text-[10px] font-medium text-black hover:text-[#187fe7] disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex-shrink-0"
                  >
                    <Download className="w-3 h-3" />
                    Download
                  </button>
                </div>

                <div className="p-2">
                  {!loading && resumes.length === 0 ? (
                    <div className="py-16 text-center">
                      <p className="text-sm text-black/50">
                        Add a resume to see it here.
                      </p>
                    </div>
                  ) : previewLoading ? (
                    <div className="py-16">
                      <LoadingSpinner message="Loading resume..." />
                    </div>
                  ) : previewUrl ? (
                    <div
                      onClick={() => setExpanded(true)}
                      className="relative w-full aspect-[8.5/11] cursor-pointer group overflow-hidden"
                    >
                      <PdfPreview url={previewUrl} mode="fit" className="w-full h-full" />
                      <div className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/30 transition-colors">
                        <span className="opacity-0 group-hover:opacity-100 transition-opacity bg-white text-black text-xs font-medium px-3 py-1.5 rounded-full shadow">
                          Click to expand
                        </span>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-black/50 text-center py-16">Couldn&apos;t load a preview.</p>
                  )}
                </div>
              </div>

              <SkillsInsights rows={generatedResumes} loading={statsLoading} />
            </div>

            {/* Right: application stats */}
            <DashboardStats rows={generatedResumes} baseResumeCount={resumes.length} loading={statsLoading} />
          </div>
        </div>
      </main>

      {expanded && previewUrl && (
        <div
          onClick={() => setExpanded(false)}
          className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-lg shadow-2xl aspect-[8.5/11] h-[96vh] max-w-[96vw] flex flex-col overflow-hidden"
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 flex-shrink-0">
              <span className="text-sm font-medium text-gray-900 truncate">
                {selectedResume?.file_name ?? selectedResume?.title}
              </span>
              <button
                onClick={() => setExpanded(false)}
                className="text-gray-500 hover:text-gray-800 cursor-pointer flex-shrink-0"
                aria-label="Close"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <PdfPreview url={previewUrl} mode="scroll" className="w-full flex-1" />
          </div>
        </div>
      )}

      <Footer />
    </div>
  );
}
