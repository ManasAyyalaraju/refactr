import { blobToDataUrl } from './data-url';

export interface TailorRequest {
  // Provide exactly one of pdfBlob / resumeJson.
  pdfBlob?: Blob;
  resumeJson?: Record<string, unknown>;
  fileName?: string;
  jobDescription: string;
  resumeFormat: 'regular' | 'technical';
  // Skills the candidate explicitly confirmed (from the inferred-skills
  // picker) - merged into the resume's truthful skill pool before tailoring.
  additionalSkills?: string[];
  // JD requirement phrases (verbatim) that parseJobDescription's
  // skillMatches determined are satisfied by the confirmed additionalSkills
  // - credits the compatibility score/matched-list without writing the
  // broader wording onto the resume itself.
  creditedSkills?: string[];
}

export interface CompatibilityReport {
  score: number;
  must_coverage: number;
  nice_coverage: number;
  matched_must_have: string[];
  matched_nice_to_have: string[];
  missing_must_have: string[];
  missing_nice_to_have: string[];
  resume_skill_hits: string[];
}

export interface TailorResult {
  pdfBlob: Blob;
  compatibility?: CompatibilityReport;
  resumeSkills?: string[];
}

export async function tailorResumePdf({
  pdfBlob,
  resumeJson,
  fileName,
  jobDescription,
  resumeFormat,
  additionalSkills,
  creditedSkills,
}: TailorRequest): Promise<TailorResult> {
  // Routed through the background service worker - a direct fetch() here
  // would run in the host page's execution context and get silently blocked
  // by that page's CSP connect-src (see background.ts for details).
  const pdfDataUrl = pdfBlob ? await blobToDataUrl(pdfBlob) : undefined;

  const response = await chrome.runtime.sendMessage({
    type: 'TAILOR_RESUME',
    pdfDataUrl,
    resumeJson,
    fileName,
    jobDescription,
    resumeFormat,
    additionalSkills,
    creditedSkills,
  });

  if (!response?.ok) {
    throw new Error(response?.error || 'Tailoring failed.');
  }

  const tailoredBlob = await fetch(response.pdfDataUrl).then((r) => r.blob());
  return {
    pdfBlob: tailoredBlob,
    compatibility: response.compatibility,
    resumeSkills: response.resumeSkills,
  };
}

export interface JdParseResult {
  must_have_skills: string[];
  nice_to_have_skills: string[];
}

export interface SkillMatch {
  jd_skill: string;
  matched_candidate_skills: string[];
}

export interface ParseJdResponse {
  jobDescription: JdParseResult;
  skillMatches: SkillMatch[];
}

/**
 * Parse a job description's skills (Phase 4) - used to compute overlap with
 * a resume's inferred_skills for the skill-suggestion picker. Also routed
 * through the background service worker for the same CSP reason as above.
 *
 * inferredSkills: a resume's inferred_skills - when given, also returns
 * skillMatches: concrete inferred skills that satisfy a JD requirement
 * phrased more broadly than the skill's own wording (e.g. "hyperparameter
 * tuning" satisfying "data modeling techniques"), on top of whatever plain
 * literal-string overlap already finds.
 */
export async function parseJobDescription(
  jobDescription: string,
  inferredSkills?: string[]
): Promise<ParseJdResponse> {
  const response = await chrome.runtime.sendMessage({
    type: 'PARSE_JD',
    jobDescription,
    inferredSkills,
  });

  if (!response?.ok) {
    throw new Error(response?.error || 'Failed to parse job description.');
  }

  return { jobDescription: response.jobDescription, skillMatches: response.skillMatches ?? [] };
}
