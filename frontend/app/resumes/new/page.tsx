'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import Footer from '@/components/Footer';
import FileUpload from '@/components/FileUpload';
import ErrorMessage from '@/components/ErrorMessage';
import LoadingSpinner from '@/components/LoadingSpinner';
import { createClient } from '@/lib/supabase/client';
import { useAuth } from '@/lib/supabase/auth-context';
import { uploadBaseResume, findBaseResumeByFileName, replaceBaseResume, BaseResumeRow } from '@/lib/supabase/resumes';
import {
  reformatResume,
  fetchTemplatePreview,
  base64ToFile,
  ReformatJsonResult,
  ResumeFormat,
} from '@/lib/api';

export default function NewResumePage() {
  const router = useRouter();
  const { user, displayName } = useAuth();
  const supabase = createClient();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [resumeFormat, setResumeFormat] = useState<ResumeFormat>('regular');
  const [previewUrls, setPreviewUrls] = useState<Record<ResumeFormat, string>>({ regular: '', technical: '' });
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [duplicateResume, setDuplicateResume] = useState<BaseResumeRow | null>(null);
  const [isCheckingDuplicate, setIsCheckingDuplicate] = useState(false);
  const [replaceTargetId, setReplaceTargetId] = useState<string | null>(null);

  useEffect(() => {
    let regularUrl = '';
    let technicalUrl = '';

    Promise.all([fetchTemplatePreview('regular'), fetchTemplatePreview('technical')])
      .then(([regularBlob, technicalBlob]) => {
        regularUrl = URL.createObjectURL(regularBlob);
        technicalUrl = URL.createObjectURL(technicalBlob);
        setPreviewUrls({ regular: regularUrl, technical: technicalUrl });
      })
      .catch((err) => console.error('Failed to load template previews:', err));

    return () => {
      if (regularUrl) URL.revokeObjectURL(regularUrl);
      if (technicalUrl) URL.revokeObjectURL(technicalUrl);
    };
  }, []);

  const handleFileSelect = async (file: File | null) => {
    setSelectedFile(file);
    setReplaceTargetId(null);
    setDuplicateResume(null);
    setError('');

    if (!file || !user) return;

    setIsCheckingDuplicate(true);
    try {
      const existing = await findBaseResumeByFileName(supabase, user.id, file.name);
      if (existing) {
        setDuplicateResume(existing);
      }
    } catch (err) {
      console.error('Duplicate check failed:', err);
      setError('Could not check for an existing resume with this name. Please try uploading again.');
      setSelectedFile(null);
    } finally {
      setIsCheckingDuplicate(false);
    }
  };

  const handleReplaceConfirm = () => {
    if (!duplicateResume) return;
    setReplaceTargetId(duplicateResume.id);
    setDuplicateResume(null);
  };

  const handleReplaceCancel = () => {
    setDuplicateResume(null);
    setSelectedFile(null);
  };

  const saveResume = async (replaceId: string | null) => {
    if (!selectedFile || !user) return;

    setIsSaving(true);
    setError('');

    const reformatResponse = await reformatResume({
      pdfFile: selectedFile,
      fileName: selectedFile.name,
      resumeFormat,
      outputFormat: 'json',
    });

    if (!reformatResponse.success || !reformatResponse.data) {
      setError(reformatResponse.error || 'Failed to reformat your resume. Please try again.');
      setIsSaving(false);
      return;
    }

    const { resume, inferred_skills, pdf_base64 } = reformatResponse.data as ReformatJsonResult;
    const reformattedFile = base64ToFile(pdf_base64, selectedFile.name);
    const result = replaceId
      ? await replaceBaseResume(supabase, replaceId, user.id, reformattedFile, resume, inferred_skills)
      : await uploadBaseResume(supabase, user.id, reformattedFile, resume, inferred_skills);

    if (!result) {
      setError('Failed to save your resume. Please try again.');
      setIsSaving(false);
      return;
    }

    router.push('/dashboard');
    router.refresh();
  };

  return (
    <div className="min-h-screen flex flex-col">
      <Header />

      <main className="flex-1 py-12 px-4">
        <div className="container mx-auto max-w-3xl">
          <div className="mb-8">
            <h1 className="font-bold text-[32px] sm:text-[48px] leading-[1.05] tracking-[-0.96px] text-black mb-3">
              Welcome {displayName || 'User'} !!
            </h1>
            <p className="text-[15px] tracking-[-0.3px] text-black">
              Upload a PDF and we&apos;ll reformat it into a clean, ATS-friendly resume saved to your account.
            </p>
          </div>

          {error && (
            <div className="mb-6">
              <ErrorMessage message={error} onRetry={() => setError('')} />
            </div>
          )}

          <div className="mb-8">
            {isSaving ? (
              <div className="bg-[#fffcfc] border border-[#504b4b] rounded-[4px] p-8">
                <LoadingSpinner message="Reformatting your resume..." submessage="This usually finishes in under a minute." />
              </div>
            ) : (
              <FileUpload selectedFile={selectedFile} onFileSelect={handleFileSelect} />
            )}
          </div>

          {!isSaving && selectedFile && isCheckingDuplicate && (
            <p className="text-sm text-gray-500 mb-8">Checking your saved resumes...</p>
          )}

          {!isSaving && selectedFile && !isCheckingDuplicate && !duplicateResume && (
            <>
              <div className="bg-[#fffcfc] border border-[#504b4b] rounded-[4px] p-8 mb-8">
                <div className="mb-6">
                  <h2 className="font-semibold text-[24px] tracking-[-0.48px] text-black mb-2">Choose a Template</h2>
                  <p className="text-[15px] tracking-[-0.3px] text-black">Pick how your resume should be formatted</p>
                </div>

                <div className="flex w-full rounded-[14px] border border-black overflow-hidden mb-6">
                  <button
                    type="button"
                    onClick={() => setResumeFormat('regular')}
                    className={`flex-1 py-4 text-center font-semibold text-[16px] border-r border-black transition-colors cursor-pointer ${
                      resumeFormat === 'regular' ? 'bg-[#187fe7] text-white' : 'bg-white text-black hover:bg-gray-50'
                    }`}
                  >
                    Regular
                  </button>
                  <button
                    type="button"
                    onClick={() => setResumeFormat('technical')}
                    className={`flex-1 py-4 text-center font-semibold text-[16px] transition-colors cursor-pointer ${
                      resumeFormat === 'technical' ? 'bg-[#187fe7] text-white' : 'bg-white text-black hover:bg-gray-50'
                    }`}
                  >
                    Technical
                  </button>
                </div>

                {previewUrls[resumeFormat] ? (
                  <div>
                    <p className="font-semibold text-[15px] tracking-[-0.3px] text-black mb-2">
                      Sample {resumeFormat === 'regular' ? 'Regular' : 'Technical'} template
                    </p>
                    <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
                      <iframe
                        src={`${previewUrls[resumeFormat]}#view=FitH&toolbar=0&navpanes=0&scrollbar=1`}
                        className="w-full h-[500px] border-0"
                        title={`${resumeFormat} template sample`}
                      />
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">Loading sample previews...</p>
                )}
              </div>

              <div className="text-center">
                <button
                  onClick={() => saveResume(replaceTargetId)}
                  disabled={isSaving}
                  className="inline-flex items-center justify-center gap-3 bg-[#187fe7] hover:bg-[#146bc7] text-white px-10 py-4 rounded-[14px] font-semibold text-lg shadow-[0px_4px_2px_rgba(0,0,0,0.25)] transition-colors cursor-pointer"
                >
                  Save Resume
                </button>
              </div>
            </>
          )}
        </div>
      </main>

      {duplicateResume && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 px-4">
          <div className="bg-[#fffcfc] border border-black rounded-[4px] p-6 sm:p-8 max-w-md w-full">
            <p className="font-bold text-[18px] tracking-[-0.36px] text-black mb-2">
              Replace existing resume?
            </p>
            <p className="text-[14px] tracking-[-0.28px] text-black/70 mb-6">
              You already have a resume named &quot;{duplicateResume.title}&quot;. Replacing it
              will overwrite its saved file and data - past tailored resumes generated from it
              stay linked to the new version. This can&apos;t be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={handleReplaceCancel}
                className="px-5 py-2.5 rounded-[14px] text-[14px] text-black hover:bg-gray-100 transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleReplaceConfirm}
                className="bg-[#187fe7] hover:bg-[#146bc7] text-white px-5 py-2.5 rounded-[14px] text-[14px] font-semibold transition-colors cursor-pointer"
              >
                Replace
              </button>
            </div>
          </div>
        </div>
      )}

      <Footer />
    </div>
  );
}
