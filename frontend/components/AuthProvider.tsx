"use client";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { currentUser, type User } from "@/lib/api";

const AuthContext = createContext<{ user: User | null; loading: boolean }>({ user: null, loading: true });
export const useAuth = () => useContext(AuthContext);
export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const revision = useRef(0);
  useEffect(() => {
    let live = true;
    const changed = (event: Event) => { revision.current++; setUser((event as CustomEvent<User | null>).detail); setLoading(false); };
    window.addEventListener("qf-auth", changed);
    const version = revision.current;
    currentUser().then(value => { if (live && version === revision.current) setUser(value); })
      .catch(() => { if (live && version === revision.current) setUser(null); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; window.removeEventListener("qf-auth", changed); };
  }, []);
  return <AuthContext.Provider value={{ user, loading }}>{children}</AuthContext.Provider>;
}
export function RequireAuth({ children, admin = false }: { children: React.ReactNode; admin?: boolean }) {
  const { user, loading } = useAuth();
  if (loading) return <main className="mx-auto max-w-5xl p-10">Checking your session…</main>;
  if (!user) return <main className="mx-auto max-w-5xl p-10"><h1 className="text-2xl font-bold">Sign in to continue</h1><Link href="/login" className="mt-5 inline-block text-cyan-300">Sign in</Link></main>;
  if (admin && user.role !== "admin") return <main className="mx-auto max-w-5xl p-10">Administrator access is required.</main>;
  return <>{children}</>;
}
