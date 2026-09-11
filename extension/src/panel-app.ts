import type { User } from '@supabase/supabase-js';
import { getSupabaseClient } from './lib/supabase-client';
import { listBaseResumes, downloadBaseResume, uploadGeneratedResume, type BaseResumeRow } from './lib/resumes';
import { tailorResumePdf, parseJobDescription, type SkillMatch } from './lib/api';
import { blobToDataUrl } from './lib/data-url';
import type { JobContext } from './lib/extract-jd';
import { WEB_APP_URL } from './lib/config';

type Screen =
  | 'loading'
  | 'login'
  | 'waiting-login'
  | 'picker'
  | 'checking-skills'
  | 'skill-picker'
  | 'tailoring'
  | 'done'
  | 'error';

export interface PanelAppOptions {
  container: HTMLElement;
  jobContext: JobContext | null;
  onClose?: () => void;
}

interface State {
  screen: Screen;
  user: User | null;
  resumes: BaseResumeRow[];
  selectedResumeId: string | null;
  resumeFormat: 'regular' | 'technical';
  errorMessage: string;
  lastScore: number | null;
  lastResultId: string | null;
  pickerSkills: string[];
  selectedSkills: Set<string>;
  pickerSkillMatches: SkillMatch[];
}

const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 3 * 60 * 1000;

