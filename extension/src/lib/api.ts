import { blobToDataUrl } from './data-url';

export interface TailorRequest {
  // Provide exactly one of pdfBlob / resumeJson.
  pdfBlob?: Blob;
  resumeJson?: Record<string, unknown>;
  fileName?: string;
  jobDescription: string;
  resumeFormat: 'regular' | 'technical';
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
