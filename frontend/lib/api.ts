import axios from 'axios';
import { Resume, TailoredResult, JobDescription } from '@/types/resume';

// Configure the base URL for the backend API
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'multipart/form-data',
  },
});

export type ResumeFormat = 'regular' | 'technical';

// axios's own error.message is a generic "Request failed with status code
// 422" - the backend's actual explanation lives in the JSON error body's
// "detail" field (FastAPI's HTTPException shape). Falls back to axios's
// generic message when the error body isn't a parsed JSON object (e.g. a
// PDF-output request whose error response came back as a Blob).
function extractErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data;
    if (data && typeof data === 'object' && typeof (data as { detail?: unknown }).detail === 'string') {
      return (data as { detail: string }).detail;
    }
    return error.message || fallback;
  }
  return error instanceof Error ? error.message : fallback;
}

export interface TailorResumeParams {
  // Provide exactly one of pdfFile / resumeJson. resumeJson (a previously-
  // parsed Resume from a saved base_resume) skips the backend's PDF parse.
  pdfFile?: File | Blob;
  resumeJson?: Resume;
  fileName?: string;
  jobDescription: string;
  outputFormat?: 'json' | 'pdf';
  resumeFormat?: ResumeFormat;
  // Skills the candidate explicitly confirmed (from the inferred-skills
  // picker) - merged into the resume's truthful skill pool before tailoring.
  additionalSkills?: string[];
}

function resolveFileName(pdfFile: File | Blob, fileName?: string): string {
  return fileName ?? (pdfFile instanceof File ? pdfFile.name : 'resume.pdf');
}

export interface TailorResumeResponse {
  data: TailoredResult | Blob;
  success: boolean;
  error?: string;
}

export interface ReformatResumeParams {
  pdfFile: File | Blob;
  fileName?: string;
  resumeFormat?: ResumeFormat;
  outputFormat?: 'pdf' | 'json';
}

export interface ReformatJsonResult {
  resume: Resume;
  inferred_skills: string[];
  pdf_base64: string;
}

export interface ReformatResumeResponse {
  data: Blob | ReformatJsonResult;
  success: boolean;
  error?: string;
}

/**
 * Tailor a resume based on a job description
 */
export async function tailorResume({
  pdfFile,
  resumeJson,
  fileName,
  jobDescription,
  outputFormat = 'json',
  resumeFormat = 'regular',
  additionalSkills,
}: TailorResumeParams): Promise<TailorResumeResponse> {
  try {
    const formData = new FormData();
    if (resumeJson) {
      formData.append('resume_json', JSON.stringify(resumeJson));
    } else if (pdfFile) {
      formData.append('pdf', pdfFile, resolveFileName(pdfFile, fileName));
    } else {
      throw new Error('tailorResume requires either pdfFile or resumeJson.');
    }
    formData.append('jd_text', jobDescription);
    formData.append('output', outputFormat);
    formData.append('resume_format', resumeFormat);
    if (additionalSkills && additionalSkills.length > 0) {
      formData.append('additional_skills', JSON.stringify(additionalSkills));
    }

    const response = await apiClient.post('/api/tailor/pdf', formData, {
      responseType: outputFormat === 'pdf' ? 'blob' : 'json',
    });

    return {
      data: response.data,
      success: true,
    };
  } catch (error) {
    console.error('Error tailoring resume:', error);
    return {
      data: {} as TailoredResult,
      success: false,
      error: extractErrorMessage(error, 'An error occurred'),
    };
  }
}

/**
 * Reformat a resume into an ATS-friendly PDF without tailoring to a job description
 */
export async function reformatResume({
  pdfFile,
  fileName,
  resumeFormat = 'regular',
  outputFormat = 'pdf',
}: ReformatResumeParams): Promise<ReformatResumeResponse> {
  try {
    const formData = new FormData();
    formData.append('pdf', pdfFile, resolveFileName(pdfFile, fileName));
    formData.append('resume_format', resumeFormat);
    formData.append('output', outputFormat);

    const response = await apiClient.post('/api/reformat/pdf', formData, {
      responseType: outputFormat === 'pdf' ? 'blob' : 'json',
    });

    return {
      data: response.data,
      success: true,
    };
  } catch (error) {
    console.error('Error reformatting resume:', error);
    return {
      data: new Blob(),
      success: false,
      error: extractErrorMessage(error, 'An error occurred'),
    };
  }
}

export interface ReparseResumeResult {
  resume: Resume;
  inferred_skills: string[];
}

export interface ReparseResumeResponse {
  data: ReparseResumeResult;
  success: boolean;
  error?: string;
}

/**
 * Tester-only (Phase 3): re-parse an already-saved resume PDF to backfill
 * parsed_data/inferred_skills. Does not re-render or replace the PDF.
 */