export function mountPanelApp({ container, jobContext, onClose }: PanelAppOptions): void {
  const supabase = getSupabaseClient();
  let pollHandle: ReturnType<typeof setInterval> | null = null;

  const state: State = {
    screen: 'loading',
    user: null,
    resumes: [],
    selectedResumeId: null,
    resumeFormat: 'regular',
    errorMessage: '',
    lastScore: null,
    lastResultId: null,
    pickerSkills: [],
    selectedSkills: new Set(),
    pickerSkillMatches: [],
  };

  function render() {
    container.innerHTML = `
      <div class="refactr-panel">
        ${renderHeader()}
        <div class="refactr-body">${renderBody()}</div>
      </div>
    `;
    bindEvents();
  }

  function renderHeader(): string {
    return `
      <div class="refactr-header">
        <div class="refactr-logo"><span></span><span></span></div>
        <div class="refactr-brand">refactr</div>
        ${onClose ? '<button type="button" class="refactr-close" data-action="close">&times;</button>' : ''}
      </div>
    `;
  }

  function renderBody(): string {
    switch (state.screen) {
      case 'loading':
        return `<div class="refactr-status"><div class="refactr-spinner"></div><p>Loading...</p></div>`;
      case 'login':
        return renderLogin();
      case 'waiting-login':
        return `
          <div class="refactr-status">
            <div class="refactr-spinner"></div>
            <p>Waiting for you to log in in the other tab...</p>
            <button type="button" class="refactr-btn refactr-btn-secondary" style="margin-top:14px;" data-action="cancel-login">Cancel</button>
          </div>
        `;
      case 'picker':
        return renderPicker();
      case 'checking-skills':
        return `<div class="refactr-status"><div class="refactr-spinner"></div><p>Checking for matching skills...</p></div>`;
      case 'skill-picker':
        return renderSkillPicker();
      case 'tailoring':
        return `<div class="refactr-status"><div class="refactr-spinner"></div><p>Tailoring your resume...</p></div>`;
      case 'done':
        return `
          <div class="refactr-status">
            <p>&#10003; Tailored resume downloaded.</p>
            ${
              state.lastScore !== null
                ? `<p class="refactr-score"><strong>${state.lastScore}</strong> match score</p>`
                : ''
            }
            <div style="display:flex; flex-direction:column; gap:10px; margin-top:14px;">
              ${
                state.lastResultId
                  ? `<button type="button" class="refactr-btn" data-action="view-details">View Detailed Results</button>`
                  : ''
              }
              <button type="button" class="refactr-btn refactr-btn-secondary" data-action="reset">Tailor another</button>
            </div>
          </div>
        `;
      case 'error':
        return `
          <div class="refactr-status">
            <p class="refactr-error">${escapeHtml(state.errorMessage)}</p>
            <button type="button" class="refactr-btn" data-action="reset">Try again</button>
          </div>
        `;
    }
  }

  function renderLogin(): string {
    return `
      ${state.errorMessage ? `<p class="refactr-error">${escapeHtml(state.errorMessage)}</p>` : ''}
      <p style="font-size:13px;color:#374151;margin:0 0 14px;">
        Log in to your refactr account to tailor resumes from this page.
      </p>
      <button type="button" class="refactr-btn" data-action="login">Log in to refactr</button>
    `;
  }

  function renderPicker(): string {
    const jobMeta = jobContext
      ? `
        <div class="refactr-job-meta">
          ${jobContext.title ? `<p class="refactr-job-title">${escapeHtml(jobContext.title)}</p>` : ''}
          ${jobContext.company ? `<p>${escapeHtml(jobContext.company)}</p>` : ''}
        </div>
      `
      : '';

    if (state.resumes.length === 0) {
      return `
        ${jobMeta}
        <div class="refactr-empty">
          No saved resumes yet. Tailor or reformat a resume once on the refactr web app to save one here.
        </div>
        ${renderAccountFooter()}
      `;
    }

    const options = state.resumes
      .map(
        (r) =>
          `<option value="${r.id}" ${r.id === state.selectedResumeId ? 'selected' : ''}>${escapeHtml(r.file_name ?? r.title)}</option>`
      )
      .join('');

    return `
      ${jobMeta}
      <div class="refactr-field">
        <label for="refactr-resume">Resume</label>
        <select id="refactr-resume">${options}</select>
      </div>
      <div class="refactr-field">
        <label>Template</label>
        <div class="refactr-format-options">
          <div class="refactr-format-option ${state.resumeFormat === 'regular' ? 'selected' : ''}" data-format="regular">Regular</div>
          <div class="refactr-format-option ${state.resumeFormat === 'technical' ? 'selected' : ''}" data-format="technical">Technical</div>
        </div>
      </div>
      <button type="button" class="refactr-btn" data-action="tailor" ${!jobContext ? 'disabled' : ''}>
        Tailor &amp; Download
      </button>
      ${!jobContext ? '<p class="refactr-error" style="margin-top:8px;">Could not read a job description on this page.</p>' : ''}
      ${renderAccountFooter()}
    `;
  }

  function renderSkillPicker(): string {
    const items = state.pickerSkills
      .map(
        (skill) => `
          <label class="refactr-skill-option">
            <input type="checkbox" data-skill="${escapeHtml(skill)}" ${state.selectedSkills.has(skill) ? 'checked' : ''} />
            <span>${escapeHtml(skill)}</span>
          </label>
        `
      )
      .join('');

    return `
      <p style="font-size:13px;color:#374151;margin:0 0 12px;">
        Based on your resume's background, these look plausible and match this job, but
        aren't explicitly listed on your resume. Confirm any that are actually true.
      </p>
      <div class="refactr-skill-list">${items}</div>
      <div class="refactr-actions">
        <button type="button" class="refactr-btn refactr-btn-secondary" data-action="skip-skills">Skip</button>
        <button type="button" class="refactr-btn" data-action="confirm-skills">Continue</button>
      </div>
    `;
  }

  function renderAccountFooter(): string {
    return `
      <p class="refactr-footer-link" style="margin-top:14px;font-size:12px;color:#6b7280;">
        Connected as ${escapeHtml(state.user?.email ?? '')} &middot;
        <a class="refactr-link" data-action="sign-out">Switch account</a>
      </p>
    `;
  }

  function bindEvents() {
    container.querySelector('[data-action="close"]')?.addEventListener('click', () => {
      stopPolling();
      onClose?.();
    });
    container.querySelector('[data-action="login"]')?.addEventListener('click', handleLoginClick);
    container.querySelector('[data-action="cancel-login"]')?.addEventListener('click', () => {
      stopPolling();
      state.screen = 'login';
      render();
    });
    container.querySelector('[data-action="tailor"]')?.addEventListener('click', handleTailor);
    container.querySelector('[data-action="reset"]')?.addEventListener('click', () => {
      state.lastScore = null;
      state.lastResultId = null;
      state.pickerSkills = [];
      state.selectedSkills = new Set();
      state.pickerSkillMatches = [];
      state.screen = 'picker';
      render();
    });
    container.querySelector('[data-action="view-details"]')?.addEventListener('click', () => {
      if (state.lastResultId) {
        window.open(`${WEB_APP_URL}/tailored/${state.lastResultId}`, '_blank');
      }
    });
    container.querySelectorAll('[data-format]').forEach((el) => {
      el.addEventListener('click', () => {
        state.resumeFormat = (el as HTMLElement).dataset.format as 'regular' | 'technical';
        render();
      });
    });
    container.querySelector('#refactr-resume')?.addEventListener('change', (e) => {
      state.selectedResumeId = (e.target as HTMLSelectElement).value;
    });
    container.querySelector('[data-action="sign-out"]')?.addEventListener('click', handleSignOut);
    container.querySelectorAll('[data-skill]').forEach((el) => {
      el.addEventListener('change', (e) => {
        const skill = (el as HTMLElement).dataset.skill;
        if (!skill) return;
        if ((e.target as HTMLInputElement).checked) {
          state.selectedSkills.add(skill);
        } else {
          state.selectedSkills.delete(skill);
        }
      });
    });
    container.querySelector('[data-action="skip-skills"]')?.addEventListener('click', () => runTailor([]));
    container.querySelector('[data-action="confirm-skills"]')?.addEventListener('click', () => {
      const chosen = state.pickerSkills.filter((s) => state.selectedSkills.has(s));
      // Credit a JD requirement (e.g. "data modeling techniques") if at
      // least one of the skills that satisfy it was actually confirmed -
      // computed from the full-pool matches already found by the earlier
      // overlap check, not re-derived against just the confirmed subset (a
      // smaller pool makes the match-judgment markedly less reliable).
      const chosenLower = new Set(chosen.map((s) => s.toLowerCase()));
      const credited = state.pickerSkillMatches
        .filter((m) => m.matched_candidate_skills.some((s) => chosenLower.has(s.toLowerCase())))
        .map((m) => m.jd_skill);
      runTailor(chosen, credited);
    });
  }

  async function handleSignOut() {
    await supabase.auth.signOut();
    state.user = null;
    state.resumes = [];
    state.selectedResumeId = null;
    state.errorMessage = '';
    state.screen = 'login';
    render();
  }

  function handleLoginClick() {
    window.open(`${WEB_APP_URL}/extension/connect`, '_blank');
    state.errorMessage = '';
    state.screen = 'waiting-login';
    render();
    startPolling();
  }

  function startPolling() {
    stopPolling();
    const startedAt = Date.now();

    pollHandle = setInterval(async () => {
      if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
        stopPolling();
        state.errorMessage = "Didn't detect a login. Please try again.";
        state.screen = 'login';
        render();
        return;
      }

      const { data } = await supabase.auth.getUser();
      if (data.user) {
        stopPolling();
        state.user = data.user;
        await loadResumes();
      }
    }, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (pollHandle !== null) {
      clearInterval(pollHandle);
      pollHandle = null;
    }
  }

  async function loadResumes() {
    if (!state.user) return;
    state.resumes = await listBaseResumes(supabase, state.user.id);
    state.selectedResumeId = state.resumes[0]?.id ?? null;
    state.screen = 'picker';
    render();
  }

  async function handleTailor() {
    if (!state.user || !jobContext || !state.selectedResumeId) return;

    const resume = state.resumes.find((r) => r.id === state.selectedResumeId);
    if (!resume) return;

    // Only resumes with inferred_skills (saved after Phase 1, or reparsed)
    // have anything to offer here - skip straight to tailoring otherwise.
    if (!resume.inferred_skills || resume.inferred_skills.length === 0) {
      await runTailor([]);
      return;
    }

    state.screen = 'checking-skills';
    render();

    try {
      const { jobDescription: jd, skillMatches } = await parseJobDescription(
        jobContext.description,
        resume.inferred_skills
      );
      const explicitLower = new Set(
        ((resume.parsed_data?.skills as string[] | undefined) ?? []).map((s) => s.toLowerCase())
      );

      // Plain literal overlap (e.g. JD says "Docker", inferred_skills has "Docker").
      const jdSkillsLower = new Set(
        [...(jd.must_have_skills ?? []), ...(jd.nice_to_have_skills ?? [])].map((s) => s.toLowerCase())
      );
      const literalOverlap = resume.inferred_skills.filter(
        (s) => jdSkillsLower.has(s.toLowerCase()) && !explicitLower.has(s.toLowerCase())
      );

      // Semantic overlap (e.g. JD says "data modeling techniques", candidate
      // has "hyperparameter tuning") - a JD requirement phrased more broadly
      // than any single skill's own wording, which literal matching can't catch.
      const semanticOverlap = skillMatches
        .flatMap((m) => m.matched_candidate_skills)
        .filter((s) => !explicitLower.has(s.toLowerCase()));

      const overlap = Array.from(new Set([...literalOverlap, ...semanticOverlap]));

      if (overlap.length === 0) {
        await runTailor([]);
        return;
      }

      state.pickerSkills = overlap;
      state.selectedSkills = new Set(overlap);
      state.pickerSkillMatches = skillMatches;
      state.screen = 'skill-picker';
      render();
    } catch {
      // Non-critical enhancement - don't block tailoring if this check fails.
      await runTailor([]);
    }
  }

  async function runTailor(additionalSkills: string[], creditedSkills: string[] = []) {
    if (!state.user || !jobContext || !state.selectedResumeId) return;

    const resume = state.resumes.find((r) => r.id === state.selectedResumeId);
    if (!resume) return;

    state.screen = 'tailoring';
    render();

    try {
      // Resumes saved after Phase 1 already carry their parsed structure -
      // skip re-downloading and re-parsing the PDF entirely for those.
      let sourceParams: { pdfBlob: Blob; fileName: string } | { resumeJson: Record<string, unknown> };
      if (resume.parsed_data) {
        sourceParams = { resumeJson: resume.parsed_data };
      } else {
        const pdfBlob = await downloadBaseResume(supabase, resume.storage_path);
        if (!pdfBlob) throw new Error('Could not load that saved resume file.');
        sourceParams = { pdfBlob, fileName: resume.file_name ?? resume.title };
      }

      const tailorResult = await tailorResumePdf({
        ...sourceParams,
        jobDescription: jobContext.description,
        resumeFormat: state.resumeFormat,
        additionalSkills,
        creditedSkills,
      });

      await downloadBlob(tailorResult.pdfBlob, 'tailored_resume.pdf');

      const saved = await uploadGeneratedResume(supabase, state.user.id, {
        baseResumeId: resume.id,
        pdfBlob: tailorResult.pdfBlob,
        jobTitle: jobContext.title,
        company: jobContext.company,
        jobUrl: window.location?.href,
        jobDescription: jobContext.description,
        resumeFormat: state.resumeFormat,
        compatibility: tailorResult.compatibility,
        resumeSkills: tailorResult.resumeSkills,
      });

      state.lastScore = tailorResult.compatibility?.score ?? null;
      state.lastResultId = saved?.id ?? null;
      state.screen = 'done';
      render();
    } catch (err) {
      state.errorMessage = err instanceof Error ? err.message : 'Something went wrong.';
      state.screen = 'error';
      render();
    }
  }

  async function downloadBlob(blob: Blob, filename: string): Promise<void> {
    // Content scripts can't call chrome.downloads directly, and blob: URLs
    // don't resolve across contexts - so we hand the background service
    // worker a data: URL (a plain string) it can pass to chrome.downloads.
    const dataUrl = await blobToDataUrl(blob);
    await chrome.runtime.sendMessage({ type: 'DOWNLOAD_FILE', url: dataUrl, filename });
  }

  function escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Initial load
  render();
  supabase.auth.getUser().then(async ({ data }) => {
    if (data.user) {
      state.user = data.user;
      await loadResumes();
    } else {
      state.screen = 'login';
      render();
    }
  });
}
