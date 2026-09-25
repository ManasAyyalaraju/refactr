'use client';

import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import type { GeneratedResumeRow } from '@/lib/supabase/resumes';
import { computeApplicationStats } from '@/lib/dashboard-stats';

interface DashboardStatsProps {
  rows: GeneratedResumeRow[];
  baseResumeCount: number;
  loading: boolean;
}

export default function DashboardStats({ rows, baseResumeCount, loading }: DashboardStatsProps) {
  const stats = computeApplicationStats(rows);

  return (
    <div className="flex-1 min-w-0 bg-[#fffcfc] border border-black rounded flex flex-col min-h-[260px] sm:min-h-[400px] lg:min-h-[602px]">
      <div className="border-b border-black px-6 flex items-center h-[50px] sm:h-[58px] flex-shrink-0">
        <h2 className="text-[20px] font-semibold text-black">Dashboard</h2>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-sm text-black/50">Loading…</span>
        </div>
      ) : stats.total === 0 ? (
        <div className="flex-1 flex items-center justify-center px-6 text-center">
          <p className="text-sm text-black/50">
            Tailor a resume to a job description to start seeing stats about your applications here.
          </p>
        </div>
      ) : (
        <div className="p-6 flex flex-col gap-6 overflow-y-auto">
          {/* Stat tiles */}
          <div className="grid grid-cols-3 gap-3">
            <div className="border border-black/[0.19] rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-black">{stats.total}</p>
              <p className="text-[11px] text-black/50 mt-1">Total Tailored</p>
            </div>
            <div className="border border-black/[0.19] rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-black">{stats.avgScore !== null && stats.avgScore !== undefined ? `${stats.avgScore}%` : '—'}</p>
              <p className="text-[11px] text-black/50 mt-1">Avg Match Score</p>
            </div>
            <div className="border border-black/[0.19] rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-black">{baseResumeCount}</p>
              <p className="text-[11px] text-black/50 mt-1">Resumes on File</p>
            </div>
          </div>

          <div className="grid sm:grid-cols-2 gap-6">
            {/* Top roles */}
            <div>
              <h3 className="text-[13px] font-semibold text-black mb-2">Top Roles</h3>
              {stats.topRoles.length === 0 ? (
                <p className="text-[13px] text-black/40">Not enough data yet.</p>
              ) : (
                <ul className="space-y-1.5">
                  {stats.topRoles.map((r) => (
                    <li key={r.role} className="flex items-center justify-between text-[13px]">
                      <span className="truncate text-black/80">{r.role}</span>
                      <span className="text-black/40 flex-shrink-0 ml-2">{r.count}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Industries */}
            <div>
              <h3 className="text-[13px] font-semibold text-black mb-2">Industries (estimated)</h3>
              {stats.topIndustries.length === 0 ? (
                <p className="text-[13px] text-black/40">Not enough data yet.</p>
              ) : (
                <ul className="space-y-1.5">
                  {stats.topIndustries.map((ind) => (
                    <li key={ind.industry} className="flex items-center justify-between text-[13px]">
                      <span className="truncate text-black/80">{ind.industry}</span>
                      <span className="text-black/40 flex-shrink-0 ml-2">{ind.count}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* Recent activity */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-[13px] font-semibold text-black">Recent Activity</h3>
              <Link href="/tailored" className="text-[12px] text-[#187fe7] hover:underline">
                View all
              </Link>
            </div>
            <div className="border border-black/[0.19] rounded-lg overflow-hidden">
              {stats.recentActivity.map((item, i) => (
                <Link
                  key={item.id}
                  href={`/tailored/${item.id}`}
                  className={`flex items-center justify-between gap-3 px-3 py-2.5 hover:bg-black/[0.03] transition-colors ${
                    i !== stats.recentActivity.length - 1 ? 'border-b border-black/[0.12]' : ''
                  }`}
                >
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium text-black truncate">{item.title}</p>
                    {item.company && <p className="text-[11px] text-black/40 truncate">{item.company}</p>}
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {item.score !== null && (
                      <span className="text-[11px] px-2 py-0.5 rounded-full bg-black/5 text-black/60">
                        {item.score}%
                      </span>
                    )}
                    <ChevronRight className="w-3.5 h-3.5 text-black/30" />
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
