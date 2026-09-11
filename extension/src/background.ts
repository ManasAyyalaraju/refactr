import { getSupabaseClient } from './lib/supabase-client';
import { blobToDataUrl } from './lib/data-url';
import { API_BASE_URL } from './lib/config';

interface DownloadFileMessage {
  type: 'DOWNLOAD_FILE';
  url: string;
  filename: string;
}

interface TailorResumeMessage {
  type: 'TAILOR_RESUME';
  // Provide exactly one of pdfDataUrl / resumeJson.
  pdfDataUrl?: string;
  resumeJson?: Record<string, unknown>;
  fileName?: string;
  jobDescription: string;
  resumeFormat: 'regular' | 'technical';
  additionalSkills?: string[];
  creditedSkills?: string[];
}

interface ParseJdMessage {
  type: 'PARSE_JD';
  jobDescription: string;
  inferredSkills?: string[];
}

type Message = DownloadFileMessage | TailorResumeMessage | ParseJdMessage;

chrome.runtime.onMessage.addListener((message: Message, _sender, sendResponse) => {
  if (message.type === 'DOWNLOAD_FILE') {
    chrome.downloads.download(
      { url: message.url, filename: message.filename, saveAs: false },
      () => sendResponse({ ok: !chrome.runtime.lastError })
    );
    return true; // keep the message channel open for the async sendResponse
  }

  if (message.type === 'TAILOR_RESUME') {
    // Content scripts run in the host page's execution context and are
    // subject to that page's Content-Security-Policy connect-src (LinkedIn's
    // silently blocks fetches to arbitrary hosts like our localhost backend,
    // with zero network trace - not a CORS error, the request never leaves
    // the browser). The background service worker isn't bound by any
    // webpage's CSP, so route the actual API call through here instead.
    (async () => {
      try {
        const pdfBlob = message.pdfDataUrl
          ? await fetch(message.pdfDataUrl).then((r) => r.blob())
          : null;

        const buildFormData = (output: 'json' | 'pdf') => {
          const formData = new FormData();
          if (message.resumeJson) {
            formData.append('resume_json', JSON.stringify(message.resumeJson));
          } else if (pdfBlob) {
            formData.append('pdf', pdfBlob, message.fileName);
          }
          formData.append('jd_text', message.jobDescription);
          formData.append('output', output);
          formData.append('resume_format', message.resumeFormat);
          if (message.additionalSkills && message.additionalSkills.length > 0) {
            formData.append('additional_skills', JSON.stringify(message.additionalSkills));
          }
          if (message.creditedSkills && message.creditedSkills.length > 0) {
            formData.append('credited_skills', JSON.stringify(message.creditedSkills));
          }
          return formData;
        };

        // Fetch the structured result first so we can persist the full
        // compatibility breakdown alongside the tailored PDF, then fetch
        // the PDF itself for download.
        const jsonResponse = await fetch(`${API_BASE_URL}/api/tailor/pdf`, {
          method: 'POST',
          body: buildFormData('json'),
        });

        if (!jsonResponse.ok) {
          const text = await jsonResponse.text().catch(() => '');
          sendResponse({ ok: false, error: `Tailoring failed (${jsonResponse.status}): ${text.slice(0, 300)}` });
          return;
        }

        const jsonResult = await jsonResponse.json();

        const pdfResponse = await fetch(`${API_BASE_URL}/api/tailor/pdf`, {
          method: 'POST',
          body: buildFormData('pdf'),
        });

        if (!pdfResponse.ok) {
          const text = await pdfResponse.text().catch(() => '');
          sendResponse({ ok: false, error: `Tailoring failed (${pdfResponse.status}): ${text.slice(0, 300)}` });
          return;
        }

        const resultDataUrl = await blobToDataUrl(await pdfResponse.blob());
        sendResponse({
          ok: true,
          pdfDataUrl: resultDataUrl,
          compatibility: jsonResult.compatibility,
          resumeSkills: jsonResult.resume?.skills,
        });
      } catch (err) {
        sendResponse({ ok: false, error: err instanceof Error ? err.message : 'Tailoring failed.' });
      }
    })();
    return true; // keep the message channel open for the async sendResponse
  }

  if (message.type === 'PARSE_JD') {
    // Same CSP-routing reason as TAILOR_RESUME above.
    (async () => {
      try {
        const formData = new FormData();
        formData.append('jd_text', message.jobDescription);
        if (message.inferredSkills && message.inferredSkills.length > 0) {
          formData.append('inferred_skills', JSON.stringify(message.inferredSkills));
        }

        const response = await fetch(`${API_BASE_URL}/api/jd/parse`, {
          method: 'POST',
          body: formData,
        });

        if (!response.ok) {
          const text = await response.text().catch(() => '');
          sendResponse({ ok: false, error: `Parsing job description failed (${response.status}): ${text.slice(0, 300)}` });
          return;
        }

        const result = await response.json();
        sendResponse({ ok: true, jobDescription: result.job_description, skillMatches: result.skill_matches });
      } catch (err) {
        sendResponse({ ok: false, error: err instanceof Error ? err.message : 'Failed to parse job description.' });
      }
    })();
    return true; // keep the message channel open for the async sendResponse
  }

  return false;
});

interface AuthHandoffMessage {
  type: 'REFACTR_AUTH_HANDOFF';
  access_token: string;
  refresh_token: string;
}

// Received from the refactr web app (see externally_connectable in manifest.json)
// after the user logs in there, so the extension picks up the same session.
chrome.runtime.onMessageExternal.addListener((message: AuthHandoffMessage, _sender, sendResponse) => {
  if (message.type !== 'REFACTR_AUTH_HANDOFF') return false;

  const supabase = getSupabaseClient();
  supabase.auth
    .setSession({ access_token: message.access_token, refresh_token: message.refresh_token })
    .then(({ error }) => sendResponse({ ok: !error, error: error?.message }))
    .catch((err) => sendResponse({ ok: false, error: err instanceof Error ? err.message : 'Unknown error' }));

  return true; // keep the message channel open for the async sendResponse
});
