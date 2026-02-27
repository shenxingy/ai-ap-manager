"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import { Sidebar } from "./Sidebar";
import { Button } from "@/components/ui/button";
import { LogOut } from "lucide-react";
import api from "@/lib/api";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { token, user, setAuth, logout } = useAuthStore();

  // Auth guard
  useEffect(() => {
    if (!token) {
      router.push("/login");
    }
  }, [token, router]);

  // Fetch /users/me to hydrate user on mount
  useEffect(() => {
    if (token && !user) {
      api.get("/users/me").then((res) => {
        setAuth(token, res.data);
      }).catch(() => {
        logout();
        router.push("/login");
      });
    }
  }, [token, user, setAuth, logout, router]);

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  if (!token) return null;

  return (
    <div className="flex min-h-screen bg-gray-50">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        {/* Top header */}
        <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200">
          <div />
          <div className="flex items-center gap-3">
            {user && (
              <span className="text-sm text-gray-600">
                {user.name} <span className="text-gray-400">({user.role})</span>
              </span>
            )}
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              <LogOut className="h-4 w-4 mr-1" />
              Logout
            </Button>
          </div>
        </header>
        {/* Main content */}
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
