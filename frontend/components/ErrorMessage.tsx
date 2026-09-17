'use client';

import { AlertCircle } from 'lucide-react';

interface ErrorMessageProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export default function ErrorMessage({
  title = 'Something went wrong',
  message,
  onRetry
}: ErrorMessageProps) {
  return (
    <div className="bg-[#fffcfc] border border-[#504b4b] rounded-[4px] p-6 flex gap-4">
      <div className="flex-shrink-0 w-9 h-9 rounded-full bg-red-50 flex items-center justify-center">
        <AlertCircle className="w-[18px] h-[18px] text-red-600" />
      </div>

      <div className="flex-1 min-w-0">
        <h3 className="font-semibold text-[16px] tracking-[-0.32px] text-black mb-1">
          {title}
        </h3>
        <p className="text-[14px] tracking-[-0.28px] text-black/70 leading-relaxed">
          {message}
        </p>

        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-4 inline-flex items-center justify-center bg-white border border-black text-black hover:bg-gray-50 font-semibold text-[14px] px-5 py-2 rounded-[10px] transition-colors cursor-pointer"
          >
            Dismiss
          </button>
        )}
      </div>
    </div>
  );
}

