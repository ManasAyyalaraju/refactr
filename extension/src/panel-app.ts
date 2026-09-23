import type { User } from '@supabase/supabase-js';
import { getSupabaseClient } from './lib/supabase-client';
import { listBaseResumes, downloadBaseResume, uploadGeneratedResume, type BaseResumeRow } from './lib/resumes';
import { tailorResumePdf, parseJobDescription } from './lib/api';
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
  // Show a chevron that minimizes the panel to its header bar (on-page
  // panel only - the toolbar popup has nothing to collapse into).
  collapsible?: boolean;
}

interface State {
  screen: Screen;
  user: User | null;
  resumes: BaseResumeRow[];
  selectedResumeId: string | null;
  resumeFormat: 'regular' | 'technical';
  errorMessage: string;
  lastScore: number | null;
  // Score of the resume before tailoring - the count-up starts here.
  lastOriginalScore: number | null;
  // Number currently shown on the done screen while counting up.
  displayScore: number | null;
  scoreAnimDone: boolean;
  lastResultId: string | null;
  pickerSkills: string[];
  selectedSkills: Set<string>;
}

const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 3 * 60 * 1000;
// Mirrors the web app's useCountUp in TailoredResultView.tsx.
// Long hold: the download (and Chrome's download bubble or Save dialog)
// lands at the same moment the done screen appears, so a short hold played
// the whole count-up while the user was looking elsewhere.
const COUNT_UP_DELAY_MS = 5000;
// Paced per point so small and large jumps both read as a steady climb.
const COUNT_UP_MS_PER_POINT = 90;
const COUNT_UP_MIN_MS = 1500;
const COUNT_UP_MAX_MS = 3200;

// Gentle start and finish - no burst of skipped numbers at the beginning.
function easeInOutSine(t: number): number {
  return -(Math.cos(Math.PI * t) - 1) / 2;
}

