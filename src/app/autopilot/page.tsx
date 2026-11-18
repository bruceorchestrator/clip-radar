import { AutopilotView } from "@/components/autopilot-view";

export const metadata = { title: "Autopilot · Clip Radar" };

export default function AutopilotPage() {
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6">
      <h1 className="text-3xl font-semibold tracking-tight">Autopilot</h1>
      <p className="mt-2 max-w-2xl text-muted">
        We watch the streamers, clip what their viewers are clipping, and queue the best clips here. Nothing is posted on its own: press Post on a clip you like and it goes to that channel.
      </p>
      <div className="mt-8">
        <AutopilotView />
      </div>
    </main>
  );
}
