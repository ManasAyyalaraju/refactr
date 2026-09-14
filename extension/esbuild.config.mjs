import * as esbuild from 'esbuild';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { cpSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const watch = process.argv.includes('--watch');
const prod = process.argv.includes('--prod');

const entryPoints = {
  background: 'src/background.ts',
  'content-script': 'src/content-script.ts',
  popup: 'src/popup.ts',
  'extract-injectable': 'src/extract-injectable.ts',
};

const buildOptions = {
  entryPoints: Object.fromEntries(
    Object.entries(entryPoints).map(([name, path]) => [name, join(__dirname, path)])
  ),
  bundle: true,
  outdir: join(__dirname, 'dist'),
  format: 'iife',
  target: 'chrome116',
  sourcemap: true,
  logLevel: 'info',
  // config.ts's API_BASE_URL/WEB_APP_URL default to localhost for `npm run
  // build`/`watch` (local dev, loaded unpacked from dist/); `npm run
  // build:prod` overrides both to the deployed URLs for the build that gets
  // pushed to extension-release.
  define: {
    'process.env.API_BASE_URL': JSON.stringify(prod ? 'https://api.refactrapp.com' : ''),
    'process.env.WEB_APP_URL': JSON.stringify(prod ? 'https://www.refactrapp.com' : ''),
  },
};

mkdirSync(join(__dirname, 'dist'), { recursive: true });

// Copy static assets (manifest, html, icons) into dist. manifest.json's
// "key" pins a fixed extension ID regardless of build - both dev and prod
// keep it identical on purpose, since the web app's login handoff
// (chrome.runtime.sendMessage(EXTENSION_ID, ...) in frontend/lib/extension.ts)
// only ever targets that one fixed ID. That also means you can switch
// between a locally-built dev copy and a downloaded prod copy without
// removing either first - "Load unpacked" on the other folder just
// re-points the same extension entry. The dev build's name/version_name get
// a "(Local Dev)" label so the two are visually distinguishable in
// chrome://extensions and the toolbar - the shipped prod build's identity
// stays untouched, since real users only ever see that one.
const manifest = JSON.parse(readFileSync(join(__dirname, 'manifest.json'), 'utf8'));
if (!prod) {
  manifest.name = `${manifest.name} (Local Dev)`;
  manifest.version_name = `${manifest.version} (Local Dev)`;
}
writeFileSync(join(__dirname, 'dist', 'manifest.json'), JSON.stringify(manifest, null, 2));
cpSync(join(__dirname, 'src', 'popup.html'), join(__dirname, 'dist', 'popup.html'));
cpSync(join(__dirname, 'src', 'panel.css'), join(__dirname, 'dist', 'panel.css'));
cpSync(join(__dirname, 'icons'), join(__dirname, 'dist', 'icons'), { recursive: true });

if (watch) {
  const ctx = await esbuild.context(buildOptions);
  await ctx.watch();
  console.log('Watching for changes...');
} else {
  await esbuild.build(buildOptions);
  console.log('Build complete.');
}
