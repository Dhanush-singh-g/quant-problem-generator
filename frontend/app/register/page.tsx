"use client";
import { FormEvent, useState } from "react";
import { register } from "@/lib/api";
import Link from "next/link";
import { useRouter } from "next/navigation";
export default function Register() {
  const [name, setName] = useState(""), [email, setEmail] = useState(""), [password, setPassword] = useState("");
  const [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const router = useRouter();
  async function go(e: FormEvent) {
    e.preventDefault(); if (busy) return; setBusy(true); setError("");
    try { await register(name.trim(), email, password); router.push("/quiz"); }
    catch (e) { setError(e instanceof Error ? e.message : "Registration failed"); }
    finally { setBusy(false); }
  }
  return <main className="mx-auto max-w-md px-6 py-12"><div className="glass rounded-3xl p-8"><h1 className="text-3xl font-black">Create account</h1><form onSubmit={go} className="mt-8 space-y-4">
    <label className="block">Name<input autoComplete="name" minLength={2} maxLength={120} value={name} onChange={e => setName(e.target.value)} required className="mt-2 w-full rounded-xl bg-slate-950 p-4"/></label>
    <label className="block">Email<input autoComplete="email" type="email" maxLength={255} value={email} onChange={e => setEmail(e.target.value)} required className="mt-2 w-full rounded-xl bg-slate-950 p-4"/></label>
    <label className="block">Password<input autoComplete="new-password" type="password" minLength={8} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} required className="mt-2 w-full rounded-xl bg-slate-950 p-4"/></label>
    <button disabled={busy || name.trim().length < 2} className="w-full rounded-xl bg-cyan-400 p-4 font-bold text-slate-950 disabled:opacity-50">{busy ? "Creating account…" : "Create account"}</button></form>
    {error && <p role="alert" className="mt-4 text-red-300">{error}</p>}<p className="mt-6 text-slate-400">Already registered? <Link className="text-cyan-300" href="/login">Sign in</Link></p></div></main>;
}
