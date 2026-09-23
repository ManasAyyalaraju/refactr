'use client';

import { useEffect, useState } from 'react';
import { Download, FileText, CheckCircle2, AlertTriangle, Plus, type LucideIcon, RefreshCw } from 'lucide-react';
import type { CompatibilityReport, JobDescription } from '@/types/resume';
import PdfPreview from './PdfPreview';

interface TailoredResultViewProps {
  resumeSkills: string[];
  jobDescription?: JobDescription;
  compatibility: CompatibilityReport | null;
  pdfUrl: string;
  primaryAction: { label: string; onClick: () => void; icon?: LucideIcon };
  heading?: string;
  subheading?: string;
}

function sanitizeFilenamePart(value: string): string {
  return value.replace(/[\\/:*?"<>|]/g, '').trim();
}

// "Company - Job Title - Resume.pdf" instead of a generic name, so a user
// tailoring against multiple jobs can tell their downloads apart. Falls back
// gracefully when the JD didn't have a company/title parsed out.
function buildTailoredResumeFilename(jobDescription?: JobDescription): string {
  const parts = [jobDescription?.company, jobDescription?.title]
    .filter((v): v is string => Boolean(v && v.trim()))
    .map(sanitizeFilenamePart)
    .filter(Boolean);

  if (parts.length === 0) return 'Tailored Resume.pdf';
  return `${[...parts, 'Resume'].join(' - ')}.pdf`;
}

function scoreTheme(score: number) {
  if (score >= 80) return { ring: '#1e9e5a', label: 'Strong Match' };
  if (score >= 60) return { ring: '#d97706', label: 'Solid Alignment' };
  return { ring: '#dc2626', label: 'Needs Attention' };
}

const COUNT_UP_DELAY_MS = 700;
// Paced per point so small and large jumps both read as a steady climb.
const COUNT_UP_MS_PER_POINT = 90;
const COUNT_UP_MIN_MS = 1500;
const COUNT_UP_MAX_MS = 3200;

function countUpDuration(from: number, to: number): number {
  return Math.min(COUNT_UP_MAX_MS, Math.max(COUNT_UP_MIN_MS, Math.abs(to - from) * COUNT_UP_MS_PER_POINT));
}

// Gentle start and finish - no burst of skipped numbers at the beginning.
function easeInOutSine(t: number): number {
  return -(Math.cos(Math.PI * t) - 1) / 2;
}

// Holds on `from` briefly so the pre-tailoring score registers, then eases
// up to `to`. Returns the unrounded value (for a smooth ring sweep) and
// whether it has finished.
function useCountUp(from: number, to: number): { value: number; done: boolean } {
  // Animation progress, 0 -> 1. Only ever set from timer/frame callbacks.
  const [progress, setProgress] = useState(0);
  const animate = from !== to;

  useEffect(() => {
    if (!animate) return;
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const duration = countUpDuration(from, to);
    let frame = 0;
    let start: number | null = null;
    const tick = (now: number) => {
      if (start === null) start = now;
      const t = Math.min(1, (now - start) / duration);
      setProgress(t);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    const timer = setTimeout(
      () => {
        if (reduceMotion) setProgress(1);
        else frame = requestAnimationFrame(tick);
      },
      reduceMotion ? 0 : COUNT_UP_DELAY_MS
    );

    return () => {
      clearTimeout(timer);
      cancelAnimationFrame(frame);
    };
  }, [animate, from, to]);

  if (!animate) return { value: to, done: true };
  return { value: from + (to - from) * easeInOutSine(progress), done: progress >= 1 };
}

// Split out so the per-frame count-up only re-renders the ring, not the
// whole results view (PDF preview included) - that re-render was the stutter.
function ScoreRing({ score, originalScore }: { score: number; originalScore?: number }) {
  // Only animate a genuine improvement - equal or lower just shows the final score.
  const improvement = originalScore !== undefined && score > originalScore ? score - originalScore : 0;
  const { value, done } = useCountUp(improvement ? originalScore! : score, score);
  const scoreAngle = `${(value / 100) * 360}deg`;
  const ringColor = scoreTheme(Math.round(value)).ring;

  return (
    <div className="relative w-24 h-24 flex-shrink-0">
      <div
        className="absolute inset-0 rounded-full"
        style={{
          background: `conic-gradient(${ringColor} 0deg, ${ringColor} ${scoreAngle}, rgba(0,0,0,0.08) ${scoreAngle})`,
        }}
      />
      <div className="absolute inset-2 rounded-full bg-[#fffcfc] border border-black/10 flex flex-col items-center justify-center text-center">
        <span className="relative text-2xl font-bold text-black tabular-nums">
          {Math.round(value)}
          {improvement > 0 && (
            <span
              className={`absolute left-full top-0.5 ml-0.5 text-[11px] font-semibold text-[#1e9e5a] whitespace-nowrap transition-all duration-700 ease-out ${
                done ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-1'
              }`}
              aria-label={`Up ${improvement} points from ${originalScore} before tailoring`}
            >
              &uarr;{improvement}
            </span>
          )}
        </span>
        <span className="text-[10px] text-black/40 uppercase tracking-wide">Score</span>
      </div>
    </div>
  );
}

function MatchedChip({ skill }: { skill: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[13px] font-medium bg-[#187fe7]/10 text-[#187fe7] border border-[#187fe7]/25">
      {skill}
      <CheckCircle2 className="w-3.5 h-3.5" />
    </span>
  );
}

function GapChip({ skill }: { skill: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[13px] font-medium bg-amber-500/10 text-amber-700 border border-amber-500/25">
      {skill}
      <AlertTriangle className="w-3.5 h-3.5" />
    </span>
  );
}

function NeutralChip({ skill }: { skill: string }) {
  return (
    <span className="inline-flex items-center px-3 py-1.5 rounded-full text-[13px] font-medium bg-black/[0.04] text-black/60 border border-black/10">
      {skill}
    </span>
  );
}

export default function TailoredResultView({
  resumeSkills,
  jobDescription,
  compatibility,
  pdfUrl,
  primaryAction,
  heading = 'Your Tailored Resume is Ready',
  subheading = 'Skill-by-skill comparison against the job description with a compatibility score.',
}: TailoredResultViewProps) {
  const [isDownloading, setIsDownloading] = useState(false);

  const jdMust = jobDescription?.must_have_skills || [];
  const jdNice = jobDescription?.nice_to_have_skills || [];

  const matchedResumeSkillSet = new Set(compatibility?.resume_skill_hits || []);
  const matchedMustSet = new Set(compatibility?.matched_must_have || []);
  const matchedNiceSet = new Set(compatibility?.matched_nice_to_have || []);

  const PrimaryIcon = primaryAction.icon ?? RefreshCw;

  const handleDownloadPDF = async () => {
    if (!pdfUrl) return;

    setIsDownloading(true);
    try {
      const link = document.createElement('a');
      link.href = pdfUrl;
      link.download = buildTailoredResumeFilename(jobDescription);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (error) {
      console.error('Error downloading PDF:', error);
      alert('Failed to download PDF. Please try again.');
    } finally {
      setIsDownloading(false);
    }
  };

  const score = compatibility?.score ?? 0;
  const theme = scoreTheme(score);

  return (
    <div className="container mx-auto max-w-6xl space-y-8">
      <div>
        <h1 className="font-bold text-[28px] sm:text-[36px] leading-[1.05] tracking-[-0.96px] text-black mb-2">
          {heading}
        </h1>
        <p className="text-[15px] text-black/50">{subheading}</p>
      </div>

      {/* Compatibility + Actions */}
      <div className="bg-[#fffcfc] border border-black rounded">
        <div className="p-6 sm:p-8">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-8">
            <div className="flex items-center gap-6">
              <ScoreRing score={score} originalScore={compatibility?.original_score} />
              <div>
                <p className="text-[13px] font-semibold text-[#187fe7] mb-1">Compatibility Overview</p>
                <h2 className="text-[22px] font-bold text-black mb-1">{theme.label}</h2>
                <p className="text-black/50 text-[14px]">
                  {compatibility?.matched_must_have.length ?? 0} / {jdMust.length} required skills matched ·{' '}
                  {compatibility?.matched_nice_to_have.length ?? 0} / {jdNice.length} nice-to-haves matched
                </p>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
              <button
                onClick={primaryAction.onClick}
                className="inline-flex items-center justify-center gap-2 border border-black text-black hover:bg-black/5 font-medium px-6 py-3.5 rounded-[14px] transition-colors"
              >
                <PrimaryIcon className="w-4 h-4" />
                {primaryAction.label}
              </button>
            </div>
          </div>

          <div className="mt-6 grid sm:grid-cols-3 gap-3">
            <div className="border border-black/[0.15] rounded-lg p-4 bg-black/[0.02]">
              <p className="text-[12px] font-semibold text-black/50 mb-1">Must-have coverage</p>
              <p className="text-2xl font-bold text-black">
                {Math.round((compatibility?.must_coverage || 0) * 100)}%
              </p>
            </div>
            <div className="border border-black/[0.15] rounded-lg p-4 bg-black/[0.02]">
              <p className="text-[12px] font-semibold text-black/50 mb-1">Nice-to-have coverage</p>
              <p className="text-2xl font-bold text-black">
                {Math.round((compatibility?.nice_coverage || 0) * 100)}%
              </p>
            </div>
            <div className="border border-black/[0.15] rounded-lg p-4 bg-black/[0.02]">
              <p className="text-[12px] font-semibold text-black/50 mb-1">Resume skills listed</p>
              <p className="text-2xl font-bold text-black">{resumeSkills.length}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Skills comparison */}
      <div className="grid md:grid-cols-2 gap-6">
        <div className="bg-[#fffcfc] border border-black rounded">
          <div className="flex items-center justify-between border-b border-black px-6 h-[50px] sm:h-[58px]">
            <div>
              <h3 className="text-[16px] font-semibold text-black">Resume Skills</h3>
              <p className="text-[11px] text-black/40 -mt-0.5">From your resume</p>
            </div>
            <span className="text-[11px] px-2.5 py-1 rounded-full bg-black/5 text-black/60 flex-shrink-0">
              {resumeSkills.length} skills
            </span>
          </div>
          <div className="p-6">
            {resumeSkills.length === 0 ? (
              <p className="text-black/40 text-[14px]">No skills detected in your resume.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {resumeSkills.map((skill) =>
                  matchedResumeSkillSet.has(skill) ? (
                    <MatchedChip key={skill} skill={skill} />
                  ) : (
                    <NeutralChip key={skill} skill={skill} />
                  )
                )}
              </div>
            )}
          </div>
        </div>

        <div className="bg-[#fffcfc] border border-black rounded">
          <div className="flex items-center justify-between border-b border-black px-6 h-[50px] sm:h-[58px]">
            <div>
              <h3 className="text-[16px] font-semibold text-black">Required Skills</h3>
              <p className="text-[11px] text-black/40 -mt-0.5">From the JD</p>
            </div>
            <span className="text-[11px] px-2.5 py-1 rounded-full bg-black/5 text-black/60 flex-shrink-0">
              {jdMust.length} must-have
            </span>
          </div>
          <div className="p-6 space-y-6">
            <div>
              {jdMust.length === 0 ? (
                <p className="text-black/40 text-[14px]">No required skills were extracted from the JD.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {jdMust.map((skill) =>
                    matchedMustSet.has(skill) ? (
                      <MatchedChip key={skill} skill={skill} />
                    ) : (
                      <GapChip key={skill} skill={skill} />
                    )
                  )}
                </div>
              )}
            </div>

            <div>
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-[13px] font-semibold text-black">Nice-to-Have Skills</h4>
                <span className="text-[11px] px-2.5 py-1 rounded-full bg-black/5 text-black/60">
                  {jdNice.length} optional
                </span>
              </div>
              {jdNice.length === 0 ? (
                <p className="text-black/40 text-[14px]">No nice-to-have skills were extracted.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {jdNice.map((skill) =>
                    matchedNiceSet.has(skill) ? (
                      <MatchedChip key={skill} skill={skill} />
                    ) : (
                      <NeutralChip key={skill} skill={skill} />
                    )
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Gaps & opportunities */}
      {(compatibility?.missing_must_have.length || compatibility?.missing_nice_to_have.length) ? (
        <div className="bg-[#fffcfc] border border-black rounded p-6 space-y-6">
          {compatibility?.missing_must_have.length ? (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="w-4 h-4 text-amber-600" />
                <h3 className="text-[15px] font-semibold text-black">Critical gaps (must-have)</h3>
              </div>
              <div className="flex flex-wrap gap-2">
                {compatibility?.missing_must_have.map((skill) => (
                  <GapChip key={skill} skill={skill} />
                ))}
              </div>
            </div>
          ) : null}

          {compatibility?.missing_nice_to_have.length ? (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Plus className="w-4 h-4 text-black/40" />
                <h3 className="text-[15px] font-semibold text-black">Nice-to-have opportunities</h3>
              </div>
              <div className="flex flex-wrap gap-2">
                {compatibility?.missing_nice_to_have.map((skill) => (
                  <NeutralChip key={skill} skill={skill} />
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Resume Preview */}
      <div className="bg-[#fffcfc] border border-black rounded overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-black px-6 h-[50px] sm:h-[58px]">
          <div className="flex items-center gap-3">
            <FileText className="w-4 h-4 text-black flex-shrink-0" />
            <h2 className="text-[16px] font-semibold text-black">Your Tailored Resume</h2>
          </div>
          <button
            onClick={handleDownloadPDF}
            disabled={!pdfUrl || isDownloading}
            className="inline-flex items-center gap-1.5 text-[13px] font-medium text-black hover:text-[#187fe7] disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex-shrink-0"
          >
            <Download className="w-3.5 h-3.5" />
            {isDownloading ? 'Downloading...' : 'Download PDF'}
          </button>
        </div>

        {pdfUrl ? (
          <div className="p-4 md:p-8 flex items-center justify-center min-h-[900px] bg-black/[0.02]">
            <div className="bg-white border border-black/10 rounded overflow-hidden w-full max-w-4xl">
              <PdfPreview url={pdfUrl} mode="scroll" className="w-full h-[850px]" />
            </div>
          </div>
        ) : (
          <div className="text-center py-20">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-full border border-black/15 mb-4">
              <FileText className="w-6 h-6 text-black/30" />
            </div>
            <p className="text-black/50 text-[15px]">PDF preview not available</p>
            <p className="text-black/30 text-[13px] mt-1">Please download the PDF to view your resume</p>
          </div>
        )}
      </div>
    </div>
  );
}
