"use client";

import Link from "next/link";
import { useEffect } from "react";
import Icon from "@/components/Icon";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // surfaced in the browser console only; no user data is sent anywhere
    console.error(error);
  }, [error]);

  return (
    <div role="alert" className="mx-auto max-w-md py-16 text-center">
      <Icon name="alert" className="mx-auto h-10 w-10 text-amber-500" />
      <h1 className="mt-4 text-2xl font-semibold">Something went wrong</h1>
      <p className="mt-2 text-slate-600">
        We couldn&apos;t load this page. The event service may be temporarily unavailable.
      </p>
      <div className="mt-6 flex justify-center gap-3">
        <button type="button" onClick={reset} className="btn-primary">Try again</button>
        <Link href="/" className="btn-secondary">Home</Link>
      </div>
      {error.digest && <p className="mt-4 text-xs text-slate-500">Reference: {error.digest}</p>}
    </div>
  );
}
