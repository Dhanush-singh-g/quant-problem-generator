"use client";
import {useEffect,useMemo,useState} from "react";
import Link from "next/link";
import {Activity,BarChart3,CheckCircle2,Clock3,Target,Trophy,XCircle} from "lucide-react";
import {analytics} from "@/lib/api";
import {RequireAuth} from "@/components/AuthProvider";

const label=(s:string)=>s==="strong"?"Strong":s==="needs_practice"?"Needs practice":s==="developing"?"Developing":"Building data";
const badge=(s:string)=>s==="strong"?"border-emerald-400/20 bg-emerald-400/10 text-emerald-300":s==="needs_practice"?"border-amber-400/20 bg-amber-400/10 text-amber-300":"border-white/10 bg-white/[.04] text-slate-400";

export default function Page(){return <RequireAuth><Analytics/></RequireAuth>}
function Analytics(){
  const[d,setD]=useState<any>(null),[err,setErr]=useState("");
  useEffect(()=>{analytics().then(setD).catch(e=>setErr(e.message))},[]);
  const strongest=useMemo(()=>{if(!d?.by_domain)return null;const rows=Object.entries(d.by_domain) as [string,any][];return rows.filter(([,v])=>v.total>=5).sort((a,b)=>b[1].accuracy-a[1].accuracy)[0]||null},[d]);
  if(err)return <main className="mx-auto max-w-5xl px-6 py-20"><div className="glass rounded-2xl p-6">{err}. <Link className="text-cyan-300" href="/login">Sign in</Link></div></main>;
  if(!d)return <main className="mx-auto max-w-5xl px-6 py-20 text-slate-400">Loading performance profile…</main>;
  return <main className="mx-auto max-w-7xl px-4 py-10 md:px-6 md:py-14">
    <section className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
      <div><p className="text-xs font-bold uppercase tracking-[.2em] text-cyan-300">Performance profile</p><h1 className="mt-2 text-4xl font-black tracking-tight md:text-5xl">{d.profile?.name||"Your"} practice stats</h1><p className="mt-3 max-w-2xl text-slate-400">A factual view of your solved questions, accuracy, speed and topic-level performance. You still choose what to practise next.</p></div>
      <Link href="/quiz" className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-400 px-5 py-3 font-black text-slate-950"><Target size={18}/>Start another set</Link>
    </section>

    <section className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {[ [Activity,"Questions completed",d.questions_completed],[CheckCircle2,"Correct",d.correct_answers??0],[BarChart3,"Accuracy",`${d.accuracy}%`],[Clock3,"Avg / question",`${d.avg_seconds_per_question}s`] ].map(([I,a,b]:any)=><div key={a} className="glass metric-glow rounded-2xl p-5"><div className="flex items-center justify-between"><p className="text-sm text-slate-400">{a}</p><I size={18} className="text-cyan-300"/></div><p className="mt-3 text-3xl font-black">{b}</p></div>)}
    </section>

    <section className="mt-8 grid gap-6 lg:grid-cols-[1.3fr_.7fr]">
      <div className="glass rounded-3xl p-6 md:p-7"><div className="flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-[.16em] text-slate-500">Topic analysis</p><h2 className="mt-1 text-2xl font-black">Strength by topic</h2></div>{strongest&&<div className="hidden items-center gap-2 rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-3 py-2 text-sm text-emerald-300 sm:flex"><Trophy size={16}/>{strongest[0]}</div>}</div>
        <div className="mt-6 space-y-4">{Object.keys(d.by_domain||{}).length===0?<p className="text-sm text-slate-500">Complete a practice set to build your topic profile.</p>:Object.entries(d.by_domain).sort((a:any,b:any)=>b[1].total-a[1].total).map(([k,v]:any)=><div key={k} className="rounded-2xl border border-white/[.07] bg-white/[.02] p-4"><div className="flex items-center justify-between gap-4"><div><p className="font-bold">{k}</p><p className="mt-1 text-xs text-slate-500">{v.correct}/{v.total} correct</p></div><div className="text-right"><p className="text-xl font-black">{v.accuracy}%</p><span className={`mt-1 inline-flex rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-wider ${badge(v.strength)}`}>{label(v.strength)}</span></div></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-white/[.06]"><div className="h-full rounded-full bg-cyan-400" style={{width:`${Math.min(100,Math.max(0,v.accuracy))}%`}}/></div></div>)}</div>
      </div>
      <div className="space-y-6">
        <div className="glass rounded-3xl p-6"><p className="text-xs font-bold uppercase tracking-[.16em] text-slate-500">Accuracy split</p><div className="mt-5 grid grid-cols-2 gap-3"><div className="rounded-2xl bg-emerald-400/[.08] p-4"><CheckCircle2 className="text-emerald-300" size={18}/><p className="mt-3 text-2xl font-black">{d.correct_answers??0}</p><p className="text-xs text-slate-500">Correct</p></div><div className="rounded-2xl bg-rose-400/[.07] p-4"><XCircle className="text-rose-300" size={18}/><p className="mt-3 text-2xl font-black">{(d.incorrect_answers??0)+(d.skipped_answers??0)}</p><p className="text-xs text-slate-500">Incorrect / skipped</p></div></div></div>
        <div className="glass rounded-3xl p-6"><p className="text-xs font-bold uppercase tracking-[.16em] text-slate-500">Difficulty profile</p><div className="mt-4 space-y-3">{Object.entries(d.by_difficulty||{}).map(([k,v]:any)=><div key={k} className="flex items-center justify-between rounded-xl border border-white/[.06] px-4 py-3"><div><p className="font-bold capitalize">{k}</p><p className="text-xs text-slate-500">{v.total} questions</p></div><p className="text-xl font-black text-cyan-300">{v.accuracy}%</p></div>)}</div></div>
      </div>
    </section>

    <section className="mt-8 glass rounded-3xl p-6 md:p-7"><p className="text-xs font-bold uppercase tracking-[.16em] text-slate-500">Recent sessions</p><div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-4">{(d.recent||[]).map((r:any)=><div key={r.id} className="rounded-xl border border-white/[.07] bg-white/[.02] p-4"><p className="text-2xl font-black">{r.score}/{r.total}</p><p className="mt-1 text-xs text-slate-500">{new Date(r.created_at).toLocaleString()}</p></div>)}{!(d.recent||[]).length&&<p className="text-sm text-slate-500">No completed sessions yet.</p>}</div></section>
  </main>
}
