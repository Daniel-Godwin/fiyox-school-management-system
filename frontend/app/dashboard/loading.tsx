import FiyoxLoader from "@/components/FiyoxLoader";

// Shown automatically by Next.js while a dashboard route is loading.
export default function DashboardLoading() {
  return <FiyoxLoader fullScreen label="Loading your workspace…" />;
}
