"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuthStore } from "@/store/auth";
import { Sidebar } from "./Sidebar";
import { Button } from "@/components/ui/button";
import { Bell, LogOut, Menu, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { AskAiPanel } from "@/components/AskAiPanel";

interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
  invoice_id: string | null;
  read_at: string | null;
  created_at: string;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { token, user, setAuth, logout } = useAuthStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const notifRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  const { data: notifications = [] } = useQuery<Notification[]>({
    queryKey: ["notifications"],
    queryFn: () => api.get("/notifications").then((r) => r.data),
    refetchInterval: 30000,
    enabled: !!(token && user),
  });

  const unreadCount = notifications.filter((n) => !n.read_at).length;

  const markAllRead = useMutation({
    mutationFn: () => api.post("/notifications/read-all"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotifOpen(false);
      }
    }
    if (notifOpen) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [notifOpen]);

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
            {token && user && (
              <div className="relative" ref={notifRef}>
                <Button
                  variant="ghost"
                  size="icon"
                  className="relative"
                  onClick={() => setNotifOpen((v) => !v)}
                >
                  <Bell className="h-5 w-5" />
                  {unreadCount > 0 && (
                    <span className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-red-500 text-xs text-white flex items-center justify-center">
                      {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                  )}
                </Button>
                {notifOpen && (
                  <div className="absolute right-0 mt-2 w-80 bg-white border border-gray-200 rounded-lg shadow-lg z-50">
                    <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100">
                      <span className="text-sm font-semibold text-gray-700">Notifications</span>
                      {unreadCount > 0 && (
                        <button
                          className="text-xs text-blue-600 hover:underline"
                          onClick={() => markAllRead.mutate()}
                        >
                          Mark all read
                        </button>
                      )}
                    </div>
                    <div className="max-h-80 overflow-y-auto">
                      {notifications.length === 0 ? (
                        <p className="text-sm text-gray-500 px-4 py-6 text-center">No notifications</p>
                      ) : (
                        notifications.slice(0, 10).map((n) => (
                          <div
                            key={n.id}
                            className={`px-4 py-3 border-b border-gray-50 last:border-0 ${!n.read_at ? "bg-blue-50" : ""}`}
                          >
                            <p className="text-sm font-medium text-gray-800">{n.title}</p>
                            <p className="text-xs text-gray-500 mt-0.5">{n.message}</p>
                            {n.invoice_id && (
                              <Link
                                href={`/invoices/${n.invoice_id}`}
                                className="text-xs text-blue-600 hover:underline mt-1 inline-block"
                                onClick={() => setNotifOpen(false)}
                              >
                                View invoice
                              </Link>
                            )}
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
            <AskAiPanel />
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
