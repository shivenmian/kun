// Minimal shadcn-style primitives (Tailwind only, no Radix) — keeps the build
// offline-safe while matching the shadcn visual language. See web/README.md note.
import * as React from "react";
import { cn } from "../../lib/utils";

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-lg border border-neutral-800 bg-neutral-900/60 shadow-sm",
        className
      )}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex items-center justify-between border-b border-neutral-800 px-3 py-2",
        className
      )}
      {...props}
    />
  );
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn("text-xs font-semibold uppercase tracking-wide text-neutral-300", className)}
      {...props}
    />
  );
}

export function CardBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-3", className)} {...props} />;
}

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "outline" | "ghost";
  size?: "sm" | "md";
};

export function Button({ className, variant = "default", size = "md", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:pointer-events-none disabled:opacity-50",
        size === "sm" ? "h-7 px-2 text-xs" : "h-9 px-3 text-sm",
        variant === "default" && "bg-sky-600 text-white hover:bg-sky-500",
        variant === "outline" &&
          "border border-neutral-700 bg-transparent text-neutral-200 hover:bg-neutral-800",
        variant === "ghost" && "text-neutral-300 hover:bg-neutral-800",
        className
      )}
      {...props}
    />
  );
}

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-9 w-full rounded-md border border-neutral-700 bg-neutral-950 px-2 text-sm text-neutral-100 placeholder:text-neutral-500 focus:border-sky-500 focus:outline-none",
        className
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "w-full rounded-md border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm text-neutral-100 placeholder:text-neutral-500 focus:border-sky-500 focus:outline-none",
        className
      )}
      {...props}
    />
  );
}

export function Badge({
  className,
  color,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { color?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        className
      )}
      style={color ? { backgroundColor: `${color}22`, color, border: `1px solid ${color}55` } : undefined}
      {...props}
    />
  );
}

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn("mb-1 block text-[10px] uppercase tracking-wide text-neutral-500", className)}
      {...props}
    />
  );
}

export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-9 rounded-md border border-neutral-700 bg-neutral-950 px-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none",
        className
      )}
      {...props}
    />
  );
}

/** Lightweight backdrop modal (no Radix). Matches ForkDialog's visual language. */
export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: "md" | "lg";
}) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className={cn(
          "flex max-h-[90vh] w-full flex-col rounded-lg border border-neutral-700 bg-neutral-900 shadow-xl",
          size === "lg" ? "max-w-2xl" : "max-w-md"
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-neutral-800 px-4 py-3">
          <div>
            <h3 className="text-sm font-semibold text-neutral-100">{title}</h3>
            {subtitle && <div className="mt-0.5 text-[11px] text-neutral-500">{subtitle}</div>}
          </div>
          <button onClick={onClose} className="text-neutral-500 hover:text-neutral-200">
            ✕
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto px-4 py-3">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-neutral-800 px-4 py-3">{footer}</div>
        )}
      </div>
    </div>
  );
}
