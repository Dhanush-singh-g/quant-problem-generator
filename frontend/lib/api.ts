export const API = process.env.NEXT_PUBLIC_API_URL || "/api";

export type User = { id: number; name: string; email: string; role: string };
export type Question = {
  id: string;
  domain: string;
  difficulty: string;
  story_text: string;
  options: Record<string, string>;
};

export type Assessment = {
  id: string;
  title: string;
  duration_minutes: number;
  easy_count: number;
  medium_count: number;
  hard_count: number;
  domains: string[];
  status: string;
  total_questions: number;
  expected_candidates: number;
  candidates_per_variant: number;
  variant_count: number;
  blueprint: { position: number; domain: string; difficulty: string }[];
};

export const authHeaders = () => ({ "Content-Type": "application/json" });

export class ApiError extends Error {
  constructor(message: string, public status: number, public detail?: unknown) { super(message); }
}

export function publishAuth(user: User | null) {
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("qf-auth", { detail: user }));
}

async function req(path: string, init: RequestInit = {}) {
  let response: Response;
  try {
    response = await fetch(`${API}${path}`, {
      ...init, headers: { ...authHeaders(), ...(init.headers || {}) },
      cache: "no-store", credentials: "include", signal: init.signal || AbortSignal.timeout(20000),
    });
  } catch {
    throw new ApiError("Cannot reach the server. Your saved progress is safe; check the connection and retry.", 0);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail;
    const message = typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map(x => x.msg).join("; ")
      : detail?.message || `Request failed (${response.status})`;
    if (response.status === 401 && !path.startsWith("/auth/login")) publishAuth(null);
    throw new ApiError(message, response.status, detail);
  }
  return response.status === 204 ? null : response.json();
}

export async function register(name: string, email: string, password: string) {
  const x = await req("/auth/register", {
    method: "POST",
    body: JSON.stringify({ name, email, password }),
  });
  publishAuth(x.user);
  return x;
}

