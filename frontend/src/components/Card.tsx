import React from "react";

interface CardProps {
  title?: React.ReactNode;
  subtitle?: string;
  badge?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  headerBorder?: boolean;
  onClick?: () => void;
}

export const Card: React.FC<CardProps> = ({
  title,
  subtitle,
  badge,
  action,
  children,
  className = "",
  headerBorder = true,
  onClick,
}) => {
  return (
    <div
      onClick={onClick}
      className={`bg-[#0d1322] border border-[#1c263c] rounded-xl overflow-hidden shadow-lg transition-all hover:border-[#273754] ${className}`}
    >
      {(title || action || badge) && (
        <div
          className={`flex items-center justify-between px-5 py-3.5 bg-[#0a0f1d]/60 ${
            headerBorder ? "border-b border-[#1c263c]" : ""
          }`}
        >
          <div className="flex items-center gap-3">
            <div>
              {typeof title === "string" ? (
                <h3 className="text-sm font-semibold text-slate-100 tracking-tight">{title}</h3>
              ) : (
                title
              )}
              {subtitle && <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>}
            </div>
            {badge && <div>{badge}</div>}
          </div>
          {action && <div className="flex items-center gap-2">{action}</div>}
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );
};
