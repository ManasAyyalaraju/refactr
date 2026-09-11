'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import Header from '@/components/Header';
import Footer from '@/components/Footer';
import JobDescriptionInput from '@/components/JobDescriptionInput';
import LoadingSpinner from '@/components/LoadingSpinner';
import ErrorMessage from '@/components/ErrorMessage';
import { Sparkles, Wand2, FileText, Code2 } from 'lucide-react';
import { tailorResume, reformatResume, parseJobDescription, ResumeFormat, SkillMatch } from '@/lib/api';
import { createClient } from '@/lib/supabase/client';
import { useAuth } from '@/lib/supabase/auth-context';
import { listBaseResumes, downloadBaseResume, uploadGeneratedResume, BaseResumeRow } from '@/lib/supabase/resumes';
import type { Resume, TailoredResult } from '@/types/resume';

type FlowTab = 'tailor' | 'reformat';

export default function TailorPage() {
  return (
    <Suspense fallback={null}>
      <TailorPageInner />
    </Suspense>
  );
}

function TailorPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const supabase = createClient();

  const [activeTab, setActiveTab] = useState<FlowTab>('tailor');
  const [resumes, setResumes] = useState<BaseResumeRow[]>([]);
  const [resumesLoading, setResumesLoading] = useState(true);
  const [selectedResumeId, setSelectedResumeId] = useState<string | null>(null);
  const [jobDescription, setJobDescription] = useState('');
  const [resumeFormat, setResumeFormat] = useState<ResumeFormat>('regular');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [isCheckingOverlap, setIsCheckingOverlap] = useState(false);
  const [pickerSkills, setPickerSkills] = useState<string[] | null>(null);
  const [selectedSkills, setSelectedSkills] = useState<Set<string>>(new Set());
  const [pickerSkillMatches, setPickerSkillMatches] = useState<SkillMatch[]>([]);

  const [reformatLoading, setReformatLoading] = useState(false);
  const [reformatError, setReformatError] = useState<string>('');
  const [reformatSuccess, setReformatSuccess] = useState<string>('');
  const [reformatPdfUrl, setReformatPdfUrl] = useState<string>('');

  useEffect(() => {
    if (!user) return;
    listBaseResumes(supabase, user.id).then((rows) => {
      if (rows.length === 0) {
        router.push('/resumes/new');
        return;
      }
      setResumes(rows);
      const requested = searchParams.get('resumeId');
      const preselect = requested && rows.some((r) => r.id === requested) ? requested : rows[0].id;
      setSelectedResumeId(preselect);
      setResumesLoading(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  const selectedResume = resumes.find((r) => r.id === selectedResumeId) ?? null;
  const canSubmit = selectedResume && jobDescription.length >= 100;

  const handleTabChange = (tab: FlowTab) => {
    setActiveTab(tab);
    setError('');
    setPickerSkills(null);
    setPickerSkillMatches([]);
    setReformatError('');
    setReformatSuccess('');
    if (reformatPdfUrl) {
      URL.revokeObjectURL(reformatPdfUrl);
      setReformatPdfUrl('');
    }
  };

  const handleTailorClick = async () => {
    if (!selectedResume || !jobDescription || !user) return;

    // Only resumes with inferred_skills (saved after Phase 1, or reparsed)
    // have anything to offer here - skip the check for older resumes.
    if (!selectedResume.inferred_skills || selectedResume.inferred_skills.length === 0) {
      await handleSubmit([]);
      return;
    }

    setError('');
    setIsCheckingOverlap(true);
    const jdResponse = await parseJobDescription(jobDescription, selectedResume.inferred_skills);
    setIsCheckingOverlap(false);

    if (!jdResponse.success || !jdResponse.data?.job_description) {
      // Non-critical enhancement - don't block tailoring if this check fails.
      await handleSubmit([]);
      return;
    }

    const jd = jdResponse.data.job_description;
    const explicitLower = new Set((selectedResume.parsed_data?.skills ?? []).map((s) => s.toLowerCase()));

    // Plain literal overlap (e.g. JD says "Docker", inferred_skills has "Docker").
    const jdSkillsLower = new Set(
      [...(jd.must_have_skills ?? []), ...(jd.nice_to_have_skills ?? [])].map((s) => s.toLowerCase())
    );
    const literalOverlap = selectedResume.inferred_skills.filter(
      (s) => jdSkillsLower.has(s.toLowerCase()) && !explicitLower.has(s.toLowerCase())
    );

    // Semantic overlap (e.g. JD says "data modeling techniques", candidate has
    // "hyperparameter tuning") - a JD requirement phrased more broadly than
    // any single skill's own wording, which literal matching can't catch.
    const semanticOverlap = (jdResponse.data.skill_matches ?? [])
      .flatMap((m) => m.matched_candidate_skills)
      .filter((s) => !explicitLower.has(s.toLowerCase()));

    const overlap = Array.from(new Set([...literalOverlap, ...semanticOverlap]));

    if (overlap.length === 0) {
      await handleSubmit([]);
      return;
    }

    setPickerSkills(overlap);
    // Unchecked by default - require an active, deliberate confirmation per
    // skill rather than pre-selecting everything and asking the user to opt
    // out (which is what led to over-inclusion/clutter in testing).
    setSelectedSkills(new Set());
    setPickerSkillMatches(jdResponse.data.skill_matches ?? []);
  };

  const toggleSkill = (skill: string) => {
    setSelectedSkills((prev) => {
      const next = new Set(prev);
      if (next.has(skill)) {
        next.delete(skill);
      } else {
        next.add(skill);
      }
      return next;
    });
  };

  const handleConfirmSkills = async () => {
    const chosen = pickerSkills ? pickerSkills.filter((s) => selectedSkills.has(s)) : [];
    // Credit a JD requirement (e.g. "data modeling techniques") if at least
    // one of the skills that satisfy it was actually confirmed - computed
    // from the full-pool matches already found by the earlier overlap check,
    // not re-derived against just the confirmed subset (a smaller pool
    // makes the match-judgment markedly less reliable).
    const chosenLower = new Set(chosen.map((s) => s.toLowerCase()));
    const credited = pickerSkillMatches
      .filter((m) => m.matched_candidate_skills.some((s) => chosenLower.has(s.toLowerCase())))
      .map((m) => m.jd_skill);
    setPickerSkills(null);
    await handleSubmit(chosen, credited);
  };

  const handleSubmit = async (additionalSkills: string[], creditedSkills: string[] = []) => {
    if (!selectedResume || !jobDescription || !user) return;

    setIsLoading(true);
    setError('');

    try {
      const fileName = selectedResume.file_name ?? selectedResume.title;

      // Resumes saved after Phase 1 already carry their parsed structure -
      // skip re-downloading and re-parsing the PDF entirely for those.
      let sourceParams: { pdfFile: Blob; fileName: string } | { resumeJson: Resume };
      if (selectedResume.parsed_data) {
        sourceParams = { resumeJson: selectedResume.parsed_data };
      } else {
        const pdfBlob = await downloadBaseResume(supabase, selectedResume.storage_path);
        if (!pdfBlob) {
          setError('Could not load the selected resume. Please try again.');
          return;
        }
        sourceParams = { pdfFile: pdfBlob, fileName };
      }

      // Request JSON first to get structured data
      const jsonResponse = await tailorResume({
        ...sourceParams,
        jobDescription,
        outputFormat: 'json',
        resumeFormat,
        additionalSkills,
        creditedSkills,
      });

      if (!jsonResponse.success || !jsonResponse.data) {
        setError(jsonResponse.error || 'Failed to tailor resume. Please try again.');
        return;
      }

      // Request PDF version
      const pdfResponse = await tailorResume({
        ...sourceParams,
        jobDescription,
        outputFormat: 'pdf',
        resumeFormat,
        additionalSkills,
        creditedSkills,
      });

      if (!pdfResponse.success || !pdfResponse.data) {
        setError('Failed to generate PDF. Please try again.');
        return;
      }

      // Store both JSON and PDF blob
      sessionStorage.setItem('tailoredResult', JSON.stringify(jsonResponse.data));
      sessionStorage.setItem('originalFileName', fileName);

      // Create blob URL for PDF and store it
      const tailoredPdfBlob = pdfResponse.data as Blob;
      const pdfUrl = URL.createObjectURL(tailoredPdfBlob);
      sessionStorage.setItem('pdfBlobUrl', pdfUrl);

      // Best-effort save to the user's account - never blocks navigation to /results
      const result = jsonResponse.data as TailoredResult;
      uploadGeneratedResume(supabase, user.id, {
        baseResumeId: selectedResume.id,
        pdfBlob: tailoredPdfBlob,
        jobTitle: result.job_description?.title,
        company: result.job_description?.company,
        jobDescription,
        tailoringOptions: {
          mode: 'tailor',
          score: result.compatibility?.score,
          resume_format: resumeFormat,
          compatibility: result.compatibility,
          resume_skills: result.resume?.skills,
        },
      });

      // Navigate to results page
      router.push('/results');
    } catch (err) {
      console.error('Error:', err);
      setError('An unexpected error occurred. Please check if the backend is running.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleReformatSubmit = async () => {
    if (!selectedResume || !user) return;

    setReformatLoading(true);
    setReformatError('');
    setReformatSuccess('');
    if (reformatPdfUrl) {
      URL.revokeObjectURL(reformatPdfUrl);
      setReformatPdfUrl('');
    }

    try {
      const pdfBlob = await downloadBaseResume(supabase, selectedResume.storage_path);
      if (!pdfBlob) {
        setReformatError('Could not load the selected resume. Please try again.');
        return;
      }
      const fileName = selectedResume.file_name ?? selectedResume.title;

      const pdfResponse = await reformatResume({ pdfFile: pdfBlob, fileName });

      if (!pdfResponse.success || !pdfResponse.data) {
        setReformatError(pdfResponse.error || 'Failed to reformat resume. Please try again.');
        return;
      }

      const reformattedBlob = pdfResponse.data as Blob;
      const pdfUrl = URL.createObjectURL(reformattedBlob);
      setReformatPdfUrl(pdfUrl);
      setReformatSuccess('ATS-friendly PDF is ready. You can preview or download it below.');

      // Best-effort save to the user's account - never blocks the preview
      uploadGeneratedResume(supabase, user.id, {
        baseResumeId: selectedResume.id,
        pdfBlob: reformattedBlob,
        tailoringOptions: { mode: 'reformat' },
      });
    } catch (err) {
      console.error('Error:', err);
      setReformatError('An unexpected error occurred. Please check if the backend is running.');
    } finally {
      setReformatLoading(false);
    }
  };

  const handleDownloadReformat = () => {
    if (!reformatPdfUrl) return;
    const link = document.createElement('a');
    link.href = reformatPdfUrl;
    link.download = 'ats_resume.pdf';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleRetry = () => {
    setError('');
  };

  const renderResumePicker = () => (
    <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold text-gray-800 mb-2">Your Resume</h2>
          <p className="text-gray-600">Choose which saved resume to use</p>
        </div>
        <Link
          href="/resumes/new"
          className="text-sm font-medium text-blue-600 hover:text-blue-700 whitespace-nowrap flex-shrink-0"
        >
          + Add another
        </Link>
      </div>
      <select
        value={selectedResumeId ?? ''}
        onChange={(e) => setSelectedResumeId(e.target.value)}
        className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-600 focus:border-blue-600 outline-none transition-colors"
      >
        {resumes.map((r) => (
          <option key={r.id} value={r.id}>
            {r.title}
          </option>
        ))}
      </select>
    </div>
  );

  if (!user || resumesLoading) {
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1 py-12 px-4 flex items-center justify-center">
          <LoadingSpinner message="Loading..." />
        </main>
        <Footer />
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header />

      <main className="flex-1 py-12 px-4">
        <div className="container mx-auto max-w-6xl">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center gap-2 bg-blue-100 text-blue-700 px-4 py-2 rounded-full text-sm font-medium mb-4">
              <Sparkles className="w-4 h-4" />
              Tailor or Reformat
            </div>
            <h1 className="text-4xl font-bold text-gray-800 mb-4">
              Customize Your Resume Experience
            </h1>
            <p className="text-lg text-gray-600 max-w-2xl mx-auto">
              {activeTab === 'tailor'
                ? 'Pick a saved resume and paste a job description to tailor it for that role.'
                : 'Pick a saved resume to instantly reformat it into an ATS-friendly PDF—no job description needed.'}
            </p>
          </div>

          {/* Tabs */}
          <div className="flex justify-center mb-10">
            <div className="inline-flex bg-gray-100 rounded-full p-1 shadow-inner">
              <button
                onClick={() => handleTabChange('tailor')}
                className={`px-5 py-2 rounded-full text-sm font-semibold transition-all duration-200 ${
                  activeTab === 'tailor'
                    ? 'bg-white text-blue-600 shadow'
                    : 'text-gray-600 hover:text-gray-800'
                }`}
              >
                Tailoring
              </button>
              <button
                onClick={() => handleTabChange('reformat')}
                className={`px-5 py-2 rounded-full text-sm font-semibold transition-all duration-200 ${
                  activeTab === 'reformat'
                    ? 'bg-white text-blue-600 shadow'
                    : 'text-gray-600 hover:text-gray-800'
                }`}
              >
                Reformatting
              </button>
            </div>
          </div>

          {/* Main Content */}
          {activeTab === 'tailor' ? (
            isLoading ? (
              <div className="bg-white rounded-xl shadow-lg p-12">
                <LoadingSpinner
                  message="Tailoring your resume..."
                  submessage="This may take 1-3 minutes. Please wait."
                />
              </div>
            ) : isCheckingOverlap ? (
              <div className="bg-white rounded-xl shadow-lg p-12">
                <LoadingSpinner message="Checking for matching skills..." />
              </div>
            ) : error ? (
              <div className="bg-white rounded-xl shadow-lg p-8">
                <ErrorMessage
                  message={error}
                  onRetry={handleRetry}
                />
              </div>
            ) : pickerSkills ? (
              <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
                <div className="mb-6">
                  <h2 className="text-2xl font-bold text-gray-800 mb-2">
                    Skills To Add:
                  </h2>
                  <p className="text-xs text-gray-600">
                    Based on your background these are plausible skills that match the job. These
                    aren&apos;t explicitly listed on your resume. Choose those that are actually
                    true to your background.
                  </p>
                </div>
                <div className="grid grid-cols-3 gap-3 mb-8">
                  {pickerSkills.map((skill) => {
                    const selected = selectedSkills.has(skill);
                    return (
                      <button
                        key={skill}
                        type="button"
                        onClick={() => toggleSkill(skill)}
                        className={`h-[50px] px-2 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
                          selected ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-900 hover:bg-gray-200'
                        }`}
                      >
                        {skill}
                      </button>
                    );
                  })}
                </div>
                <button
                  onClick={handleConfirmSkills}
                  className="w-full bg-blue-600 hover:bg-blue-700 text-white py-4 rounded-[14px] font-semibold text-lg shadow-[0px_4px_2px_rgba(0,0,0,0.25)] transition-colors cursor-pointer"
                >
                  Continue
                </button>
              </div>
            ) : (
              <>
                {renderResumePicker()}

                <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
                  <div className="mb-6">
                    <h2 className="text-2xl font-semibold text-gray-800 mb-2">
                      Job Description
                    </h2>
                    <p className="text-gray-600">
                      Paste the complete job description
                    </p>
                  </div>
                  <JobDescriptionInput
                    value={jobDescription}
                    onChange={setJobDescription}
                  />
                </div>

                {/* Template Choice */}
                <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
                  <div className="mb-6">
                    <h2 className="text-2xl font-semibold text-gray-800 mb-2">
                      Choose a Template
                    </h2>
                    <p className="text-gray-600">
                      Pick how your tailored resume should be formatted
                    </p>
                  </div>
                  <div className="grid sm:grid-cols-2 gap-4">
                    <button
                      type="button"
                      onClick={() => setResumeFormat('regular')}
                      className={`flex items-start gap-3 text-left p-4 rounded-lg border-2 transition-colors cursor-pointer ${
                        resumeFormat === 'regular'
                          ? 'border-blue-600 bg-blue-50'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      <FileText className={`w-6 h-6 flex-shrink-0 ${resumeFormat === 'regular' ? 'text-blue-600' : 'text-gray-400'}`} />
                      <div>
                        <p className="font-semibold text-gray-800">Regular</p>
                        <p className="text-sm text-gray-600">
                          Classic single-line skills format. Best for most roles.
                        </p>
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setResumeFormat('technical')}
                      className={`flex items-start gap-3 text-left p-4 rounded-lg border-2 transition-colors cursor-pointer ${
                        resumeFormat === 'technical'
                          ? 'border-blue-600 bg-blue-50'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      <Code2 className={`w-6 h-6 flex-shrink-0 ${resumeFormat === 'technical' ? 'text-blue-600' : 'text-gray-400'}`} />
                      <div>
                        <p className="font-semibold text-gray-800">Technical</p>
                        <p className="text-sm text-gray-600">
                          Adds a categorized Technical Skills section (e.g. Languages, Software, Certifications). Best for engineering/technical roles.
                        </p>
                      </div>
                    </button>
                  </div>
                </div>

                {/* Submit Button */}
                <div className="text-center">
                  <button
                    onClick={handleTailorClick}
                    disabled={!canSubmit}
                    className={`
                      inline-flex items-center justify-center gap-3
                      px-12 py-5 rounded-xl font-semibold text-lg
                      shadow-lg hover:shadow-xl
                      transition-all duration-200
                      ${canSubmit
                        ? 'bg-blue-600 hover:bg-blue-700 text-white cursor-pointer transform hover:scale-105'
                        : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                      }
                    `}
                  >
                    Tailor My Resume
                  </button>

                  {!canSubmit && (
                    <p className="mt-4 text-sm text-gray-500">
                      Please provide a job description (min 100 characters)
                    </p>
                  )}
                </div>

                {/* Info Box */}
                <div className="mt-12 bg-blue-50 border border-blue-200 rounded-lg p-6">
                  <h3 className="font-semibold text-gray-800 mb-2">
                    💡 Tips for best tailoring results:
                  </h3>
                  <ul className="space-y-2 text-sm text-gray-700">
                    <li>• Use a well-formatted PDF resume with clear sections</li>
                    <li>• Include the complete job description with requirements and responsibilities</li>
                    <li>• The more detailed the job description, the better the tailoring</li>
                    <li>• Processing typically takes 1-3 minutes depending on resume length</li>
                  </ul>
                </div>
              </>
            )
          ) : reformatLoading ? (
            <div className="bg-white rounded-xl shadow-lg p-12">
              <LoadingSpinner
                message="Reformatting your resume..."
                submessage="This usually finishes in under a minute."
              />
            </div>
          ) : reformatError ? (
            <div className="bg-white rounded-xl shadow-lg p-8">
              <ErrorMessage
                message={reformatError}
                onRetry={() => setReformatError('')}
              />
            </div>
          ) : (
            <>
              {renderResumePicker()}

              <div className="bg-white rounded-xl shadow-lg p-8">
                <div className="mb-6">
                  <h2 className="text-2xl font-semibold text-gray-800 mb-2 flex items-center gap-2">
                    <Wand2 className="w-6 h-6 text-blue-600" />
                    Reformat Your Resume
                  </h2>
                  <p className="text-gray-600">
                    Instantly generate an ATS-friendly, clean PDF from your selected resume without changing its content.
                  </p>
                </div>

                <div className="text-center">
                  <button
                    onClick={handleReformatSubmit}
                    disabled={!selectedResume || reformatLoading}
                    className={`
                      inline-flex items-center justify-center gap-3
                      px-12 py-5 rounded-xl font-semibold text-lg
                      shadow-lg hover:shadow-xl
                      transition-all duration-200
                      ${selectedResume && !reformatLoading
                        ? 'bg-blue-600 hover:bg-blue-700 text-white cursor-pointer transform hover:scale-105'
                        : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                      }
                    `}
                  >
                    <Wand2 className="w-6 h-6" />
                    Reformat My Resume
                  </button>
                </div>

                {reformatSuccess && (
                  <div className="mt-6 bg-green-50 border border-green-200 text-green-700 rounded-lg p-4 text-sm text-center">
                    {reformatSuccess}
                  </div>
                )}
              </div>

              {/* Info Box */}

                {reformatPdfUrl && (
                  <div className="mt-8 bg-gradient-to-br from-gray-50 to-white border border-gray-200 rounded-lg shadow-lg overflow-hidden">
                    <div className="bg-blue-600 px-6 py-4 flex items-center justify-between">
                      <div className="text-white font-semibold">ATS-friendly PDF Preview</div>
                      <button
                        onClick={handleDownloadReformat}
                        className="inline-flex items-center gap-2 bg-white/90 hover:bg-white text-blue-700 font-semibold px-4 py-2 rounded-lg shadow"
                      >
                        Download PDF
                      </button>
                    </div>
                    <div className="p-4 md:p-6">
                      <div className="bg-white rounded-lg shadow-inner overflow-hidden">
                        <iframe
                          src={`${reformatPdfUrl}#view=FitH&toolbar=0&navpanes=0&scrollbar=1`}
                          className="w-full h-[750px] border-0"
                          title="Reformatted Resume PDF Preview"
                        />
                      </div>
                    </div>
                  </div>
                )}
              <div className="mt-8 bg-blue-50 border border-blue-200 rounded-lg p-6">
                <h3 className="font-semibold text-gray-800 mb-2">
                  💡 Tips for ATS-friendly formatting:
                </h3>
                <ul className="space-y-2 text-sm text-gray-700">
                  <li>• Use clear section headings like Education, Experience, and Skills</li>
                  <li>• Keep bullet points concise and avoid images or tables</li>
                  <li>• Ensure contact information is present at the top of your resume</li>
                  <li>• Double-check the downloaded PDF before submitting applications</li>
                </ul>
              </div>
            </>
          )}
        </div>
      </main>

      <Footer />
    </div>
  );
}
