"use client";
import { useEffect, useState } from "react";
import { RequireAuth } from "@/components/AuthProvider";
import { useDraft } from "@/hooks/useDraft";
import { abandonPractice, assessmentOptions, getActivePractice, getPracticeInventory, getPracticeSession, getQuiz,
  savePracticeDraft, savePracticeQuestion, submitQuiz, type PracticeInventory, type PracticeSession } from "@/lib/api";

export default function Page() { return <RequireAuth><Practice/></RequireAuth>; }
function Practice() {
  const [domains, setDomains] = useState<string[]>([]), [domain, setDomain] = useState("ALL"), [difficulty, setDifficulty] = useState("medium");
  const [count, setCount] = useState(5), [mode, setMode] = useState<"unseen" | "revision">("unseen");
  const [inventory, setInventory] = useState<PracticeInventory>({ unseen: [], revision: [] });
  const [session, setSession] = useState<PracticeSession | null>(null), [answers, setAnswers] = useState<Record<string, string>>({});
  const [index, setIndex] = useState(0), [saved, setSaved] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0), [serverOffset, setServerOffset] = useState(0);
  const draft = useDraft(savePracticeDraft);

  function install(value: PracticeSession) {
    setSession(value); setAnswers(value.answers); setIndex(value.current_index); setDomain(value.domain);
    setDifficulty(value.difficulty); setMode(value.mode as "unseen" | "revision");
    setServerOffset(Date.parse(value.server_time) - Date.now());
    draft.restore(value.session_id, value.answers, value.current_index, value.revision);
    if (value.status !== "active") draft.stop();
    window.history.replaceState(null, "", `/quiz?session=${value.session_id}`);
  }
  useEffect(() => {
    let live = true;
    async function load() {
      try {
        const params = new URLSearchParams(window.location.search);
        const [options, available, active] = await Promise.all([assessmentOptions(), getPracticeInventory(),
          params.get("session") ? getPracticeSession(params.get("session")!).then(s => ({ session: s })) : getActivePractice()]);
        if (!live) return;
        setDomains(options.domains); setInventory(available);
        if (active.session?.status !== "abandoned" && active.session) install(active.session);
        else if (params.get("domain") && options.domains.includes(params.get("domain"))) setDomain(params.get("domain")!);
      } catch (e) { if (live) setError(e instanceof Error ? e.message : "Could not load practice"); }
      finally { if (live) setLoading(false); }
    }
    void load(); return () => { live = false; };
    // Initial restore only; subsequent changes are kept in state and saved separately.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!session || session.status !== "active") return;
    const tick = () => setElapsed(Math.max(0, Math.floor((Date.now() + serverOffset - Date.parse(session.started_at)) / 1000)));
    tick(); const timer = setInterval(tick, 1000); return () => clearInterval(timer);
  }, [session, serverOffset]);

  async function start() {
    setBusy(true); setError("");
    try { setSaved(new Set()); install(await getQuiz(count, domain, difficulty, mode)); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not start practice"); }
    finally { setBusy(false); }
  }
  function choose(next: Record<string, string>, position = index) { setAnswers(next); setIndex(position); draft.change(next, position); }
  async function finish() {
    if (!session || busy) return;
    setBusy(true); setError("");
    try {
      await draft.flush();
      const result = await submitQuiz(session.session_id, Object.entries(answers).map(([question_id, selected_option]) => ({ question_id, selected_option })));
      draft.stop(); setSession({ ...session, status: "submitted", result });
    } catch (e) { setError(e instanceof Error ? e.message : "Could not submit set"); }
    finally { setBusy(false); }
  }
  async function reset(abandon = false) {
    if (!session) return;
    setBusy(true); setError("");
    try {
      if (abandon) { await draft.flush(); await abandonPractice(session.session_id); }
      draft.stop(); setSession(null); setAnswers({}); setIndex(0); window.history.replaceState(null, "", "/quiz");
      setInventory(await getPracticeInventory());
    } catch (e) { setError(e instanceof Error ? e.message : "Could not leave set"); }
    finally { setBusy(false); }
  }
  async function bookmark(id: string) {
    try { await savePracticeQuestion(id, true); setSaved(previous => new Set([...previous, id])); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not save question"); }
  }
  const available = inventory[mode].filter(row => (domain === "ALL" || row.domain === domain) && (difficulty === "ALL" || row.difficulty === difficulty)).reduce((sum, row) => sum + row.count, 0);
  const q = session?.questions[index];
  if (loading) return <main className="mx-auto max-w-6xl p-10">Restoring your practice…</main>;
  return <main className="mx-auto max-w-6xl px-4 py-10">
    {error && <p role="alert" className="mb-6 rounded-xl border border-red-300/30 p-4 text-red-300">{error}</p>}
    {!session ? <section className="glass mx-auto max-w-2xl rounded-3xl p-7">
      <h1 className="text-3xl font-black">Build your practice set</h1>
      <p className="mt-3 text-slate-400">Progress saves to your account. Finish a set to review answers and update your profile.</p>
      <div className="mt-6 grid gap-5 sm:grid-cols-2">
        <label>Topic<select value={domain} onChange={e => setDomain(e.target.value)} className="mt-2 w-full rounded-xl bg-slate-950 p-3"><option value="ALL">All topics</option>{domains.map(d => <option key={d}>{d}</option>)}</select></label>
        <label>Difficulty<select value={difficulty} onChange={e => setDifficulty(e.target.value)} className="mt-2 w-full rounded-xl bg-slate-950 p-3">{["easy", "medium", "hard", "ALL"].map(b => <option key={b} value={b}>{b === "ALL" ? "Mixed" : b}</option>)}</select></label>
        <label>Mode<select value={mode} onChange={e => setMode(e.target.value as "unseen" | "revision")} className="mt-2 w-full rounded-xl bg-slate-950 p-3"><option value="unseen">New questions</option><option value="revision">Revision of completed questions</option></select></label>
        <label>Set size<input type="number" min={1} max={20} value={Number.isNaN(count) ? "" : count} onChange={e => setCount(e.target.valueAsNumber)} className="mt-2 w-full rounded-xl bg-slate-950 p-3"/></label>
      </div>
      <p role="status" className="mt-5 text-cyan-300">{available} questions available for your account and selection.</p>
      {available < count && <p className="mt-2 text-sm text-amber-200">Choose a smaller set, another topic, or revision mode. An administrator can generate more questions.</p>}
      <button disabled={busy || !Number.isInteger(count) || count < 1 || count > 20 || count > available} onClick={() => void start()} className="mt-6 w-full rounded-xl bg-cyan-400 p-4 font-black text-slate-950 disabled:opacity-40">{busy ? "Preparing…" : "Start practice"}</button>
    </section> : session.result ? <section>
      <h1 className="text-3xl font-black">Practice complete: {session.result.score}/{session.result.total}</h1>
      <button disabled={busy} onClick={() => void reset()} className="mt-5 rounded-xl bg-cyan-400 px-5 py-3 font-bold text-slate-950">Practice another set</button>
      <div className="mt-6 space-y-4">{session.result.results.map((r, n) => {
        const original = session.questions.find(item => item.id === r.question_id);
        return <article key={r.question_id} className="glass rounded-2xl p-6"><h2 className="font-bold">Question {n + 1} · {r.correct ? "Correct" : r.selected_option ? "Incorrect" : "Skipped"}</h2><p className="mt-3 whitespace-pre-line">{original?.story_text}</p>
          <div className="mt-4 space-y-2">{Object.entries(original?.options || {}).map(([letter, value]) => <p key={letter} className={letter === r.correct_option ? "text-emerald-300" : "text-slate-400"}>{letter}. {value}{letter === r.selected_option ? " (your answer)" : ""}</p>)}</div>
          <p className="mt-4 text-slate-300">{r.solution}</p><button onClick={() => void bookmark(r.question_id)} className="mt-4 rounded-lg border border-white/15 px-4 py-2">{saved.has(r.question_id) ? "Saved" : "Save for revision"}</button></article>;
      })}</div>
    </section> : q ? <section className="grid gap-6 lg:grid-cols-[1fr_240px]">
      <div className="glass rounded-3xl p-6 md:p-8">
        <div className="flex justify-between gap-3 text-sm text-cyan-300"><span>{q.domain} · {q.difficulty}</span><span>{Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")} elapsed</span></div>
        <h1 className="mt-5 text-sm text-slate-400">Question {index + 1} of {session.questions.length}</h1><p className="mt-3 whitespace-pre-line text-xl leading-8">{q.story_text}</p>
        <div className="mt-6 grid gap-3">{Object.entries(q.options).map(([letter, text]) => <button disabled={busy} aria-pressed={answers[q.id] === letter} key={letter} onClick={() => choose({ ...answers, [q.id]: letter })} className={`rounded-xl border p-4 text-left ${answers[q.id] === letter ? "border-cyan-400 bg-cyan-400/10" : "border-white/10"}`}><b className="mr-3">{letter}</b>{text}</button>)}</div>
        <div className="mt-6 flex flex-wrap gap-3"><button disabled={busy || index === 0} onClick={() => choose(answers, index - 1)} className="rounded-xl border border-white/10 px-4 py-3 disabled:opacity-40">Previous</button>
          {index < session.questions.length - 1 && <button disabled={busy} onClick={() => choose(answers, index + 1)} className="rounded-xl border border-white/10 px-4 py-3">Next</button>}
          <button disabled={busy} onClick={() => void bookmark(q.id)} className="rounded-xl border border-white/10 px-4 py-3">{saved.has(q.id) ? "Saved" : "Save for revision"}</button>
          <button disabled={busy} onClick={() => void finish()} className="rounded-xl bg-cyan-400 px-4 py-3 font-bold text-slate-950">{busy ? "Submitting…" : "Finish set"}</button>
        </div>
        <p role="status" className="mt-5 text-sm text-slate-400">{draft.status}</p><button onClick={() => void draft.flush().catch(e => setError(e.message))} className="mt-2 text-sm text-cyan-300">Save now / retry</button>
      </div>
      <aside className="glass h-fit rounded-3xl p-5"><h2 className="font-bold">Question navigator</h2><div className="mt-4 grid grid-cols-5 gap-2">{session.questions.map((item, n) => <button disabled={busy} key={item.id} aria-label={`Go to question ${n + 1}`} onClick={() => choose(answers, n)} className={`rounded-lg p-2 ${n === index ? "bg-cyan-400 text-slate-950" : answers[item.id] ? "bg-emerald-400/20" : "bg-white/5"}`}>{n + 1}</button>)}</div><p className="mt-5 text-sm text-slate-400">{Object.keys(answers).length}/{session.questions.length} answered</p><p className="mt-3 text-sm text-slate-400">You can leave and resume after your progress shows Saved.</p><button disabled={busy} onClick={() => void reset(true)} className="mt-5 text-sm text-amber-200">Discard this set</button></aside>
    </section> : <p>Session data is unavailable. Reload to retry.</p>}
  </main>;
}
