import React from "react";
import { useApp } from "../context/AppContext";
import { CheckCircle2, XCircle, AlertTriangle, Info, X } from "lucide-react";

export const ToastContainer: React.FC = () => {
  const { toasts, dismissToast } = useApp();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2.5 max-w-md w-full pointer-events-none">
      {toasts.map((t) => {
        let borderClass = "border-slate-700 bg-[#0e1627]";
        let IconComp = Info;
        let iconColor = "text-emerald-400";

        if (t.type === "success") {
          borderClass = "border-emerald-500/40 bg-[#091817] shadow-[0_0_15px_rgba(16,185,129,0.2)]";
          IconComp = CheckCircle2;
          iconColor = "text-emerald-400";
        } else if (t.type === "error") {
          borderClass = "border-red-500/40 bg-[#1c0f14] shadow-[0_0_15px_rgba(239,68,68,0.2)]";
          IconComp = XCircle;
          iconColor = "text-red-400";
        } else if (t.type === "warn") {
          borderClass = "border-amber-500/40 bg-[#1f170b]";
          IconComp = AlertTriangle;
          iconColor = "text-amber-400";
        }

        return (
          <div
            key={t.id}
            className={`pointer-events-auto flex items-start gap-3 p-4 rounded-xl border shadow-xl backdrop-blur-md transition-all animate-in slide-in-from-right-4 duration-200 ${borderClass}`}
          >
            <IconComp className={`w-5 h-5 flex-shrink-0 mt-0.5 ${iconColor}`} />
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-semibold text-slate-100">{t.title}</h4>
              {t.message && <p className="text-xs text-slate-300 mt-0.5 break-words">{t.message}</p>}
            </div>
            <button
              onClick={() => dismissToast(t.id)}
              className="text-slate-400 hover:text-slate-100 p-0.5"
              aria-label="Dismiss toast"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
};
