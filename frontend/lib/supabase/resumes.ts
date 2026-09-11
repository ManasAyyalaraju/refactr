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

/**
 * Throws on a query failure rather than swallowing it - the caller must
 * treat "the check failed" differently from "no duplicate exists" (a
 * silent duplicate-creation bug came from conflating the two: an error was
 * being treated the same as "no match," so the upload silently proceeded
 * as if nothing existed).
 */
export async function findBaseResumeByFileName(
  supabase: SupabaseClient,
  userId: string,
  fileName: string
): Promise<BaseResumeRow | null> {
  // .limit(1) rather than .maybeSingle() - this feature stops new duplicates
  // from being created going forward, but accounts with pre-existing
  // same-named rows (uploaded before this existed) can already have more
  // than one match, which .maybeSingle() would throw on. Target the most
  // recently saved one.
  const { data, error } = await supabase
    .from('base_resumes')
    .select('*')
    .eq('user_id', userId)
    .eq('file_name', fileName)
    .order('created_at', { ascending: false })
    .limit(1);

  if (error) {
    throw error;
  }

  return data?.[0] ?? null;
}

/**
 * Replace an existing base_resumes row in place (same row id), so any
 * generated_resumes history linked via base_resume_id stays correctly
 * associated. Uploads the new file to a fresh storage path, updates the
 * row, then cleans up the old storage object.
 */
export async function replaceBaseResume(
  supabase: SupabaseClient,
  existingResumeId: string,
  userId: string,
  file: File,
  parsedData?: Resume | null,
  inferredSkills?: string[] | null
): Promise<{ id: string; storage_path: string } | null> {
  try {
    const { data: existingRow } = await supabase
      .from('base_resumes')
      .select('storage_path')
      .eq('id', existingResumeId)
      .single();

    const newStoragePath = `${userId}/${randomId()}-${file.name}`;

    const { error: uploadError } = await supabase.storage
      .from('base-resumes')
      .upload(newStoragePath, file, { contentType: file.type || 'application/pdf' });
    if (uploadError) throw uploadError;

    const { data, error: updateError } = await supabase
      .from('base_resumes')
      .update({
        title: file.name,
        storage_path: newStoragePath,
        file_name: file.name,
        parsed_data: parsedData ?? null,
        inferred_skills: inferredSkills ?? null,
      })
      .eq('id', existingResumeId)
      .select('id, storage_path')
      .single();
    if (updateError) throw updateError;

    if (existingRow?.storage_path && existingRow.storage_path !== newStoragePath) {
      await supabase.storage.from('base-resumes').remove([existingRow.storage_path]);
    }

    return data;
  } catch (err) {
    console.error('replaceBaseResume failed:', err);
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
