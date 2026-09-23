import { blobToDataUrl } from './data-url';

export interface TailorRequest {
  // Provide exactly one of pdfBlob / resumeJson.
  pdfBlob?: Blob;
  resumeJson?: Record<string, unknown>;
  fileName?: string;
  jobDescription: string;
  resumeFormat: 'regular' | 'technical';
  // Skills the candidate explicitly confirmed (from the inferred-skills
  // picker), pre-split by panel-app.ts's splitConfirmedSkillsByType:
  // - additionalHardSkills: tools/languages/certifications - merged into
  //   the resume's Technical Skills.
  // - additionalAppliedSkills: methodologies/techniques - woven into
  //   bullet wording instead.
  // - additionalUnclassifiedSkills: confirmed skills from a resume whose
  //   inferred_skills predates the tool-vs-methodology split - classified
  //   server-side.
  additionalHardSkills?: string[];
  additionalAppliedSkills?: string[];
  additionalUnclassifiedSkills?: string[];
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
  // Score of the resume as uploaded, before tailoring (literal matching
  // only). Absent on results saved before this field existed.
  original_score?: number;
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
  additionalHardSkills,
  additionalAppliedSkills,
  additionalUnclassifiedSkills,
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
    additionalHardSkills,
    additionalAppliedSkills,
    additionalUnclassifiedSkills,
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
 * a resume's skills for the skill-suggestion picker. Also routed through the
 * background service worker for the same CSP reason as above.
 *
 * inferredSkills/explicitSkills: a resume's inferred (plausible-but-unlisted)
 * and already-listed skills. When either is given, the backend combines both
 * into one candidate pool and returns skillMatches: which satisfy a JD
 * requirement phrased more broadly than any single skill's own wording (e.g.
 * "hyperparameter tuning" or "Power BI" each satisfying "data modeling
 * techniques"/"business intelligence"), on top of whatever plain
 * literal-string overlap already finds.
 */
export async function parseJobDescription(
  jobDescription: string,
  inferredSkills?: string[],
  explicitSkills?: string[]
): Promise<ParseJdResponse> {
  const response = await chrome.runtime.sendMessage({
    type: 'PARSE_JD',
    jobDescription,
    inferredSkills,
    explicitSkills,
  });

  if (!response?.ok) {
    throw new Error(response?.error || 'Failed to parse job description.');
  }

  return { jobDescription: response.jobDescription, skillMatches: response.skillMatches ?? [] };
}
