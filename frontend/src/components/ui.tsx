import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { cn } from "../lib/utils";

export function Button({
  className,
  variant = "default",
  size = "md",
  ...props
}: ComponentPropsWithoutRef<"button"> & {
  variant?: "default" | "secondary" | "ghost" | "outline";
  size?: "sm" | "md" | "icon";
}) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md border text-sm font-medium transition disabled:pointer-events-none disabled:opacity-50",
        variant === "default" &&
          "border-neutral-950 bg-neutral-950 text-white shadow-sm hover:bg-neutral-800",
        variant === "secondary" &&
          "border-neutral-200 bg-white text-neutral-900 shadow-sm hover:bg-neutral-50",
        variant === "ghost" &&
          "border-transparent bg-transparent text-neutral-700 hover:bg-neutral-100 hover:text-neutral-950",
        variant === "outline" &&
          "border-neutral-200 bg-transparent text-neutral-900 hover:bg-white",
        size === "sm" && "h-8 px-3",
        size === "md" && "h-10 px-4",
        size === "icon" && "h-9 w-9 p-0",
        className,
      )}
      {...props}
    />
  );
}

export function Card({
  className,
  ...props
}: ComponentPropsWithoutRef<"section">) {
  return (
    <section
      className={cn(
        "rounded-lg border border-neutral-200 bg-white shadow-sm shadow-neutral-950/[0.03]",
        className,
      )}
      {...props}
    />
  );
}

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "green" | "blue" | "amber" | "red" | "violet";
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center rounded-md border px-2 py-0.5 text-xs font-medium",
        tone === "neutral" && "border-neutral-200 bg-neutral-50 text-neutral-700",
        tone === "green" && "border-emerald-200 bg-emerald-50 text-emerald-700",
        tone === "blue" && "border-sky-200 bg-sky-50 text-sky-700",
        tone === "amber" && "border-amber-200 bg-amber-50 text-amber-700",
        tone === "red" && "border-rose-200 bg-rose-50 text-rose-700",
        tone === "violet" && "border-violet-200 bg-violet-50 text-violet-700",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Input({
  className,
  ...props
}: ComponentPropsWithoutRef<"input">) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-md border border-neutral-200 bg-white px-3 text-sm outline-none transition placeholder:text-neutral-400 focus:border-neutral-400 focus:ring-4 focus:ring-neutral-100",
        className,
      )}
      {...props}
    />
  );
}

export function Select({
  className,
  children,
  ...props
}: ComponentPropsWithoutRef<"select">) {
  return (
    <select
      className={cn(
        "h-10 rounded-md border border-neutral-200 bg-white px-3 text-sm outline-none focus:border-neutral-400 focus:ring-4 focus:ring-neutral-100",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}

export function Progress({ value, className }: { value: number; className?: string }) {
  return (
    <div className={cn("h-2 overflow-hidden rounded-full bg-neutral-100", className)}>
      <div
        className="h-full rounded-full bg-neutral-950 transition-all"
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

export function Avatar({ name, src }: { name: string; src?: string }) {
  return (
    <div className="grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-md bg-neutral-900 text-xs font-semibold text-white">
      {src ? <img className="h-full w-full object-cover" src={src} alt="" /> : initials(name)}
    </div>
  );
}

function initials(name: string) {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}
