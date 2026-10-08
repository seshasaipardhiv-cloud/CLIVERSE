import React from "react";
import { CheckCircle2, XCircle, AlertTriangle, ShieldCheck, Lock, HelpCircle, Info } from "lucide-react";

export type BadgeVariant =
  | "ALLOW"
  | "DENY"
  | "WARN"
  | "REQUIRE"
  | "ASK"
  | "OK_WITH_RESULTS"
  | "OK_EMPTY"
  | "ERROR"
  | "HEALTHY"
  | "CLEAN"
  | "MODIFIED"
  | "VERIFIED"
  | "TAMPERED"
  | "READY"
  | "ACTIVE";

interface StatusBadgeProps {
  status: string;
  size?: "sm" | "md" | "lg";
  showIcon?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = "md", showIcon = true }) => {
  const norm = (status || "").toUpperCase();

  let colorClasses = "bg-slate-800 text-slate-300 border-slate-700";
  let IconComponent = Info;

  switch (norm) {
    case "ALLOW":
    case "HEALTHY":
    case "CLEAN":
    case "OK_WITH_RESULTS":
    case "VERIFIED":
    case "ACTIVE":
    case "READY":
    case "SUCCESS":
    case "COMPLETED":
      colorClasses = "bg-emerald-950/70 text-emerald-300 border-emerald-500/40 shadow-[0_0_12px_rgba(16,185,129,0.15)]";
      IconComponent = CheckCircle2;
      break;

    case "DENY":
    case "BLOCK":
    case "ERROR":
    case "TAMPERED":
    case "FAILED":
    case "BLOCKED":
      colorClasses = "bg-red-950/70 text-red-300 border-red-500/40 shadow-[0_0_12px_rgba(239,68,68,0.15)]";
      IconComponent = XCircle;
      break;

    case "WARN":
    case "DEGRADED":
    case "MODIFIED":
    case "AWAITING_CONFIRMATION":
    case "WARN_CONFIRMED":
      colorClasses = "bg-amber-950/70 text-amber-300 border-amber-500/40";
      IconComponent = AlertTriangle;
      break;

    case "REQUIRE":
    case "ENFORCE":
      colorClasses = "bg-rose-950/70 text-rose-300 border-rose-500/40 shadow-[0_0_12px_rgba(244,63,94,0.15)]";
      IconComponent = ShieldCheck;
      break;

    case "ASK":
      colorClasses = "bg-amber-950/70 text-amber-300 border-amber-500/40";
      IconComponent = HelpCircle;
      break;

    case "OK_EMPTY":
      colorClasses = "bg-slate-900/80 text-slate-400 border-slate-700/60";
      IconComponent = Lock;
      break;

    default:
      colorClasses = "bg-slate-900 text-slate-300 border-slate-800";
      IconComponent = Info;
      break;
  }

  const sizeClasses = {
    sm: "px-2 py-0.5 text-xs gap-1 font-mono",
    md: "px-2.5 py-1 text-xs gap-1.5 font-medium font-mono",
    lg: "px-3 py-1.5 text-sm gap-2 font-semibold font-mono",
  }[size];

  return (
    <span
      className={`inline-flex items-center rounded-md border tracking-wide uppercase transition-colors ${colorClasses} ${sizeClasses}`}
    >
      {showIcon && <IconComponent className={size === "sm" ? "w-3 h-3" : size === "lg" ? "w-4 h-4" : "w-3.5 h-3.5"} />}
      <span>{norm.replace(/_/g, " ")}</span>
    </span>
  );
};
