"use client";
import { FormEvent, useEffect, useState } from "react";
import { RequireAuth } from "@/components/AuthProvider";
import { activateAssessment, assessmentOptions, closeAssessment, createAssessment, getLeaderboard, listAssessments, previewAssessment, type Assessment } from "@/lib/api";
export default function Page() { return <RequireAuth admin><Manage/></RequireAuth>; }
function Manage() {
  const [rows, setRows] = useState<Assessment[]>([]), [domains, setDomains] = useState<string[]>([]), [selected, setSelected] = useState<string[]>([]);
  const [title, setTitle] = useState("Aptitude assessment"), [duration, setDuration] = useState(15);
  const [easy, setEasy] = useState(5), [medium, setMedium] = useState(5), [hard, setHard] = useState(0);
  const [expected, setExpected] = useState(100), [perVariant, setPerVariant] = useState(25);
  const [preview, setPreview] = useState<any>(null), [leaderboard, setLeaderboard] = useState<any>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const body = () => ({ title, duration_minutes: duration, easy_count: easy, medium_count: medium, hard_count: hard, domains: selected, expected_candidates: expected, candidates_per_variant: perVariant });
  async function refresh() { const [assessments, options] = await Promise.all([listAssessments(), assessmentOptions()]); setRows(assessments.assessments); setDomains(options.domains); }
  useEffect(() => { void refresh().catch(e => setError(e.message)); }, []);
  async function action(run: () => Promise<unknown>) { setBusy(true); setError(""); try { await run(); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : "Assessment action failed"); } finally { setBusy(false); } }
  async function create(e: FormEvent) { e.preventDefault(); await action(async () => { await createAssessment(body()); setPreview(null); }); }
  return <main className="mx-auto max-w-6xl px-4 py-10"><h1 className="text-3xl font-black">Manage assessments</h1>{error && <p role="alert" className="mt-5 text-red-300">{error}</p>}
    <form onSubmit={create} className="glass mt-6 rounded-3xl p-6"><h2 className="text-xl font-bold">Create a draft</h2><div className="mt-5 grid gap-4 sm:grid-cols-3">
      <label>Title<input required minLength={3} maxLength={160} value={title} onChange={e => { setTitle(e.target.value); setPreview(null); }} className="mt-2 w-full rounded-lg bg-slate-950 p-3"/></label>
      {[["Duration (minutes)", duration, setDuration, 1, 240], ["Easy questions", easy, setEasy, 0, 100], ["Medium questions", medium, setMedium, 0, 100], ["Hard questions", hard, setHard, 0, 100], ["Expected candidates", expected, setExpected, 1, 100000], ["Candidates per variant", perVariant, setPerVariant, 5, 1000]].map(([name, value, setter, min, max]: any) => <label key={name}>{name}<input type="number" required min={min} max={max} value={Number.isNaN(value) ? "" : value} onChange={e => { setter(e.target.valueAsNumber); setPreview(null); }} className="mt-2 w-full rounded-lg bg-slate-950 p-3"/></label>)}
    </div><fieldset className="mt-5"><legend>Topics</legend><div className="mt-3 flex flex-wrap gap-3">{domains.map(d => <label key={d} className="rounded-lg border border-white/10 p-3"><input type="checkbox" checked={selected.includes(d)} onChange={e => { setSelected(e.target.checked ? [...selected, d] : selected.filter(x => x !== d)); setPreview(null); }} className="mr-2"/>{d}</label>)}</div></fieldset>
      <div className="mt-5 flex flex-wrap gap-3"><button type="button" disabled={busy || !selected.length} onClick={() => void action(async () => setPreview(await previewAssessment(body())))} className="rounded-xl border border-white/15 px-5 py-3 disabled:opacity-40">Preview distribution</button><button disabled={busy || !selected.length} className="rounded-xl bg-cyan-400 px-5 py-3 font-bold text-slate-950 disabled:opacity-40">Create draft</button></div>
      {preview && <div className="mt-5"><p>{preview.total_questions} questions · {preview.variant_count} reusable variants</p>{Object.entries(preview.by_domain).map(([topic, counts]: any) => <p key={topic} className="mt-2 text-sm text-slate-400">{topic}: {counts.easy} easy, {counts.medium} medium, {counts.hard} hard</p>)}</div>}
    </form>
    <section className="mt-8 space-y-4"><h2 className="text-2xl font-bold">Assessments</h2>{rows.map(row => <article key={row.id} className="glass rounded-2xl p-5"><h3 className="text-lg font-bold">{row.title}</h3><p className="mt-2 text-slate-400">{row.status} · {row.total_questions} questions · {row.variant_count} variants</p><div className="mt-4 flex flex-wrap gap-3">
      {row.status === "draft" && <button disabled={busy} onClick={() => void action(() => activateAssessment(row.id))} className="rounded-lg border border-cyan-400/30 px-4 py-2">Activate</button>}
      {row.status === "active" && <button disabled={busy} onClick={() => void action(() => closeAssessment(row.id))} className="rounded-lg border border-white/15 px-4 py-2">Close to new candidates</button>}
      <button disabled={busy} onClick={() => void action(async () => setLeaderboard(await getLeaderboard(row.id)))} className="rounded-lg border border-white/15 px-4 py-2">Leaderboard</button></div></article>)}</section>
    {leaderboard && <section className="glass mt-8 rounded-2xl p-5"><h2 className="text-xl font-bold">Leaderboard</h2><p className="mt-2 text-slate-400">First {leaderboard.leaderboard?.length || 0} of {leaderboard.pagination?.total ?? 0} submitted attempts.</p>{leaderboard.leaderboard?.map((r: any) => <p key={r.user_id} className="mt-3">#{r.rank} {r.name}: {r.score}/{r.total} · {r.duration_seconds}s</p>)}</section>}
  </main>;
}
