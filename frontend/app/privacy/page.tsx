import type { Metadata } from 'next';
import Link from 'next/link';
import Header from '@/components/Header';
import Footer from '@/components/Footer';

export const metadata: Metadata = {
  title: 'Privacy Policy – refactr',
  description: 'What data refactr and the refactr Chrome extension collect, and how it is used.',
};

const CONTACT_EMAIL = 'manas.ayyalaraju@gmail.com';
const LAST_UPDATED = 'September 28, 2026';

const sections: { heading: string; body: React.ReactNode }[] = [
  {
    heading: 'What we collect',
    body: (
      <ul className="list-disc pl-6 flex flex-col gap-2">
        <li>
          <strong>Account information</strong>: your email address and display name, used to sign you in.
        </li>
        <li>
          <strong>Resumes</strong>: the resumes you upload, and the reformatted and tailored versions refactr
          generates from them.
        </li>
        <li>
          <strong>Job descriptions</strong>: the text of job postings you tailor a resume against, saved with the
          tailored result.
        </li>
      </ul>
    ),
  },
  {
    heading: 'The Chrome extension',
    body: (
      <>
        <p>
          The extension runs only on job pages on LinkedIn, Indeed, Glassdoor, and Handshake. It reads the job
          posting on the page (title, company, and description) to recognize the job and offer to tailor your
          resume. Nothing from the page leaves your browser until you choose to tailor a resume, at which point the
          job description is sent to refactr as described below.
        </p>
        <p>
          The extension does not read your browsing history, other websites, or anything else on the page. It
          stores your refactr sign-in session locally in Chrome so you stay signed in.
        </p>
      </>
    ),
  },
  {
    heading: 'How your data is used',
    body: (
      <>
        <p>
          Your data is used only to provide refactr: to parse, reformat, and tailor your resume, render it as a PDF,
          and show you your saved resumes. We do not sell your data, use it for advertising, or share it with
          anyone except the service providers below, and only as needed to run refactr.
        </p>
        <p>
          The use of information received from Google APIs and the Chrome extension adheres to the{' '}
          <a
            href="https://developer.chrome.com/docs/webstore/program-policies/limited-use"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[#187fe7] hover:text-[#146bc7]"
          >
            Chrome Web Store User Data Policy
          </a>
          , including the Limited Use requirements.
        </p>
      </>
    ),
  },
  {
    heading: 'Service providers',
    body: (
      <ul className="list-disc pl-6 flex flex-col gap-2">
        <li>
          <strong>OpenAI</strong> processes resume and job description text to parse and tailor your resume.
          Under OpenAI&apos;s API terms, this data is not used to train their models.
        </li>
        <li>
          <strong>Supabase</strong> stores your account, resumes, and tailored results.
        </li>
        <li>
          <strong>Render</strong> and <strong>Vercel</strong> host the refactr servers and website.
        </li>
      </ul>
    ),
  },
  {
    heading: 'Storage and security',
    body: (
      <p>
        Your resumes are stored in private storage that only your account can access. Data is encrypted in transit
        (HTTPS). refactr does not use analytics or advertising trackers.
      </p>
    ),
  },
  {
    heading: 'Deleting your data',
    body: (
      <p>
        You can delete saved resumes at any time from your{' '}
        <Link href="/profile" className="text-[#187fe7] hover:text-[#146bc7]">
          profile
        </Link>
        . To delete your account and all associated data, email{' '}
        <a href={`mailto:${CONTACT_EMAIL}`} className="text-[#187fe7] hover:text-[#146bc7]">
          {CONTACT_EMAIL}
        </a>{' '}
        and it will be removed within 30 days. Uninstalling the extension removes everything it stored in your
        browser.
      </p>
    ),
  },
  {
    heading: 'Changes',
    body: <p>If this policy changes, the updated version will be posted on this page with a new date.</p>,
  },
];

export default function PrivacyPage() {
  return (
    <div className="min-h-screen flex flex-col">
      <Header />

      <main className="flex-1 pt-24 pb-16 px-6 md:px-10 bg-white">
        <div className="container mx-auto max-w-3xl">
          <h1 className="font-bold text-[36px] md:text-[48px] leading-[1.05] tracking-[-1.12px] text-black mb-3">
            Privacy Policy
          </h1>
          <p className="text-black/60 mb-10">Last updated {LAST_UPDATED}</p>

          <div className="flex flex-col gap-10 text-[16px] leading-relaxed text-black/80">
            {sections.map((section) => (
              <section key={section.heading} className="flex flex-col gap-3">
                <h2 className="font-semibold text-[22px] md:text-[26px] tracking-[-0.52px] text-black">
                  {section.heading}
                </h2>
                {section.body}
              </section>
            ))}

            <p>
              Questions? Email{' '}
              <a href={`mailto:${CONTACT_EMAIL}`} className="text-[#187fe7] hover:text-[#146bc7]">
                {CONTACT_EMAIL}
              </a>
              .
            </p>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
