const layers=[
  "Next.js / TypeScript client",
  "FastAPI stateless candidate API",
  "PostgreSQL assessment variants + durable sessions",
  "Redis distributed rate limits + shared AI cache + Celery broker",
  "Celery background inventory generation",
  "Deterministic formula/fact truth layer + independent verification",
  "Gemini neutral context enhancement outside the candidate hot path",
];
export default function System(){return <main className="mx-auto max-w-4xl px-6 py-14">
  <p className="text-sm font-bold uppercase tracking-[.2em] text-cyan-400">Production-oriented architecture</p>
  <h1 className="mt-3 text-5xl font-black">AI is not the correctness layer.</h1>
  <p className="mt-5 max-w-3xl leading-7 text-slate-400">Formal assessments are served from reusable, pre-materialized variants. Candidate assignment uses HMAC, while question and option order are reconstructed from a stored presentation seed. Candidate start performs no Gemini call or question generation. Redis coordinates distributed limits and background work; PostgreSQL remains the durable source of truth.</p>
  <div className="mt-10 space-y-3">{layers.map((x,i)=><div className="glass rounded-2xl p-5" key={x}><span className="mr-4 text-cyan-400">{String(i+1).padStart(2,"0")}</span><b>{x}</b></div>)}</div>
</main>}
