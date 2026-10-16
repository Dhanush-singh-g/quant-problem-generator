"use client";
import { useCallback, useEffect, useRef, useState } from "react";

type Saver = (id: string, answers: Record<string, string>, index: number, revision: number) => Promise<{ revision: number }>;
export function useDraft(save: Saver) {
  const current = useRef<{ id: string; answers: Record<string, string>; index: number; revision: number } | null>(null);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dirty = useRef(false), conflict = useRef(false), mounted = useRef(true);
  const [status, setStatus] = useState("Saved");
  const setMessage = useCallback((message: string) => { if (mounted.current) setStatus(message); }, []);
  const restore = useCallback((id: string, answers: Record<string, string>, index: number, revision: number) => {
    current.current = { id, answers, index, revision }; dirty.current = false; conflict.current = false;
    setMessage("Saved");
  }, [setMessage]);
  const flush = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current);
    queue.current = queue.current.catch(() => undefined).then(async () => {
      const snapshot = current.current;
      if (!snapshot || !dirty.current) return;
      if (conflict.current) throw new Error("Another tab changed this session. Reload before continuing.");
      setMessage("Saving…");
      try {
        const response = await save(snapshot.id, snapshot.answers, snapshot.index, snapshot.revision);
        if (current.current?.id !== snapshot.id) return;
        current.current.revision = response.revision;
        if (current.current.answers === snapshot.answers && current.current.index === snapshot.index) dirty.current = false;
        setMessage(dirty.current ? "Unsaved changes" : "Saved");
      } catch (error) {
        if ((error as { status?: number }).status === 409) conflict.current = true;
        setMessage(error instanceof Error ? error.message : "Not saved. Retry before leaving.");
        throw error;
      }
    });
    await queue.current;
  }, [save, setMessage]);
  const change = useCallback((answers: Record<string, string>, index: number) => {
    if (!current.current || conflict.current) return;
    current.current = { ...current.current, answers, index }; dirty.current = true;
    setMessage("Unsaved changes");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => { void flush().catch(() => undefined); }, 250);
  }, [flush, setMessage]);
  const stop = useCallback(() => { if (timer.current) clearTimeout(timer.current); current.current = null; dirty.current = false; setMessage("Saved"); }, [setMessage]);
  useEffect(() => {
    mounted.current = true;
    const before = (event: BeforeUnloadEvent) => { if (dirty.current) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", before);
    return () => { mounted.current = false; window.removeEventListener("beforeunload", before); if (dirty.current) void flush().catch(() => undefined); };
  }, [flush]);
  return { restore, change, flush, stop, status };
}
