"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FileText,
  AlertTriangle,
  CheckSquare,
  Users,
  Building2,
  GitBranch,
} from "lucide-react";
import { useAuthStore } from "@/store/auth";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, roles: null },
  { href: "/invoices", label: "Invoices", icon: FileText, roles: null },
  { href: "/exceptions", label: "Exceptions", icon: AlertTriangle, roles: null },
  { href: "/approvals", label: "Approvals", icon: CheckSquare, roles: ["APPROVER", "ADMIN"] },
];

const adminItems = [
  { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/vendors", label: "Vendors", icon: Building2 },
  { href: "/admin/exception-routing", label: "Exception Routing", icon: GitBranch },
];

interface SidebarProps {
  onClose?: () => void;
}

export function Sidebar({ onClose }: SidebarProps) {
  const pathname = usePathname();
  const { user } = useAuthStore();

  const visible = navItems.filter(
    (item) => !item.roles || (user && item.roles.includes(user.role))
  );

  const isAdmin = user?.role === "ADMIN";

  return (
    <aside className="flex flex-col w-64 min-h-screen bg-gray-900 text-gray-100 md:static md:min-h-screen">
      <div className="px-6 py-5 border-b border-gray-700">
        <h1 className="text-lg font-bold tracking-tight">AI AP Manager</h1>
        <p className="text-xs text-gray-400 mt-0.5">Accounts Payable</p>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1">
        {visible.map(({ href, label, icon: Icon }) => {
          const isActive = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              onClick={onClose}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                isActive
                  ? "bg-gray-700 text-white"
                  : "text-gray-400 hover:bg-gray-800 hover:text-white"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </Link>
          );
        })}

        {isAdmin && (
          <div className="pt-4">
            <p className="px-3 mb-1 text-xs font-semibold uppercase tracking-wider text-gray-500">
              Admin
            </p>
            {adminItems.map(({ href, label, icon: Icon }) => {
              const isActive =
                pathname === href || pathname.startsWith(href + "/");
              return (
                <Link
                  key={href}
                  href={href}
                  onClick={onClose}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                    isActive
                      ? "bg-gray-700 text-white"
                      : "text-gray-400 hover:bg-gray-800 hover:text-white"
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {label}
                </Link>
              );
            })}
          </div>
        )}
      </nav>
    </aside>
  );
}
