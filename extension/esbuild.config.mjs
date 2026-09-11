import * as esbuild from 'esbuild';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { cpSync, mkdirSync } from 'node:fs';

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
  // config.ts's API_BASE_URL defaults to localhost for `npm run build`/`watch`
  // (local dev, loaded unpacked from dist/); `npm run build:prod` overrides it
  // to the deployed backend for the build that gets pushed to extension-release.
  define: {
    'process.env.API_BASE_URL': JSON.stringify(prod ? 'https://api.refactrapp.com' : ''),
  },
};

mkdirSync(join(__dirname, 'dist'), { recursive: true });

// Copy static assets (manifest, html, icons) into dist
cpSync(join(__dirname, 'manifest.json'), join(__dirname, 'dist', 'manifest.json'));
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
