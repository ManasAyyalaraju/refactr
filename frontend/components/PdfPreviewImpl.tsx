'use client';

import { useEffect, useRef, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/TextLayer.css';

// Renders each page to its own <canvas> via pdf.js, entirely under our
// control - unlike the native-viewer-in-an-iframe approach this replaces,
// there's no separate plugin tile boundary to misalign at fractional
// browser zoom (the cause of the hairline seams users were seeing).
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url
).toString();

export interface PdfPreviewProps {
  url: string;
  className?: string;
  /**
   * 'scroll' (default): renders every page, stacked, in a scrollable
   * container - for a full-document view (results pages, the expanded
   * dashboard modal, template previews).
   * 'fit': renders only page 1, scaled to exactly fill the container - for
   * small clickable thumbnails where the container already sets the
   * aspect ratio and there's no room to scroll.
   */
  mode?: 'scroll' | 'fit';
  onLoadError?: (error: Error) => void;
}

export default function PdfPreview({ url, className = '', mode = 'scroll', onLoadError }: PdfPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [numPages, setNumPages] = useState(0);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const observer = new ResizeObserver((entries) => {
      const measured = entries[0]?.contentRect.width;
      if (measured) setWidth(measured);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={containerRef}
      className={`${className} ${mode === 'scroll' ? 'overflow-y-auto overflow-x-hidden' : 'overflow-hidden'}`}
    >
      {width > 0 && (
        <Document
          file={url}
          onLoadSuccess={({ numPages: n }) => setNumPages(n)}
          onLoadError={onLoadError}
          loading={<p className="text-sm text-black/40 text-center py-16">Loading preview...</p>}
          error={<p className="text-sm text-black/40 text-center py-16">Couldn&apos;t load the PDF.</p>}
        >
          {mode === 'fit' ? (
            <Page pageNumber={1} width={width} renderTextLayer={false} renderAnnotationLayer={false} loading={null} />
          ) : (
            Array.from({ length: numPages }, (_, i) => (
              <Page
                key={i}
                pageNumber={i + 1}
                width={width}
                renderAnnotationLayer={false}
                loading={null}
                className={i > 0 ? 'mt-2' : undefined}
              />
            ))
          )}
        </Document>
      )}
    </div>
  );
}
