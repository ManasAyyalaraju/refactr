import type { SupabaseClient } from '@supabase/supabase-js';
import type { CompatibilityReport } from './api';

export interface BaseResumeRow {
  id: string;
  title: string;
  storage_path: string;
  file_name: string | null;
  created_at: string;
  // Opaque parsed Resume JSON, set by the web app's reformatter at save
  // time - the extension never inspects its shape, only passes it through
  // to the backend to skip a redundant PDF parse. Null for resumes saved
  // before this existed.
  parsed_data: Record<string, unknown> | null;
  // Plausible-but-unlisted skills inferred at save time (Phase 1). Used to
  // offer a confirm/inject picker when they overlap with a job's skills.
  inferred_skills: string[] | null;
}

function randomId(): string {
  return crypto.randomUUID();
}

export async function listBaseResumes(
  supabase: SupabaseClient,
  userId: string
): Promise<BaseResumeRow[]> {
  const { data, error } = await supabase
    .from('base_resumes')
    .select('id, title, storage_path, file_name, created_at, parsed_data, inferred_skills')
    .eq('user_id', userId)
    .order('created_at', { ascending: false });

  if (error) {
    console.error('listBaseResumes failed:', error);
    return [];
  }

  return data ?? [];
}

export async function downloadBaseResume(
  supabase: SupabaseClient,
  storagePath: string
): Promise<Blob | null> {
  const { data, error } = await supabase.storage.from('base-resumes').download(storagePath);
  if (error) {
    console.error('downloadBaseResume failed:', error);
    return null;
  }
  return data;
}

export async function uploadGeneratedResume(
  supabase: SupabaseClient,
  userId: string,
  params: {
    baseResumeId: string | null;
    pdfBlob: Blob;
    jobTitle?: string | null;
    company?: string | null;
    jobUrl?: string | null;
    jobDescription?: string | null;
    resumeFormat: 'regular' | 'technical';
    compatibility?: CompatibilityReport;
    resumeSkills?: string[];
  }
): Promise<{ id: string } | null> {
  try {
    const storagePath = `${userId}/${randomId()}.pdf`;

    const { error: uploadError } = await supabase.storage
      .from('generated-resumes')
      .upload(storagePath, params.pdfBlob, { contentType: 'application/pdf' });
    if (uploadError) throw uploadError;

    const { data, error: insertError } = await supabase
      .from('generated_resumes')
      .insert({
        user_id: userId,
        base_resume_id: params.baseResumeId,
        job_title: params.jobTitle ?? null,
        company: params.company ?? null,
        job_url: params.jobUrl ?? null,
        job_description_snapshot: params.jobDescription ?? null,
        tailoring_options: {
          mode: 'tailor',
          resume_format: params.resumeFormat,
          source: 'extension',
          score: params.compatibility?.score,
          compatibility: params.compatibility,
          resume_skills: params.resumeSkills,
        },
        pdf_storage_path: storagePath,
      })
      .select('id')
      .single();
    if (insertError) throw insertError;

    return data;
  } catch (err) {
    console.error('uploadGeneratedResume failed:', err);
    return null;
  }
}