function sanitizeFilenamePart(value: string): string {
  return value.replace(/[\\/:*?"<>|]/g, '').trim();
}

// "Company - Job Title - Resume.pdf" instead of a generic name, so tailoring
// against multiple jobs produces downloads you can tell apart - mirrors the
// web app's buildTailoredResumeFilename in TailoredResultView.tsx.
function buildTailoredResumeFilename(job: JobContext | null): string {
  const parts = [job?.company, job?.title]
    .filter((v): v is string => Boolean(v && v.trim()))
    .map(sanitizeFilenamePart)
    .filter(Boolean);

  if (parts.length === 0) return 'Tailored Resume.pdf';
  return `${[...parts, 'Resume'].join(' - ')}.pdf`;
}

export function mountPanelApp({ container, jobContext, collapsible }: PanelAppOptions): void {
  const supabase = getSupabaseClient();
  let pollHandle: ReturnType<typeof setInterval> | null = null;
  let countUpTimer: ReturnType<typeof setTimeout> | null = null;
  let countUpFrame = 0;
  // Kept outside State: purely presentational, and it must survive the
  // screen changes that reset the rest of the flow.
  let collapsed = false;

  const state: State = {
    screen: 'loading',
    user: null,
    resumes: [],
    selectedResumeId: null,
    resumeFormat: 'regular',
    errorMessage: '',
    lastScore: null,
    lastOriginalScore: null,
    displayScore: null,
    scoreAnimDone: true,
    lastResultId: null,
    pickerSkills: [],
    selectedSkills: new Set(),
  };

  function render() {
    container.innerHTML = `
      <div class="refactr-panel${collapsed ? ' refactr-panel-collapsed' : ''}">
        ${renderHeader()}
        ${collapsed ? '' : `<div class="refactr-body">${renderBody()}</div>`}
      </div>
    `;
    bindEvents();
  }

  function scoreImprovement(): number {
    if (state.lastScore === null || state.lastOriginalScore === null) return 0;
    return Math.max(0, state.lastScore - state.lastOriginalScore);
  }

  function renderScore(finalScore: number): string {
    const improvement = scoreImprovement();
    const delta = improvement
      ? `<span class="refactr-score-delta${state.scoreAnimDone ? ' refactr-score-delta-visible' : ''}" data-role="score-delta">&uarr;${improvement}</span>`
      : '';
    // The delta hangs off the number's right edge (absolutely positioned) so
    // the number itself stays centered over the label.
    return `
      <div class="refactr-score">
        <span class="refactr-score-number"><strong data-role="score-value">${state.displayScore ?? finalScore}</strong>${delta}</span>
        <div class="refactr-score-label">match score</div>
      </div>
    `;
  }

  function stopScoreCountUp() {
    if (countUpTimer) clearTimeout(countUpTimer);
    cancelAnimationFrame(countUpFrame);
    countUpTimer = null;
  }

  // Shows the pre-tailoring score, then counts up to the tailored one and
  // reveals the (↑N) delta. Writes straight to the DOM each frame instead of
  // calling render(), which would rebuild the whole panel 60 times a second.
  function startScoreCountUp() {
    stopScoreCountUp();
    const to = state.lastScore;
    const from = state.lastOriginalScore;
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (to === null || from === null || from >= to || reduceMotion) {
      state.displayScore = to;
      state.scoreAnimDone = true;
      return;
    }

    state.displayScore = from;
    state.scoreAnimDone = false;
    const duration = Math.min(COUNT_UP_MAX_MS, Math.max(COUNT_UP_MIN_MS, (to - from) * COUNT_UP_MS_PER_POINT));
    let start: number | null = null;
    const tick = (now: number) => {
      if (start === null) start = now;
      const t = Math.min(1, (now - start) / duration);
      const next = Math.round(from + (to - from) * easeInOutSine(t));
      // Only touch the DOM when the visible number actually changes.
      if (next !== state.displayScore) {
        state.displayScore = next;
        const valueEl = container.querySelector('[data-role="score-value"]');
        if (valueEl) valueEl.textContent = String(next);
      }
      if (t < 1) {
        countUpFrame = requestAnimationFrame(tick);
      } else {
        state.scoreAnimDone = true;
        container.querySelector('[data-role="score-delta"]')?.classList.add('refactr-score-delta-visible');
      }
    };
    countUpTimer = setTimeout(() => {
      countUpFrame = requestAnimationFrame(tick);
    }, COUNT_UP_DELAY_MS);
  }

  function renderHeader(): string {
    return `
      <div class="refactr-header">
        <div class="refactr-logo"><span></span><span></span></div>
        <div class="refactr-brand">refactr</div>
        ${
          collapsible
            ? `<button type="button" class="refactr-collapse" data-action="toggle-collapse" aria-label="${collapsed ? 'Expand' : 'Minimize'} refactr" aria-expanded="${!collapsed}">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="${collapsed ? '6 15 12 9 18 15' : '6 9 12 15 18 9'}"></polyline></svg>
              </button>`
            : ''
        }
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
              state.lastScore !== null ? renderScore(state.lastScore) : ''
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
          <button
            type="button"
            class="refactr-skill-pill ${state.selectedSkills.has(skill) ? 'selected' : ''}"
            data-skill="${escapeHtml(skill)}"
          >${escapeHtml(skill)}</button>
        `
      )
      .join('');

    return `
      <p class="refactr-skill-picker-title">Skills To Add:</p>
      <p class="refactr-skill-picker-subtitle">
        Based on your background these are plausible skills that match the job. These aren't
        explicitly listed on your resume. Choose those that are actually true to your background.
      </p>
      <div class="refactr-skill-grid">${items}</div>
      <button type="button" class="refactr-btn refactr-btn-full" data-action="confirm-skills">Continue</button>
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
    // When collapsed, the whole header bar expands it - a bigger target than
    // the chevron alone. Login polling and the score count-up keep running
    // in the background; re-rendering picks their state back up.
    const toggleTarget = collapsed ? '.refactr-header' : '[data-action="toggle-collapse"]';
    container.querySelector(toggleTarget)?.addEventListener('click', () => {
      collapsed = !collapsed;
      render();
    });
    container.querySelector('[data-action="login"]')?.addEventListener('click', handleLoginClick);
    container.querySelector('[data-action="cancel-login"]')?.addEventListener('click', () => {
      stopPolling();
      state.screen = 'login';
      render();
    });
    container.querySelector('[data-action="tailor"]')?.addEventListener('click', handleTailor);
    container.querySelector('[data-action="reset"]')?.addEventListener('click', () => {
      stopScoreCountUp();
      state.lastScore = null;
      state.lastOriginalScore = null;
      state.displayScore = null;
      state.lastResultId = null;
      state.pickerSkills = [];
      state.selectedSkills = new Set();
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
      el.addEventListener('click', () => {
        const skill = (el as HTMLElement).dataset.skill;
        if (!skill) return;
        if (state.selectedSkills.has(skill)) {
          state.selectedSkills.delete(skill);
        } else {
          state.selectedSkills.add(skill);
        }
        render();
      });
    });
    container.querySelector('[data-action="confirm-skills"]')?.addEventListener('click', () => {
      const chosen = state.pickerSkills.filter((s) => state.selectedSkills.has(s));
      runTailor(chosen);
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

  // resume.inferred_skills is {tools, methodologies} for a resume
  // reformatted/reparsed after the tool-vs-methodology split existed, or a
  // plain string[] (no type info) for one saved before then. The picker
  // itself always shows one flat, undifferentiated list either way - this
  // just merges the two groups for display/ranking purposes.
  function flattenInferredSkills(inferred: BaseResumeRow['inferred_skills']): string[] {
    if (!inferred) return [];
    if (Array.isArray(inferred)) return inferred;
    return [...(inferred.tools ?? []), ...(inferred.methodologies ?? [])];
  }

  // Splits a set of CONFIRMED skills (a subset of flattenInferredSkills'
  // output) into hard/applied/unclassified, using whichever type info
  // resume.inferred_skills carries. A legacy string[]-shaped resume has no
  // type info at all, so everything it offers falls into "unclassified" -
  // the backend classifies those itself (tailor_resume's legacy fallback).
  function splitConfirmedSkillsByType(
    resume: BaseResumeRow,
    confirmedSkills: string[]
  ): { hard: string[]; applied: string[]; unclassified: string[] } {
    const inferred = resume.inferred_skills;
    if (!inferred || Array.isArray(inferred)) {
      return { hard: [], applied: [], unclassified: confirmedSkills };
    }

    const toolsLower = new Set((inferred.tools ?? []).map((s) => s.toLowerCase()));
    const methodologiesLower = new Set((inferred.methodologies ?? []).map((s) => s.toLowerCase()));

    const hard: string[] = [];
    const applied: string[] = [];
    const unclassified: string[] = [];
    for (const skill of confirmedSkills) {
      const lower = skill.toLowerCase();
      if (toolsLower.has(lower)) hard.push(skill);
      else if (methodologiesLower.has(lower)) applied.push(skill);
      else unclassified.push(skill);
    }
    return { hard, applied, unclassified };
  }

  async function handleTailor() {
    if (!state.user || !jobContext || !state.selectedResumeId) return;

    const resume = state.resumes.find((r) => r.id === state.selectedResumeId);
    if (!resume) return;

    const inferredSkillsFlat = flattenInferredSkills(resume.inferred_skills);

    // Only resumes with inferred_skills (saved after Phase 1, or reparsed)
    // have anything to offer here - skip straight to tailoring otherwise.
    if (inferredSkillsFlat.length === 0) {
      await runTailor([]);
      return;
    }

    state.screen = 'checking-skills';
    render();

    try {
      // Certifications are just as legitimate evidence for a JD requirement
      // (e.g. "Adobe Certified Professional" satisfying "Adobe CC") as an
      // explicit skill - bundled in here so they're treated the same way
      // throughout: covering a requirement without needing a picker suggestion.
      const additionalInfo = resume.parsed_data?.additional_info as
        | { certifications?: string[] }
        | undefined;
      const explicitSkills = [
        ...((resume.parsed_data?.skills as string[] | undefined) ?? []),
        ...(additionalInfo?.certifications ?? []),
      ];
      const { jobDescription: jd, skillMatches } = await parseJobDescription(
        jobContext.description,
        inferredSkillsFlat,
        explicitSkills
      );
      const explicitLower = new Set(explicitSkills.map((s) => s.toLowerCase()));
      const mustHaveLower = new Set((jd.must_have_skills ?? []).map((s) => s.toLowerCase()));
      const jdSkillsLower = new Set(
        [...(jd.must_have_skills ?? []), ...(jd.nice_to_have_skills ?? [])].map((s) => s.toLowerCase())
      );

      // A JD requirement already satisfied by an explicit skill (literally,
      // or via the same semantic match call) doesn't need an inferred-skill
      // suggestion - confirming one wouldn't move the score, since it's
      // credited server-side automatically either way.
      const coveredByExplicit = new Set<string>();
      for (const skill of explicitSkills) {
        if (jdSkillsLower.has(skill.toLowerCase())) coveredByExplicit.add(skill.toLowerCase());
      }
      for (const m of skillMatches) {
        if (m.matched_candidate_skills.some((s) => explicitLower.has(s.toLowerCase()))) {
          coveredByExplicit.add(m.jd_skill.toLowerCase());
        }
      }

      // Rank remaining ("gap") candidates by how many uncovered requirements
      // each would satisfy, weighting must-have above nice-to-have.
      const impact = new Map<string, number>();
      const bump = (skill: string, weight: number) => impact.set(skill, (impact.get(skill) ?? 0) + weight);

      for (const skill of inferredSkillsFlat) {
        const lower = skill.toLowerCase();
        if (jdSkillsLower.has(lower) && !coveredByExplicit.has(lower)) {
          bump(skill, mustHaveLower.has(lower) ? 2 : 1);
        }
      }
      for (const m of skillMatches) {
        const lower = m.jd_skill.toLowerCase();
        if (coveredByExplicit.has(lower)) continue;
        const weight = mustHaveLower.has(lower) ? 2 : 1;
        for (const s of m.matched_candidate_skills) {
          if (!explicitLower.has(s.toLowerCase())) bump(s, weight);
        }
      }

      if (impact.size === 0) {
        await runTailor([]);
        return;
      }

      const overlap = Array.from(impact.keys()).sort((a, b) => impact.get(b)! - impact.get(a)!);

      state.pickerSkills = overlap;
      // Unchecked by default - require an active, deliberate confirmation
      // per skill rather than pre-selecting everything and asking the user
      // to opt out (which led to over-inclusion/clutter in testing).
      state.selectedSkills = new Set();
      state.screen = 'skill-picker';
      render();
    } catch {
      // Non-critical enhancement - don't block tailoring if this check fails.
      await runTailor([]);
    }
  }

  async function runTailor(additionalSkills: string[]) {
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

      const { hard, applied, unclassified } = splitConfirmedSkillsByType(resume, additionalSkills);

      const tailorResult = await tailorResumePdf({
        ...sourceParams,
        jobDescription: jobContext.description,
        resumeFormat: state.resumeFormat,
        additionalHardSkills: hard,
        additionalAppliedSkills: applied,
        additionalUnclassifiedSkills: unclassified,
      });

      await downloadBlob(tailorResult.pdfBlob, buildTailoredResumeFilename(jobContext));

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
      state.lastOriginalScore = tailorResult.compatibility?.original_score ?? null;
      state.lastResultId = saved?.id ?? null;
      state.screen = 'done';
      startScoreCountUp();
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
