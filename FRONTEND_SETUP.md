# Frontend Setup

You only need the frontend — no Python backend or LaTeX install required, since your `.env.local` will point at the live production API.

## 1. Clone & switch to your branch
```
git clone https://github.com/ManasAyyalaraju/refactr.git
cd refactr
git checkout ui-ux
```

## 2. Install
```
cd frontend
npm install
```

## 3. Environment variables
Create `frontend/.env.local` with:
```
NEXT_PUBLIC_API_URL=https://api.refactrapp.com
NEXT_PUBLIC_SUPABASE_URL=<ask Manas>
NEXT_PUBLIC_SUPABASE_ANON_KEY=<ask Manas>
```

## 4. Run
```
npm run dev
```
Open [http://localhost:3000](http://localhost:3000).

## Notes
- Next.js (App Router) + React + Tailwind + TypeScript. Pages live in `frontend/app/`.
- Pages like `/dashboard` and `/tailor` require a logged-in user — just sign up at `/signup` like a normal user would.
- Commit and push to the `ui-ux` branch. Manas will review before merging into `master`.
