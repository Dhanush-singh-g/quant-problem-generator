"use client";
import { useCallback, useEffect, useState } from "react";
import { getSavedPracticeQuestions, savePracticeQuestion, type Question } from "@/lib/api";
import { RequireAuth } from "@/components/AuthProvider";
type Saved = Question & { solution: string | null; correct_option: string | null; review_available: boolean };
export default function Page() { return <RequireAuth><SavedPage/></RequireAuth>; }
function SavedPage() {
  const [items, setItems] = useState<Saved[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [offset, setOffset] = useState(0), [total, setTotal] = useState(0), [busy, setBusy] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const response = await getSavedPracticeQuestions(20, offset); setItems(response.questions); setTotal(response.total); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load saved questions"); }
    finally { setLoading(false); }
  }, [offset]);
  useEffect(() => { void load(); }, [load]);
  async function remove(id: string) {
    setBusy(id); setError("");
    try { await savePracticeQuestion(id, false); if (items.length === 1 && offset > 0) setOffset(Math.max(0, offset - 20)); else await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not remove saved question"); }
    finally { setBusy(null); }
  }
  return <main className="mx-auto max-w-4xl px-4 py-10"><h1 className="text-3xl font-black">Saved questions</h1><p className="mt-3 text-slate-400">Answers become available after you finish the practice set.</p>
    {error && <p role="alert" className="mt-5 text-red-300">{error}</p>}
    {loading ? <p className="mt-8">Loading…</p> : !items.length ? <p className="glass mt-8 rounded-2xl p-6">No saved questions yet.</p> : <div className="mt-8 space-y-4">{items.map(q => <article key={q.id} className="glass rounded-2xl p-6"><p className="text-sm text-cyan-300">{q.domain} · {q.difficulty}</p><h2 className="mt-3 whitespace-pre-line text-lg font-bold">{q.story_text}</h2><div className="mt-4 space-y-2">{Object.entries(q.options).map(([letter, value]) => <p key={letter}>{letter}. {value}</p>)}</div>
      {q.review_available ? <div className="mt-5 text-slate-300"><p>Correct option: {q.correct_option}</p><p className="mt-2">{q.solution}</p></div> : <p className="mt-5 text-slate-400">Finish this question’s set to unlock the solution.</p>}
      <button disabled={busy !== null} onClick={() => void remove(q.id)} className="mt-4 rounded-lg border border-white/15 px-4 py-2 disabled:opacity-40">{busy === q.id ? "Removing…" : "Remove"}</button></article>)}</div>}
    <div className="mt-6 flex items-center gap-4"><button disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))} className="disabled:opacity-30">Previous</button><span>{total ? `${offset + 1}–${Math.min(offset + 20, total)} of ${total}` : "0 saved"}</span><button disabled={loading || offset + 20 >= total} onClick={() => setOffset(offset + 20)} className="disabled:opacity-30">Next</button></div>
  </main>;
}
