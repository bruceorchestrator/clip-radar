import { Suspense } from "react";
import { JobView } from "@/components/job-view";

async function Loader({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <JobView id={id} />;
}

export default function JobPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6">
      <Suspense fallback={<p className="text-muted">Loading…</p>}>
        <Loader params={params} />
      </Suspense>
    </main>
  );
}
