'use client';

import { useEffect, useState } from 'react';
import { Download, FileText, CheckCircle2, AlertTriangle, Plus, type LucideIcon, RefreshCw, ArrowUp } from 'lucide-react';
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

const RING_SIZE = 132;
const RING_STROKE = 10;
const RING_RADIUS = (RING_SIZE - RING_STROKE) / 2;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

// Burst of dots around the ring when the count-up lands - alternating the
// app blue and the improvement green, at slightly varied distances so it
// doesn't read as a perfect circle.
const PARTICLES = Array.from({ length: 16 }, (_, i) => {
  const angle = (i / 16) * Math.PI * 2 + (i % 2 ? 0.12 : -0.08);
  const distance = RING_SIZE / 2 + 26 + (i % 3) * 9;
  return {
    dx: Math.cos(angle) * distance,
    dy: Math.sin(angle) * distance,
    size: i % 3 === 0 ? 5 : 4,
    color: i % 3 === 1 ? '#1e9e5a' : '#187fe7',
    delay: (i % 4) * 40,
  };
});

// Split out so the per-frame count-up only re-renders the ring, not the
// whole results view (PDF preview included) - that re-render was the stutter.
function ScoreRing({ score, originalScore }: { score: number; originalScore?: number }) {
  // Only animate a genuine improvement - equal or lower just shows the final score.
  const improvement = originalScore !== undefined && score > originalScore ? score - originalScore : 0;
  const { value, done } = useCountUp(improvement ? originalScore! : score, score);
  const dashOffset = RING_CIRCUMFERENCE * (1 - Math.min(100, Math.max(0, value)) / 100);
  const celebrate = improvement > 0 && done;

  return (
    <div
      className={`relative flex-shrink-0 animate-score-ring-in ${improvement > 0 ? 'mr-12' : ''}`}
      style={{ width: RING_SIZE, height: RING_SIZE }}
    >
      {celebrate && (
        <>
          <div className="absolute -inset-1 rounded-full border-[10px] border-[#187fe7]/30 blur-[6px] pointer-events-none animate-score-ring-glow" />
          {PARTICLES.map((p, i) => (
            <span
              key={i}
              className="absolute left-1/2 top-1/2 rounded-full pointer-events-none animate-score-particle"
              style={
                {
                  width: p.size,
                  height: p.size,
                  background: p.color,
                  animationDelay: `${p.delay}ms`,
                  '--dx': `${p.dx}px`,
                  '--dy': `${p.dy}px`,
                } as React.CSSProperties
              }
            />
          ))}
        </>
      )}

      <svg width={RING_SIZE} height={RING_SIZE} viewBox={`0 0 ${RING_SIZE} ${RING_SIZE}`} className="-rotate-90">
        <defs>
          <linearGradient id="score-ring-gradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#4a9ff0" />
            <stop offset="100%" stopColor="#187fe7" />
          </linearGradient>
        </defs>
        <circle
          cx={RING_SIZE / 2}
          cy={RING_SIZE / 2}
          r={RING_RADIUS}
          fill="none"
          stroke="#187fe7"
          strokeOpacity={0.1}
          strokeWidth={RING_STROKE}
        />
        <circle
          cx={RING_SIZE / 2}
          cy={RING_SIZE / 2}
          r={RING_RADIUS}
          fill="none"
          stroke="url(#score-ring-gradient)"
          strokeWidth={RING_STROKE}
          strokeLinecap="round"
          strokeDasharray={RING_CIRCUMFERENCE}
          strokeDashoffset={dashOffset}
        />
      </svg>

      <div className="absolute inset-0 flex items-center justify-center">
        <span
          className={`${
            Math.round(value) >= 100 ? 'text-[36px]' : 'text-[42px]'
          } leading-none font-(family-name:--font-archivo-black) font-normal text-[#187fe7] tabular-nums`}
        >
          {Math.round(value)}
          <span className="text-[0.5em] ml-[0.08em]">%</span>
        </span>
      </div>

      {celebrate && (
        // Tilt lives on this wrapper: the pop animation on the pill animates
        // `transform` itself and would override a rotate on the same element.
        <span className="absolute -top-3 -right-10 -rotate-[8deg]">
          <span
            className="inline-flex items-center gap-0.5 px-2.5 py-1 rounded-full bg-[#1e9e5a] text-white text-[13px] font-bold shadow-[0_2px_8px_rgba(30,158,90,0.35)] origin-bottom-left animate-score-badge-pop"
            aria-label={`Up ${improvement} points from ${originalScore} before tailoring`}
          >
            <ArrowUp className="w-3.5 h-3.5" strokeWidth={3} />
            {improvement}
          </span>
        </span>
      )}
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
            <div className="flex flex-col sm:flex-row sm:items-center gap-6 sm:gap-8">
              <ScoreRing score={score} originalScore={compatibility?.original_score} />
              <div>
                <p className="text-[13px] font-semibold text-[#187fe7] uppercase tracking-wide mb-2">Compatibility Overview</p>
                <h2 className="text-[30px] leading-tight font-bold text-black mb-2">{theme.label}</h2>
                <p className="text-black/50 text-[15px]">
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

          <div className="mt-8 grid sm:grid-cols-3 gap-4">
            {[
              { label: 'Must-have coverage', value: `${Math.round((compatibility?.must_coverage || 0) * 100)}%` },
              { label: 'Nice-to-have coverage', value: `${Math.round((compatibility?.nice_coverage || 0) * 100)}%` },
              { label: 'Resume skills listed', value: resumeSkills.length },
            ].map((stat) => (
              <div key={stat.label} className="border border-black/[0.15] rounded-lg px-5 py-4 bg-black/[0.02]">
                <p className="text-[13px] font-semibold text-black/50 mb-1.5">{stat.label}</p>
                <p className="text-[22px] leading-tight font-semibold text-black">{stat.value}</p>
              </div>
            ))}
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
