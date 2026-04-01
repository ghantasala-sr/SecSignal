"use client";

import { Skeleton } from "@/components/ui/skeleton";

export function AnalysisSkeleton() {
  return (
    <div className="max-w-4xl space-y-6 animate-in fade-in duration-300">
      {/* Header badges skeleton */}
      <div className="flex items-center gap-1.5">
        <Skeleton className="h-5 w-24 rounded-full" />
        <Skeleton className="h-5 w-14 rounded-full" />
      </div>

      {/* Answer text skeleton */}
      <div className="space-y-2.5">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-[92%]" />
        <Skeleton className="h-4 w-[85%]" />
        <Skeleton className="h-4 w-[78%]" />
        <Skeleton className="h-4 w-[60%]" />
      </div>

      {/* Table skeleton */}
      <div className="space-y-1.5">
        <Skeleton className="h-8 w-full rounded-sm" />
        <Skeleton className="h-6 w-full rounded-sm opacity-60" />
        <Skeleton className="h-6 w-full rounded-sm opacity-60" />
        <Skeleton className="h-6 w-full rounded-sm opacity-60" />
      </div>

      {/* Chart skeletons */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded-lg border border-border/30 bg-card/50 p-4 space-y-3">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-[140px] w-full rounded" />
        </div>
        <div className="rounded-lg border border-border/30 bg-card/50 p-4 space-y-3">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-[140px] w-full rounded" />
        </div>
      </div>

      {/* Sources skeleton */}
      <div className="space-y-2">
        <Skeleton className="h-5 w-20" />
        <Skeleton className="h-14 w-full rounded-lg" />
        <Skeleton className="h-14 w-full rounded-lg opacity-60" />
      </div>
    </div>
  );
}
