export const SUPABASE_URL = 'https://ajchqijmzaxdphlaadeh.supabase.co';
export const SUPABASE_ANON_KEY =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFqY2hxaWptemF4ZHBobGFhZGVoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY3MTY4MjIsImV4cCI6MjA5MjI5MjgyMn0.0sxDJH1hftzOlsupmmQBmu3DWdWUhSaxvQM9UtdvTAQ';

// `npm run build`/`watch` (local dev) leaves this at localhost; `npm run
// build:prod` (the build pushed to extension-release) overrides it via
// esbuild's `define` - see esbuild.config.mjs.
export const API_BASE_URL = process.env.API_BASE_URL || 'http://localhost:8000';

export const WEB_APP_URL = 'https://www.refactrapp.com';
