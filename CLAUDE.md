# refactr — Architecture & Constraints

High-level reference only. For the reasoning behind specific decisions, see `memory.md`.

## What this is

**refactr** (rebranded from "JobCraft") — an AI resume tailoring app. Upload a resume, tailor it to a job description or reformat it into an ATS-friendly PDF, with a Chrome extension that does the same directly from job board pages (LinkedIn, Indeed, Glassdoor, Handshake).

## Stack

- **Frontend** — `frontend/`: Next.js 16 (App Router), React 19, Tailwind, TypeScript. Deployed on Vercel.
- **Backend** — `backend/`: FastAPI (Python), OpenAI (GPT-4o-mini) for parsing/tailoring, LaTeX (`pdflatex`) for PDF rendering. Deployed on Render.
- **Database/Auth/Storage** — Supabase (project ref `ajchqijmzaxdphlaadeh`, org "refactr"): Postgres + Auth + private Storage buckets.
- **Extension** — `extension/`: Manifest V3, TypeScript bundled with esbuild, `@supabase/supabase-js`.

## Core architectural constraint: backend is stateless

The FastAPI backend **never talks to Supabase and never sees Supabase credentials**. It only does two things: parse/tailor/reformat resumes via OpenAI, and render PDFs via LaTeX. All auth, persistence, and file storage happen **frontend-driven** — the Next.js app and the Chrome extension both talk to Supabase directly via `supabase-js`, relying on Postgres RLS (scoped to `auth.uid()`) for security. The extension and web app share this same pattern so logic isn't duplicated across two different architectures.

## Data model (Supabase)

- `profiles` — auto-created via an `on_auth_user_created` trigger on `auth.users` (id only; `display_name` filled in by the app after signup).
- `base_resumes` — a user's saved resumes. `storage_path` points into the private `base-resumes` bucket. Every resume saved here has already been run through the reformatter (see `memory.md`) — it's never the raw uploaded PDF.
- `generated_resumes` — tailored/reformatted output history. `base_resume_id` links back to the source resume; `tailoring_options` (jsonb) holds `{mode, score?, resume_format}`. Not surfaced in the UI yet.
- Storage buckets `base-resumes` / `generated-resumes` are private; RLS requires the object path to start with `{user_id}/...`.

## Routes (frontend)

All except `/`, `/login`, `/signup` are auth-protected via `frontend/proxy.ts`.

- `/` — public landing page.
- `/login`, `/signup` — support a `?redirect=` param (sanitized against open redirects) for bouncing back to whatever protected page triggered the login.
- `/dashboard` — current resume preview (left) + older resumes; right column reserved for future work.
- `/resumes/new` — upload → pick Regular/Technical template (with a live sample preview) → reformat → save as a new `base_resumes` row → back to dashboard.
- `/tailor` — picks from saved `base_resumes` (no raw upload here anymore), tailor or reformat against a JD, Regular/Technical template choice.
- `/results` — post-tailor JSON/PDF result, reads from `sessionStorage`.
- `/extension/connect` — bridge page the Chrome extension opens to receive the logged-in web session (see `memory.md`).

## Backend API surface (`backend/routers/`)

- `POST /api/tailor/pdf` — multipart `{pdf, jd_text, output: json|pdf, resume_format: regular|technical}`.
- `POST /api/reformat/pdf` — multipart `{pdf, resume_format}`.
- `GET /api/templates/preview?format=regular|technical` — static example resume rendered through the real pipeline, no upload/AI call, cached in memory. Used by `/resumes/new` to show what each template looks like.

## Resume templates

Single LaTeX template (`backend/templates/resume_template.tex`) with a togglable categorized **TECHNICAL SKILLS** section (`resume.technical_skills`, a list of `{label, items}`). `render_resume_pdf(resume, use_technical_skills: bool)` in `backend/services/pdf_writer.py` controls which variant renders — "Regular" vs "Technical" is purely a render-time flag, not two separate templates.

**Page budget:** `Resume.target_pages` (1 or 2) is set from the uploaded PDF's own page count at parse time and persists with the saved resume. 1-page resumes are fit to one page (`compact_mode`, then `ultra_compact_mode` if still overflowing); 2-page resumes are rendered at normal spacing, keep their summary, and never enter compact/ultra-compact mode. See `memory.md`.

## Local dev

- Backend: `cd backend && venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000 --reload`. Port 8000 is hardcoded in `frontend/.env.local` and `extension/src/lib/config.ts` — don't let it float to another port.
- Frontend: `cd frontend && npm run dev` (port 3000).
- Extension: `cd extension && npm run build`, then load `extension/dist` unpacked in `chrome://extensions`.

## Extension: two builds (local vs. production)

- **Local dev** — `npm run build` (or `watch`) writes `extension/dist` (gitignored) with localhost URLs and a "(Local Dev)" name. Load that unpacked. Always leave local `dist` on this build.
- **Production** — the `extension-release` branch, served by the `/extension` page's download link. It does **not** auto-update from `master`. After any change to `extension/src/` or `extension/manifest.json`: run `npm run build:prod` (production URLs, plain "refactr" name — never plain `build`), copy the changed files from `dist/` into a temporary `git worktree` of `extension-release`, commit and push, remove the worktree, then rebuild with plain `npm run build`. See `memory.md`.
- Env vars: `frontend/.env.local` and `backend/.env` are gitignored; see the corresponding `.env.example` files for required keys (Supabase URL/anon key, OpenAI API key).
