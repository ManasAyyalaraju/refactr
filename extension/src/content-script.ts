import { isJobPostingUrl, extractJobContext, type JobContext } from './lib/extract-jd';
import { mountPanelApp } from './panel-app';

let currentUrl = '';
let hostEl: HTMLElement | null = null;
let dismissedForThisPage = false;
let pollHandle: ReturnType<typeof setInterval> | null = null;

function teardown() {
  hostEl?.remove();
  hostEl = null;
}

// Reloading the extension in chrome://extensions invalidates chrome.runtime
// for content scripts already injected into open tabs - the tab needs an
// actual page refresh to pick up the new script. Without this guard, that
// state throws an uncaught error out of the chrome.runtime.getURL() call
// below and leaves an empty host element stuck in the DOM.
function isExtensionContextValid(): boolean {
  try {
    return typeof chrome !== 'undefined' && !!chrome.runtime?.id;
  } catch {
    return false;
  }
}

const MAX_EXTRACTION_ATTEMPTS = 4;

async function tryShowPrompt(attempt = 0) {
  if (dismissedForThisPage || hostEl) return;

  const isLastAttempt = attempt >= MAX_EXTRACTION_ATTEMPTS;
  // Only let the last attempt fall back to the generic "biggest text block"
  // heuristic - see extractJobContext for why an earlier fallback risks
  // permanently locking onto page chrome instead of the real description.
  const jobContext = extractJobContext(window.location.href, { allowGenericFallback: isLastAttempt });

  if (!jobContext && !isLastAttempt) {
    // LinkedIn and similar SPAs render the description asynchronously.
    setTimeout(() => tryShowPrompt(attempt + 1), 1000);
    return;
  }

  if (!jobContext) return;

  await renderPrompt(jobContext);
}

async function renderPrompt(jobContext: JobContext) {
  if (!isExtensionContextValid()) {
    // Stale content script from before an extension reload - nothing we can
    // do until the page itself is refreshed, so bail out quietly rather than
    // throwing out of chrome.runtime.getURL() below.
    return;
  }

  hostEl = document.createElement('div');
  hostEl.id = 'refactr-host';
  // width:fit-content is a belt-and-suspenders backstop: forces this host to
  // hug its shadow content's actual rendered width no matter what's inside,
  // rather than relying on the browser's shrink-to-fit default for
  // fixed-position elements (which can behave inconsistently with shadow DOM).
  hostEl.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:2147483647;width:fit-content;';
  document.documentElement.appendChild(hostEl);

  const shadow = hostEl.attachShadow({ mode: 'open' });

  let cssText: string;
  try {
    cssText = await fetch(chrome.runtime.getURL('panel.css')).then((r) => r.text());
  } catch {
    // Context was invalidated mid-flight (e.g. extension reloaded while this
    // await was pending) - clean up the host we already appended and stop.
    teardown();
    return;
  }
  const style = document.createElement('style');
  style.textContent = cssText;
  shadow.appendChild(style);

  const promptEl = document.createElement('div');
  promptEl.className = 'refactr-panel';
  promptEl.innerHTML = `
    <div class="refactr-prompt">
      <p>Tailor your resume for this job?</p>
    </div>
    <div class="refactr-body" style="padding-top:0;">
      <button type="button" class="refactr-btn" data-action="open">Open refactr</button>
      <button type="button" class="refactr-btn refactr-btn-secondary" style="margin-top:8px;" data-action="dismiss">Not now</button>
    </div>
  `;
  shadow.appendChild(promptEl);

  promptEl.querySelector('[data-action="dismiss"]')?.addEventListener('click', () => {
    dismissedForThisPage = true;
    teardown();
  });

  promptEl.querySelector('[data-action="open"]')?.addEventListener('click', () => {
    shadow.removeChild(promptEl);
    const panelContainer = document.createElement('div');
    // display:contents removes this wrapper from the box model entirely -
    // without it, this bare unstyled div sits between the shrink-to-fit
    // fixed-position host and the actually-sized .refactr-panel, which can
    // leave the host's shrink-wrapped width wider than the visible panel.
    panelContainer.style.display = 'contents';
    shadow.appendChild(panelContainer);
    // Re-extract rather than reusing the jobContext captured when the small
    // prompt first appeared (within ~4s of page load, with a limited retry
    // window) - on a slower-rendering page (e.g. a promoted listing with
    // extra tracking scripts), that first pass can lock onto the generic
    // "biggest text block" fallback before the real description has
    // rendered. By the time the user reads the prompt and clicks this,
    // real content has had much more time to load.
    const freshJobContext = extractJobContext(window.location.href, { allowGenericFallback: true }) ?? jobContext;
    mountPanelApp({
      container: panelContainer,
      jobContext: freshJobContext,
      onClose: () => {
        dismissedForThisPage = true;
        teardown();
      },
    });
  });
}

function checkForNavigation() {
  if (!isExtensionContextValid()) {
    // Extension was reloaded since this script was injected - this tab's
    // instance is permanently stale until the page is refreshed. Stop
    // polling instead of repeating this check (and any future errors)
    // forever.
    if (pollHandle !== null) {
      clearInterval(pollHandle);
      pollHandle = null;
    }
    return;
  }

  if (window.location.href === currentUrl) return;
  currentUrl = window.location.href;
  dismissedForThisPage = false;
  teardown();

  if (isJobPostingUrl(currentUrl)) {
    tryShowPrompt();
  }
}

// Initial load
currentUrl = window.location.href;
if (isJobPostingUrl(currentUrl)) {
  tryShowPrompt();
}

// LinkedIn and similar boards are SPAs - URL changes without a full reload.
pollHandle = setInterval(checkForNavigation, 1500);
