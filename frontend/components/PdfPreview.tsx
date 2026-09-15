'use client';

import dynamic from 'next/dynamic';
import type { PdfPreviewProps } from './PdfPreviewImpl';

// react-pdf/pdfjs-dist touch `document` at module-evaluation time, which
// crashes under Next.js's default server-side render of client components
// (a 'use client' component still gets an initial SSR pass unless opted
// out). ssr: false defers loading the real implementation to the browser.
const PdfPreviewImpl = dynamic(() => import('./PdfPreviewImpl'), {
  ssr: false,
  loading: () => <div className="animate-pulse bg-black/[0.04]" />,
});

export default function PdfPreview(props: PdfPreviewProps) {
  return <PdfPreviewImpl {...props} />;
}
