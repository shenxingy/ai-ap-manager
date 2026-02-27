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
  BarChart2,
  Upload,
  Layers,
  RepeatIcon,
  ShieldAlert,
  Settings,
  BookOpen,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { useAuthStore } from "@/store/auth";
import { cn } from "@/lib/utils";

// ─── Nav Structure ───

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

interface NavSection {
  sectionLabel: string | null;
  allowedRoles: string[] | null; // null = visible to everyone authenticated
  items: NavItem[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    sectionLabel: null,
    allowedRoles: null,
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/invoices", label: "Invoices", icon: FileText },
      { href: "/exceptions", label: "Exceptions", icon: AlertTriangle },
      { href: "/approvals", label: "Approvals", icon: CheckSquare },
    ],
  },
  {
    sectionLabel: "Analytics",
    allowedRoles: ["AP_ANALYST", "ADMIN"],
    items: [
      { href: "/analytics", label: "Analytics", icon: BarChart2 },
      { href: "/admin/fraud", label: "Fraud Incidents", icon: ShieldAlert },
      { href: "/admin/recurring-patterns", label: "Recurring Patterns", icon: RepeatIcon },
      { href: "/admin/ai-insights", label: "AI Insights", icon: Sparkles },
      { href: "/admin/vendors", label: "Vendors", icon: Building2 },
    ],
  },
  {
    sectionLabel: "Admin",
    allowedRoles: ["ADMIN"],
    items: [
      { href: "/admin/users", label: "Users", icon: Users },
      { href: "/admin/approval-matrix", label: "Approval Matrix", icon: Layers },
      { href: "/admin/rules", label: "Policy Rules", icon: BookOpen },
      { href: "/admin/import", label: "Import", icon: Upload },
      { href: "/admin/settings", label: "Email Settings", icon: Settings },
      { href: "/admin/exception-routing", label: "Exception Routing", icon: GitBranch },
    ],
  },
];

// ─── Sidebar ───

interface SidebarProps {
  onClose?: () => void;
}

export function Sidebar({ onClose }: SidebarProps) {
  const pathname = usePathname();
  const { user } = useAuthStore();

  const userRole = user?.role ?? "";

  const visibleSections = NAV_SECTIONS.filter(
    (section) => !section.allowedRoles || section.allowedRoles.includes(userRole)
  );

  return (
    <aside className="flex flex-col w-64 min-h-screen bg-gray-900 text-gray-100 md:static md:min-h-screen">
      <div className="px-6 py-5 border-b border-gray-700">
        <h1 className="text-lg font-bold tracking-tight">AI AP Manager</h1>
        <p className="text-xs text-gray-400 mt-0.5">Accounts Payable</p>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1">
        {visibleSections.map((section, idx) => (
          <div key={idx} className={section.sectionLabel ? "pt-4" : ""}>
            {section.sectionLabel && (
              <p className="px-3 mb-1 text-xs font-semibold uppercase tracking-wider text-gray-500">
                {section.sectionLabel}
              </p>
            )}
            {section.items.map(({ href, label, icon: Icon }) => {
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
          </div>
        ))}
      </nav>
    </aside>
  );
}
