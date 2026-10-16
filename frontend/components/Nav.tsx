"use client";
import Link from "next/link";
import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { BrainCircuit, LogOut } from "lucide-react";
import { logout } from "@/lib/api";
import { useAuth } from "./AuthProvider";

export default function Nav() {
  const { user, loading } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter(), path = usePathname();
  async function out() {
    setBusy(true); setError("");
    try { await logout(); router.push("/"); }
    catch (e) { setError(e instanceof Error ? e.message : "Sign out failed; retry."); }
    finally { setBusy(false); }
  }
  const links = [["/quiz", "Practice"], ["/assessments", "Assessments"], ...(user ? [["/analytics", "Profile"], ["/saved", "Saved"]] : []), ...(user?.role === "admin" ? [["/admin", "Factory"], ["/admin/assessments", "Manage exams"]] : [])];
  return <header className="sticky top-0 z-40 border-b border-white/10 bg-[#070b12]/95 backdrop-blur-xl">
    <div className="mx-auto max-w-7xl px-4 py-3 md:px-6">
      <div className="flex items-center justify-between gap-3">
        <Link href="/" className="flex items-center gap-3 font-black"><span className="rounded-xl bg-cyan-400 p-2 text-slate-950"><BrainCircuit size={22}/></span>QuantForge</Link>
        <div className="flex items-center gap-3">{loading ? <span className="text-sm text-slate-400">Checking session…</span> : user ? <><span className="text-sm">{user.name}</span><button disabled={busy} onClick={() => void out()} aria-label="Sign out" className="rounded-lg border border-white/10 p-2 disabled:opacity-50"><LogOut size={18}/></button></> : <Link href="/login" className="rounded-xl bg-cyan-400 px-4 py-2 font-bold text-slate-950">Sign in</Link>}</div>
      </div>
      <nav aria-label="Main navigation" className="mt-3 flex gap-2 overflow-x-auto pb-1">{links.map(([href, title]) => <Link key={href} href={href} aria-current={path === href ? "page" : undefined} className={`shrink-0 rounded-lg px-3 py-2 text-sm font-semibold ${path === href ? "bg-cyan-400/10 text-cyan-300" : "text-slate-400 hover:bg-white/5"}`}>{title}</Link>)}</nav>
      {error && <p role="alert" className="mt-2 text-sm text-red-300">{error}</p>}
    </div>
  </header>;
}
