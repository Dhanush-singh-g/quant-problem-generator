"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { RequireAuth } from "@/components/AuthProvider";
import { useDraft } from "@/hooks/useDraft";
import { getActiveAssessment, getMyAssessmentReview, saveAssessmentDraft, startAssessment, submitAssessment,
  type Assessment, type AssessmentSession, type QuizResult } from "@/lib/api";
export default function Page() { return <RequireAuth><Exams/></RequireAuth>; }
function Exams() {
  const [active, setActive] = useState<{ assessment: Assessment | null; candidate_status?: string; review_available?: boolean } | null>(null);
  const [session, setSession] = useState<AssessmentSession | null>(null), [result, setResult] = useState<QuizResult | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({}), [index, setIndex] = useState(0), [seconds, setSeconds] = useState(0);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const submitting = useRef(false), offset = useRef(0), draft = useDraft(saveAssessmentDraft);
  useEffect(() => { getActiveAssessment().then(setActive).catch(e => setError(e.message)); }, []);
  async function start() {
    if (!active?.assessment) return;
    setBusy(true); setError("");
    try {
      const value: AssessmentSession = await startAssessment(active.assessment.id);
      // Use the server's remaining duration; browser clock changes cannot grant time.
      offset.current = Date.now() + value.duration_seconds * 1000;
      setSession(value); setAnswers(value.answers); setIndex(value.current_index);
      draft.restore(value.session_id, value.answers, value.current_index, value.revision);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start assessment"); }
    finally { setBusy(false); }
  }
  const finish = useCallback(async (timedOut = false) => {
    if (!session || submitting.current) return;
    submitting.current = true; setBusy(true); setError("");
    try {
      if (!timedOut) await draft.flush();
      const response = await submitAssessment(session.assessment.id, session.session_id,
        Object.entries(answers).map(([question_id, selected_option]) => ({ question_id, selected_option })));
      draft.stop(); setResult(response);
    } catch (e) { setError(e instanceof Error ? e.message : "Submission failed. Retry; saved answers are retained."); }
    finally { submitting.current = false; setBusy(false); }
  }, [session, answers, draft.flush, draft.stop]);
  useEffect(() => {
    if (!session || result) return;
    const tick = () => {
      const remaining = Math.max(0, Math.ceil((offset.current - Date.now()) / 1000));
      setSeconds(remaining);
    };
    tick(); const timer = setInterval(tick, 500); return () => clearInterval(timer);
  }, [session, result]);
  const automatic = useRef(false);
  useEffect(() => { if (session && !result && seconds === 0 && !automatic.current) {
    // On initial render, wait until the known deadline is actually reached.
    if (Date.now() >= offset.current) { automatic.current = true; void finish(true); }
  } }, [seconds, session, result, finish]);
  function change(next: Record<string, string>, position = index) { setAnswers(next); setIndex(position); draft.change(next, position); }
  async function review() {
    if (!active?.assessment) return;
    try { setResult(await getMyAssessmentReview(active.assessment.id)); }
    catch (e) { setError(e instanceof Error ? e.message : "Review is not available yet"); }
  }
  const q = session?.questions[index];
  return <main className="mx-auto max-w-5xl px-4 py-10"><h1 className="text-3xl font-black">Assessments</h1>
    {error && <p role="alert" className="mt-5 text-red-300">{error}</p>}
    {result ? <section className="glass mt-6 rounded-3xl p-6"><h2 className="text-2xl font-bold">Assessment submitted</h2>{!result.review_available ? <p className="mt-3">Your answers are recorded. Review will unlock after the assessment closes and active sessions finish.</p> : <><p className="mt-3">Score: {result.score}/{result.total}</p><div className="mt-5 space-y-4">{result.results.map((r, n) => <article key={r.question_id} className="rounded-xl border border-white/10 p-4"><h3 className="font-bold">Question {n + 1} · {r.correct ? "Correct" : "Incorrect / skipped"}</h3><p className="mt-2">Your option: {r.selected_option || "Skipped"} · Correct: {r.correct_option}</p><p className="mt-2 text-slate-400">{r.solution}</p></article>)}</div></>}</section> : session && q ? <section className="glass mt-6 rounded-3xl p-6">
      <div className="flex justify-between gap-4"><h2 className="font-bold">{session.assessment.title}</h2><p role="timer">{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")} remaining</p></div>
      <p className="mt-4 text-sm text-slate-400">Question {index + 1} of {session.questions.length}</p><p className="mt-3 whitespace-pre-line text-xl leading-8">{q.story_text}</p>
      <div className="mt-6 grid gap-3">{Object.entries(q.options).map(([letter, text]) => <button disabled={busy || seconds === 0} key={letter} aria-pressed={answers[q.id] === letter} onClick={() => change({ ...answers, [q.id]: letter })} className={`rounded-xl border p-4 text-left ${answers[q.id] === letter ? "border-cyan-400 bg-cyan-400/10" : "border-white/10"}`}>{letter}. {text}</button>)}</div>
      <div className="mt-6 flex flex-wrap gap-3">{session.questions.map((item, n) => <button disabled={busy} key={item.id} aria-label={`Go to question ${n + 1}`} onClick={() => change(answers, n)} className={`rounded-lg px-3 py-2 ${n === index ? "bg-cyan-400 text-slate-950" : "bg-white/5"}`}>{n + 1}</button>)}</div>
      <p role="status" className="mt-5 text-sm text-slate-400">{draft.status}</p><button disabled={busy} onClick={() => void finish(seconds === 0)} className="mt-5 rounded-xl bg-cyan-400 px-5 py-3 font-bold text-slate-950">{busy ? "Submitting…" : seconds === 0 ? "Submit saved answers" : "Submit assessment"}</button>
    </section> : active === null ? <p className="mt-6">Loading assessment…</p> : active.assessment ? <section className="glass mt-6 rounded-3xl p-6"><h2 className="text-2xl font-bold">{active.assessment.title}</h2><p className="mt-3">{active.assessment.total_questions} questions · {active.assessment.duration_minutes} minutes</p>
      {active.candidate_status === "submitted" ? <><p className="mt-3">You have submitted this assessment.</p><button disabled={!active.review_available} onClick={() => void review()} className="mt-5 rounded-xl border border-white/15 px-5 py-3 disabled:opacity-40">View review</button></> : <button disabled={busy} onClick={() => void start()} className="mt-5 rounded-xl bg-cyan-400 px-5 py-3 font-bold text-slate-950">{busy ? "Preparing…" : active.candidate_status === "not_started" ? "Start assessment" : "Resume assessment"}</button>}
    </section> : <p className="glass mt-6 rounded-2xl p-6">No assessment is active.</p>}
  </main>;
}
