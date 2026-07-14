"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, FileText, Sparkles, MessageCircle } from "lucide-react";

const TABS = [
  { href: "/results/live", label: "Home", Icon: Activity },
  { href: "/journal", label: "Journal", Icon: FileText },
  { href: "/insights", label: "Insights", Icon: Sparkles },
  { href: "/assistant", label: "Assistant", Icon: MessageCircle },
];

export default function BottomNav() {
  const pathname = usePathname();

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around px-2 pt-3 pb-6"
      style={{ background: "#0a1710", borderTop: "1px solid #1a3d2b" }}
    >
      {TABS.map(({ href, label, Icon }) => {
        const isActive = pathname === href || pathname?.startsWith(href + "/");
        const color = isActive ? "#c9a84c" : "#5c7568";
        return (
          <Link
            key={href}
            href={href}
            className="flex flex-col items-center gap-1 px-3 py-1 min-w-[64px]"
          >
            <Icon size={22} color={color} strokeWidth={isActive ? 2.5 : 2} />
            <span className="text-xs font-medium" style={{ color }}>
              {label}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}