export async function login(email: string, password: string) {
  const x = await req("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  publishAuth(x.user);
  return x;
}


export async function currentUser() {
  return req("/auth/me");
}

export async function logout() {
  try { await req("/auth/logout", { method: "POST" }); }
  catch (error) { if (!(error instanceof ApiError) || error.status !== 401) throw error; }
  publishAuth(null);
}

export async function googleLogin(credential: string) {
  const x = await req("/auth/google", { method: "POST", body: JSON.stringify({ credential }) });
  publishAuth(x.user);
  return x;
}

export type QuizResult = {
  score: number | null; total: number; review_available: boolean;
  results: { question_id: string; selected_option: string; correct_option: string; correct: boolean; solution: string }[];
};
export type PracticeSession = {
  session_id: string; status: string; domain: string; difficulty: string; mode: string;
  questions: Question[]; answers: Record<string, string>; current_index: number; revision: number;
  started_at: string; server_time: string; result: QuizResult | null;
};
export type PracticeInventory = Record<"unseen" | "revision", { domain: string; difficulty: string; count: number }[]>;
export async function getQuiz(count = 5, domain = "ALL", difficulty = "medium", mode = "unseen"): Promise<PracticeSession> {
  return req("/practice/sessions", { method: "POST", body: JSON.stringify({ count, domain, difficulty, mode }) });
}
export async function getPracticeInventory(): Promise<PracticeInventory> { return req("/practice/inventory"); }
export async function getActivePractice(): Promise<{ session: PracticeSession | null }> { return req("/practice/active"); }
export async function getPracticeSession(id: string): Promise<PracticeSession> { return req(`/practice/sessions/${id}`); }
export async function savePracticeDraft(id: string, answers: Record<string, string>, current_index: number, revision: number): Promise<{ revision: number }> {
  return req(`/practice/sessions/${id}/draft`, { method: "POST", body: JSON.stringify({ answers, current_index, revision }) });
}
export async function abandonPractice(id: string) { return req(`/practice/sessions/${id}/abandon`, { method: "POST" }); }

export async function submitQuiz(
  session_id: string,
  answers: { question_id: string; selected_option: string }[],
  duration_seconds = 0
) {
  return req("/quiz/submit", {
    method: "POST",
    body: JSON.stringify({ session_id, answers, duration_seconds }),
  });
}

export async function analytics() {
  return req("/analytics/me");
}

export async function adminMetrics() {
  return req("/admin/metrics");
}

export async function assessmentOptions() {
  return req("/assessment/options");
}

export async function createAssessment(body: {
  title: string;
  duration_minutes: number;
  easy_count: number;
  medium_count: number;
  hard_count: number;
  domains: string[];
  expected_candidates: number;
  candidates_per_variant: number;
}) {
  return req("/admin/assessments", { method: "POST", body: JSON.stringify(body) });
}


export async function previewAssessment(body: {
  title: string; duration_minutes: number; easy_count: number; medium_count: number; hard_count: number; domains: string[]; expected_candidates: number; candidates_per_variant: number;
}) {
  return req("/admin/assessments/preview", { method: "POST", body: JSON.stringify(body) });
}

export async function listAssessments() {
  return req("/admin/assessments");
}

export async function activateAssessment(id: string) {
  return req(`/admin/assessments/${id}/activate`, { method: "POST" });
}

export async function closeAssessment(id: string) {
  return req(`/admin/assessments/${id}/close`, { method: "POST" });
}

export async function getLeaderboard(id: string, offset = 0, limit = 100) {
  return req(`/admin/assessments/${id}/leaderboard?offset=${offset}&limit=${limit}`);
}

export async function getActiveAssessment() {
  return req("/assessments/active");
}

export async function startAssessment(id: string) {
  return req(`/assessments/${id}/start`, { method: "POST" });
}

export async function submitAssessment(
  assessmentId: string,
  session_id: string,
  answers: { question_id: string; selected_option: string }[]
) {
  return req(`/assessments/${assessmentId}/submit`, {
    method: "POST",
    body: JSON.stringify({ session_id, answers }),
  });
}

export async function getMyAssessmentInsights(id: string) {
  return req(`/assessments/${id}/insights/me`);
}

export async function getMyAssessmentReview(id: string) {
  return req(`/assessments/${id}/review/me`);
}


export async function savePracticeQuestion(questionId: string, saved = true) {
  return req(`/practice/questions/${questionId}/save`, {
    method: "POST", body: JSON.stringify({ saved }),
  });
}

export async function getSavedPracticeQuestions(limit = 20, offset = 0) {
  return req(`/practice/saved?limit=${limit}&offset=${offset}`);
}

export async function questionFactoryInventory() {
  return req("/admin/question-factory/inventory");
}

export type GenerationBatch = {
  id: string;
  domain: string;
  difficulty: string;
  requested: number;
  pending: number;
  queued: number;
  running: number;
  succeeded: number;
  rejected: number;
  failed: number;
  completed: number;
  status: string;
  reasons: Record<string, number>;
  created_at: string;
};

export async function getGenerationBatches(): Promise<{ batches: GenerationBatch[] }> {
  return req("/admin/question-factory/batches");
}

export async function getQuestionCalibration() {
  return req("/admin/question-factory/calibration");
}

export async function generateQuestions(domain: string, difficulty: string, count: number): Promise<{ batch: GenerationBatch; worker_notified: boolean }> {
  return req("/admin/question-factory/generate", {
    method: "POST",
    body: JSON.stringify({ domain, difficulty, count }),
  });
}

export type AssessmentSession = {
  session_id: string; assessment: Assessment; questions: Question[];
  started_at: string; deadline_at: string; duration_seconds: number;
  answers: Record<string, string>; current_index: number; revision: number;
};
export async function saveAssessmentDraft(id: string, answers: Record<string, string>, current_index: number, revision: number): Promise<{ revision: number }> {
  return req(`/assessment-sessions/${id}/draft`, { method: "POST", body: JSON.stringify({ answers, current_index, revision }) });
}
