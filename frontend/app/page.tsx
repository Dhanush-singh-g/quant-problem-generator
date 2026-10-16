import Link from "next/link";
import {ArrowRight,BarChart3,Bookmark,CheckCircle2,Clock3,ShieldCheck,Target,Zap} from "lucide-react";

const topics=["Time, Speed & Distance","Work & Time","Pipes & Cisterns","Profit, Loss & Discount","Mixtures & Ratio","Age-Based Problems"];
const features=[
  [ShieldCheck,"Verified questions","Reviewed mathematical models and an independent solver validate newly generated questions."],
  [Target,"Focused sets","Choose the topic, difficulty and set size yourself. QuantForge does not force an adaptive path."],
  [BarChart3,"Performance profile","Track accuracy, speed and topic-level strengths from your own practice history."],
  [Bookmark,"Revision workflow","Save questions that beat you and build a personal revision list instead of losing them."],
];

export default function Home(){return <main className="mx-auto max-w-7xl px-4 pb-24 pt-10 md:px-6 md:pt-16">
  <section className="grid items-center gap-10 lg:grid-cols-[1.12fr_.88fr]">
    <div>
      <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/[.07] px-4 py-2 text-xs font-bold uppercase tracking-[.2em] text-cyan-300"><Zap size={14}/>Verified AI aptitude practice</div>
      <h1 className="mt-6 max-w-4xl text-5xl font-black leading-[1.02] tracking-[-.045em] md:text-7xl">Train for aptitude rounds with <span className="text-cyan-300">fresh, validated questions.</span></h1>
      <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-400">Build short topic-focused sets, solve unseen questions, review mistakes and watch your accuracy improve. The AI question factory runs behind the scenes; practice stays fast and database-backed.</p>
      <div className="mt-8 flex flex-wrap gap-3"><Link href="/quiz" className="inline-flex items-center gap-2 rounded-xl bg-cyan-400 px-6 py-3 font-black text-slate-950">Start practice <ArrowRight size={18}/></Link><Link href="/analytics" className="rounded-xl border border-white/10 bg-white/[.03] px-6 py-3 font-bold">View my profile</Link></div>
      <div className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-500"><span className="flex items-center gap-2"><CheckCircle2 size={15} className="text-emerald-300"/>No-repeat normal practice</span><span className="flex items-center gap-2"><Clock3 size={15} className="text-cyan-300"/>5 / 10 / 15 / 20-question sets</span></div>
    </div>
    <div className="glass rounded-[2rem] p-5 md:p-7">
      <div className="flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-[.18em] text-slate-500">Quick practice</p><h2 className="mt-1 text-2xl font-black">Choose a topic</h2></div><Target className="text-cyan-300"/></div>
      <div className="mt-5 grid gap-2">{topics.map((t,i)=><Link href={`/quiz?domain=${encodeURIComponent(t)}`} key={t} className="group flex items-center justify-between rounded-xl border border-white/[.07] bg-white/[.025] px-4 py-3 hover:border-cyan-400/30 hover:bg-cyan-400/[.05]"><span className="font-semibold text-slate-200">{t}</span><span className="text-xs text-slate-500 group-hover:text-cyan-300">{i<2?"Core":"Practice"} →</span></Link>)}</div>
    </div>
  </section>
  <section className="mt-20"><p className="text-xs font-bold uppercase tracking-[.2em] text-cyan-300">Built for deliberate practice</p><div className="mt-5 grid gap-4 md:grid-cols-2 lg:grid-cols-4">{features.map(([I,t,d]:any)=><div key={t} className="glass rounded-2xl p-6"><I className="text-cyan-300"/><h3 className="mt-5 font-black">{t}</h3><p className="mt-2 text-sm leading-6 text-slate-400">{d}</p></div>)}</div></section>
</main>}
