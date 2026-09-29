'use client';

import Link from 'next/link';
import { Copy, Github, Linkedin } from 'lucide-react';

export default function Footer() {
  return (
    <footer className="border-t border-black bg-white mt-auto">
      <div className="container mx-auto px-6 md:px-10 py-6">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <Copy className="w-5 h-5 text-black" strokeWidth={2.25} />
              <span className="text-[20px] font-bold text-black lowercase leading-none">refactr</span>
            </div>
            <p className="text-[15px] text-black">
              Built by <span className="font-bold">Manas Ayyalaraju</span>
            </p>
            <Link href="/privacy" className="text-[14px] text-black/60 hover:text-[#187fe7] transition-colors">
              Privacy Policy
            </Link>
          </div>

          <div className="flex items-center gap-2">
            <a
              href="https://github.com/ManasAyyalaraju"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center w-9 h-9 text-black hover:text-[#187fe7] transition-colors"
              aria-label="GitHub"
            >
              <Github className="w-5 h-5" />
            </a>
            <a
              href="https://www.linkedin.com/in/manas-ayyalaraju"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center w-9 h-9 text-black hover:text-[#187fe7] transition-colors"
              aria-label="LinkedIn"
            >
              <Linkedin className="w-5 h-5" />
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}

