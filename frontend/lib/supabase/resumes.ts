import type { SupabaseClient } from '@supabase/supabase-js';
import type { CompatibilityReport, Resume } from '@/types/resume';

export interface BaseResumeRow {
  id: string;
  user_id: string;
  title: string;
  storage_path: string;
  file_name: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
  // Parsed at save time so tailoring can skip re-parsing the PDF on every
  // request; both null for resumes saved before this existed.
  parsed_data: Resume | null;
  inferred_skills: string[] | null;
}

export interface TailoringOptions {
  mode: 'tailor' | 'reformat';
  score?: number;
  resume_format?: 'regular' | 'technical';
  compatibility?: CompatibilityReport;
  resume_skills?: string[];
}

export interface GeneratedResumeRow {
  id: string;
  user_id: string;
  base_resume_id: string | null;
  job_title: string | null;
  company: string | null;
  job_url: string | null;
  job_description_snapshot: string | null;
  tailoring_options: TailoringOptions;
  pdf_storage_path: string;
  created_at: string;
}

function randomId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);
}

export async function uploadBaseResume(
  supabase: SupabaseClient,
  userId: string,
  file: File,
  parsedData?: Resume | null,
  inferredSkills?: string[] | null
): Promise<{ id: string; storage_path: string } | null> {
  try {
    const storagePath = `${userId}/${randomId()}-${file.name}`;

    const { error: uploadError } = await supabase.storage
      .from('base-resumes')
      .upload(storagePath, file, { contentType: file.type || 'application/pdf' });

    if (uploadError) throw uploadError;

    const { data, error: insertError } = await supabase
      .from('base_resumes')
      .insert({
        user_id: userId,
        title: file.name,
        storage_path: storagePath,
        file_name: file.name,
        parsed_data: parsedData ?? null,
        inferred_skills: inferredSkills ?? null,
      })
      .select('id, storage_path')
      .single();

    if (insertError) throw insertError;

    return data;
  } catch (err) {
    console.error('uploadBaseResume failed:', err);
    return null;
  }
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
    tailoringOptions: TailoringOptions;
  }
): Promise<void> {
  try {
    const storagePath = `${userId}/${randomId()}.pdf`;

    const { error: uploadError } = await supabase.storage
      .from('generated-resumes')
      .upload(storagePath, params.pdfBlob, { contentType: 'application/pdf' });

    if (uploadError) throw uploadError;

    const { error: insertError } = await supabase.from('generated_resumes').insert({
      user_id: userId,
      base_resume_id: params.baseResumeId,
      job_title: params.jobTitle ?? null,
      company: params.company ?? null,
      job_url: params.jobUrl ?? null,
      job_description_snapshot: params.jobDescription ?? null,
      tailoring_options: params.tailoringOptions,
      pdf_storage_path: storagePath,
    });

    if (insertError) throw insertError;
  } catch (err) {
    console.error('uploadGeneratedResume failed:', err);
  }
}

export async function listBaseResumes(
  supabase: SupabaseClient,
  userId: string
): Promise<BaseResumeRow[]> {
  const { data, error } = await supabase
    .from('base_resumes')
    .select('*')
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

export async function listGeneratedResumes(
  supabase: SupabaseClient,
  userId: string
): Promise<GeneratedResumeRow[]> {
  const { data, error } = await supabase
    .from('generated_resumes')
    .select('*')
    .eq('user_id', userId)
    .order('created_at', { ascending: false });

  if (error) {
    console.error('listGeneratedResumes failed:', error);
    return [];
  }

  return data ?? [];
}

export async function getGeneratedResume(
  supabase: SupabaseClient,
  id: string
): Promise<GeneratedResumeRow | null> {
  const { data, error } = await supabase
    .from('generated_resumes')
    .select('*')
    .eq('id', id)
    .single();

  if (error) {
    console.error('getGeneratedResume failed:', error);
    return null;
  }

  return data;
}

export async function downloadGeneratedResume(
  supabase: SupabaseClient,
  storagePath: string
): Promise<Blob | null> {
  const { data, error } = await supabase.storage.from('generated-resumes').download(storagePath);

  if (error) {
    console.error('downloadGeneratedResume failed:', error);
    return null;
  }

  return data;
}
