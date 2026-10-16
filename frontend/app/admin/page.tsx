"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RequireAuth } from "@/components/AuthProvider";
import { RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import {
  adminMetrics, assessmentOptions, generateQuestions, getGenerationBatches, getQuestionCalibration,
  questionFactoryInventory, type GenerationBatch,
} from "@/lib/api";

type Inventory = { domain: string; difficulty: string; count: number };
const label = (value: string) => value.replaceAll("_", " ");

export default function Page() { return <RequireAuth admin><Admin/></RequireAuth>; }
function Admin() {
  const [metrics, setMetrics] = useState<any>(null);
  const [calibration, setCalibration] = useState<any>(null);
  const [inventory, setInventory] = useState<Inventory[]>([]);
  const [batches, setBatches] = useState<GenerationBatch[]>([]);
  const [domains, setDomains] = useState<string[]>([]);
  const [domain, setDomain] = useState("");
  const [difficulty, setDifficulty] = useState("medium");
  const [count, setCount] = useState(5);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refreshing = useRef(false);
  const mounted = useRef(false);

  const refresh = useCallback(async () => {
    if (refreshing.current) return;
    refreshing.current = true;
    try {
      const [m, i, o, b, c] = await Promise.all([
        adminMetrics(), questionFactoryInventory(), assessmentOptions(), getGenerationBatches(), getQuestionCalibration(),
      ]);
      if (!mounted.current) return;
      setMetrics(m);
      setCalibration(c);
      setInventory(i.inventory || []);
      setDomains(o.domains || []);
      setBatches(b.batches);
      setDomain(previous => previous || o.domains?.[0] || "");
      setError("");
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : "Could not refresh factory");
    } finally {
      refreshing.current = false;
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => { mounted.current = false; clearInterval(timer); };
  }, [refresh]);

  async function generate() {
    setBusy(true); setError(""); setMessage("");
    try {
      const response = await generateQuestions(domain, difficulty, count);
      setBatches(previous => [response.batch, ...previous.filter(b => b.id !== response.batch.id)].slice(0, 20));
      setMessage(`Saved all ${response.batch.requested} generation jobs. ${response.worker_notified
        ? "Workers will process the batch within the concurrency limit."
        : "Worker notification failed; jobs remain saved. Check Redis and the scheduler."}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create generation batch");
    } finally { setBusy(false); }
  }

  const grouped = useMemo(() => {
    const result: Record<string, Record<string, number>> = {};
    for (const row of inventory) {
      result[row.domain] ??= { easy: 0, medium: 0, hard: 0 };
      result[row.domain][row.difficulty] = row.count;
    }
    return result;
  }, [inventory]);
  const validCount = Number.isInteger(count) && count >= 1 && count <= 100;
  const activeBatches = batches.filter(b => b.completed < b.requested).length;

  return <main className="mx-auto max-w-7xl px-4 py-10 md:px-6">
    <div className="flex flex-wrap items-end justify-between gap-5">
      <div><p className="text-xs font-bold uppercase tracking-[.2em] text-cyan-300">Admin control room</p>
        <h1 className="mt-2 text-4xl font-black">Question Factory</h1>
        <p className="mt-3 max-w-3xl text-slate-400">Generate questions from reviewed mathematical models and curated CS facts. Track each batch through completion.</p>
      </div>
      <button onClick={() => void refresh()} className="inline-flex items-center gap-2 rounded-xl border border-white/10 px-4 py-3"><RefreshCw size={16}/>Refresh</button>
    </div>
    {error && <p role="alert" className="mt-5 rounded-xl border border-red-400/30 bg-red-400/10 p-4 text-red-200">{error}</p>}
    {message && <p role="status" className="mt-5 rounded-xl border border-cyan-400/30 bg-cyan-400/10 p-4 text-cyan-100">{message}</p>}

    <section className="mt-8 grid gap-4 sm:grid-cols-3">
      <div className="glass rounded-2xl p-5"><ShieldCheck size={18} className="text-cyan-300"/><p className="mt-3 text-sm text-slate-400">Active inventory</p><p className="mt-2 text-3xl font-black">{metrics?.active_questions ?? 0}</p></div>
      <div className="glass rounded-2xl p-5"><Sparkles size={18} className="text-cyan-300"/><p className="mt-3 text-sm text-slate-400">Processing batches (latest 20)</p><p className="mt-2 text-3xl font-black">{activeBatches}</p></div>
      <div className="glass rounded-2xl p-5"><p className="text-sm text-slate-400">Concurrent jobs per topic/difficulty</p><p className="mt-2 text-3xl font-black">{metrics?.generation_max_pending_per_bucket ?? "—"}</p><p className="mt-2 text-sm text-slate-500">Additional requested jobs stay pending.</p></div>
    </section>

    <section className="glass mt-8 rounded-3xl p-6">
      <h2 className="text-2xl font-black">Generate questions</h2>
      <p className="mt-2 text-sm text-slate-400">Answers, solutions and difficulty come from supported models. Optional AI adds reviewed context without changing the question.</p>
      <div className="mt-5 grid gap-4 md:grid-cols-4">
        <label className="text-sm">Topic<select value={domain} onChange={e => setDomain(e.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 p-3">{domains.map(d => <option key={d}>{d}</option>)}</select></label>
        <label className="text-sm">Difficulty<select value={difficulty} onChange={e => setDifficulty(e.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 p-3">{["easy", "medium", "hard"].map(d => <option key={d}>{d}</option>)}</select></label>
        <label className="text-sm">Questions<input type="number" min={1} max={100} value={Number.isNaN(count) ? "" : count} onChange={e => setCount(e.target.valueAsNumber)} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 p-3"/></label>
        <div className="flex items-end"><button disabled={busy || !domain || !validCount} onClick={() => void generate()} className="w-full rounded-xl bg-cyan-400 p-3 font-black text-slate-950 disabled:opacity-50">{busy ? "Saving batch…" : "Generate batch"}</button></div>
      </div>
    </section>

    <section className="glass mt-8 rounded-3xl p-6">
      <h2 className="text-2xl font-black">Batch progress</h2>
      <p className="mt-2 text-sm text-slate-400">Updates every five seconds. Rejected or failed jobs are reported; they are never counted as published questions.</p>
      <div className="mt-5 overflow-x-auto"><table className="w-full min-w-[900px] text-left text-sm">
        <thead className="text-slate-500"><tr>{["Batch", "Requested", "Pending", "Queued", "Running", "Published", "Rejected", "Failed", "Progress"].map(h => <th key={h} className="p-3">{h}</th>)}</tr></thead>
        <tbody>{batches.map(b => <tr key={b.id} className="border-t border-white/[.07] align-top">
          <td className="p-3"><p className="font-bold">{b.domain}</p><p className="mt-1 capitalize text-slate-400">{b.difficulty} · {label(b.status)}</p><p className="mt-1 text-xs text-slate-500">{new Date(b.created_at).toLocaleString()}</p><p className="mt-1 font-mono text-xs text-slate-500">{b.id.slice(0, 8)}</p>{Object.entries(b.reasons).map(([reason, n]) => <p key={reason} className="mt-1 text-xs text-amber-300">{label(reason)}: {n}</p>)}</td>
          <td className="p-3">{b.requested}</td><td className="p-3">{b.pending}</td><td className="p-3">{b.queued}</td><td className="p-3">{b.running}</td><td className="p-3 text-emerald-300">{b.succeeded}</td><td className="p-3 text-amber-300">{b.rejected}</td><td className="p-3 text-red-300">{b.failed}</td>
          <td className="p-3"><p>{b.completed}/{b.requested}</p><progress aria-label={`Batch ${b.id} completed jobs`} value={b.completed} max={b.requested} className="mt-2 h-2 w-24 accent-cyan-400"/></td>
        </tr>)}{!batches.length && <tr><td colSpan={9} className="p-6 text-center text-slate-500">No batches yet.</td></tr>}</tbody>
      </table></div>
    </section>

    <section className="glass mt-8 rounded-3xl p-6"><h2 className="text-2xl font-black">Validated inventory</h2><div className="mt-5 overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-slate-500"><tr>{["Topic", "Easy", "Medium", "Hard"].map(h => <th key={h} className="p-3">{h}</th>)}</tr></thead><tbody>{Object.entries(grouped).map(([topic, counts]) => <tr key={topic} className="border-t border-white/[.07]"><td className="p-3 font-bold">{topic}</td>{["easy", "medium", "hard"].map(d => <td key={d} className="p-3">{counts[d]}</td>)}</tr>)}</tbody></table></div></section>
    <section className="glass mt-8 rounded-3xl p-6"><h2 className="text-2xl font-black">Observed item difficulty</h2><p className="mt-2 text-sm text-slate-400">{calibration?.method} At least {calibration?.minimum_responses ?? 30} responses are required for a provisional band. Curated difficulty stays unchanged.</p><div className="mt-5 overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-slate-400"><tr>{["Item", "Topic", "Curated", "First responses", "Accuracy", "Observed"].map(h => <th key={h} className="p-3">{h}</th>)}</tr></thead><tbody>{calibration?.items?.map((item: any) => <tr key={item.question_id} className="border-t border-white/10"><td className="p-3 font-mono">{item.question_id.slice(0, 8)}</td><td className="p-3">{item.domain}</td><td className="p-3">{item.curated_difficulty}</td><td className="p-3">{item.first_exposures}</td><td className="p-3">{item.accuracy === null ? "—" : `${item.accuracy}%`}</td><td className="p-3">{label(item.observed_band)}</td></tr>)}</tbody></table></div></section>
  </main>;
}
