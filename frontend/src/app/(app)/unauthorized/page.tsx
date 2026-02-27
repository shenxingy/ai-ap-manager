import Link from "next/link";
import { Lock } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function UnauthorizedPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center space-y-6">
      <div className="flex items-center justify-center w-16 h-16 rounded-full bg-red-100">
        <Lock className="w-8 h-8 text-red-600" />
      </div>
      <div className="space-y-2">
        <h1 className="text-3xl font-bold text-gray-900">403 — Access Denied</h1>
        <p className="text-gray-500 max-w-sm">
          You don&apos;t have permission to view this page.
        </p>
      </div>
      <Button asChild>
        <Link href="/dashboard">Go to Dashboard</Link>
      </Button>
    </div>
  );
}