export async function reparseResume(pdfFile: Blob, fileName: string): Promise<ReparseResumeResponse> {
  try {
    const formData = new FormData();
    formData.append('pdf', pdfFile, fileName);

    const response = await apiClient.post('/api/resumes/reparse', formData);

    return {
      data: response.data,
      success: true,
    };
  } catch (error) {
    console.error('Error reparsing resume:', error);
    return {
      data: {} as ReparseResumeResult,
      success: false,
      error: extractErrorMessage(error, 'An error occurred'),
    };
  }
}

export interface SkillMatch {
  jd_skill: string;
  matched_candidate_skills: string[];
}

export interface ParseJobDescriptionResult {
  job_description: JobDescription;
  domain: { industry: string; sub_domain: string; confidence: string };
  skill_matches: SkillMatch[];
}

export interface ParseJobDescriptionResponse {
  data: ParseJobDescriptionResult;
  success: boolean;
  error?: string;
}

/**
 * Parse a job description's skills/domain without tailoring a resume
 * against it (Phase 4) - used to compute overlap with a resume's skills for
 * the skill-suggestion picker.
 *
 * inferredSkills/explicitSkills: a resume's inferred (plausible-but-unlisted)
 * and already-listed skills. When either is given, the backend combines both
 * into one candidate pool and returns skill_matches: which of them satisfy a
 * JD requirement phrased more broadly than any single skill's own wording
 * (e.g. "hyperparameter tuning" or "Power BI" each satisfying "data modeling
 * techniques"/"business intelligence"), on top of whatever plain
 * literal-string overlap already finds. Matching both pools together (one
 * call) lets the caller tell which JD requirements are already covered by
 * explicit skills - those don't need an inferred-skill suggestion.
 */
export async function parseJobDescription(
  jdText: string,
  inferredSkills?: string[],
  explicitSkills?: string[]
): Promise<ParseJobDescriptionResponse> {
  try {
    const formData = new FormData();
    formData.append('jd_text', jdText);
    if (inferredSkills && inferredSkills.length > 0) {
      formData.append('inferred_skills', JSON.stringify(inferredSkills));
    }
    if (explicitSkills && explicitSkills.length > 0) {
      formData.append('explicit_skills', JSON.stringify(explicitSkills));
    }

    const response = await apiClient.post('/api/jd/parse', formData);

    return {
      data: response.data,
      success: true,
    };
  } catch (error) {
    console.error('Error parsing job description:', error);
    return {
      data: {} as ParseJobDescriptionResult,
      success: false,
      error: extractErrorMessage(error, 'An error occurred'),
    };
  }
}

export interface ValidatePdfResponse {
  valid: boolean;
  error?: string;
}

/**
 * Cheap pre-upload check: does this PDF have a real text layer? Runs right
 * after file selection, before the template step even renders, so a
 * scanned/flattened-image PDF is rejected immediately instead of after a
 * full reformat attempt.
 */
export async function validatePdfHasText(pdfFile: File | Blob, fileName?: string): Promise<ValidatePdfResponse> {
  try {
    const formData = new FormData();
    formData.append('pdf', pdfFile, resolveFileName(pdfFile, fileName));

    await apiClient.post('/api/resumes/validate-pdf', formData);
    return { valid: true };
  } catch (error) {
    return {
      valid: false,
      error: extractErrorMessage(error, 'Could not validate your PDF. Please try again.'),
    };
  }
}

/**
 * Fetch a sample PDF showing what the Regular or Technical template looks like.
 */
export async function fetchTemplatePreview(format: ResumeFormat): Promise<Blob> {
  const response = await apiClient.get('/api/templates/preview', {
    params: { format },
    responseType: 'blob',
    headers: { 'Content-Type': undefined },
  });
  return response.data;
}

/**
 * Decode a base64-encoded PDF (from ReformatJsonResult.pdf_base64) into a File.
 */
export function base64ToFile(base64: string, fileName: string): File {
  const byteChars = atob(base64);
  const byteNumbers = new Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i++) {
    byteNumbers[i] = byteChars.charCodeAt(i);
  }
  const byteArray = new Uint8Array(byteNumbers);
  return new File([byteArray], fileName, { type: 'application/pdf' });
}

/**
 * Download a PDF blob as a file
 */
export function downloadPDF(blob: Blob, filename: string = 'tailored_resume.pdf') {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

/**
 * Check if the backend API is healthy
 */
export async function checkHealth(): Promise<boolean> {
  try {
    const response = await axios.get(`${API_BASE_URL}/health`);
    return response.status === 200;
  } catch (error) {
    console.error('Health check failed:', error);
    return false;
  }
}
