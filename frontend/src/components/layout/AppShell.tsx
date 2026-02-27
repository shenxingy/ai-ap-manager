"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import { Sidebar } from "./Sidebar";
import { Button } from "@/components/ui/button";
import { LogOut, Menu, X } from "lucide-react";
import api from "@/lib/api";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { token, user, setAuth, logout } = useAuthStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);

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
      {/* Desktop Sidebar */}
      <div className="hidden md:flex">
        <Sidebar />
      </div>

      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Mobile Sidebar */}
      <div
        className={`fixed left-0 top-0 z-40 md:hidden transform transition-transform ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <Sidebar onClose={() => setSidebarOpen(false)} />
      </div>

      <div className="flex flex-col flex-1 min-w-0">
        {/* Top header */}
        <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200">
          <button
            className="md:hidden p-2 text-gray-600 hover:bg-gray-100 rounded-md"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            {sidebarOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </button>
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
