import { useEffect, useRef, useState } from "react";

type AutosaveStatus = "idle" | "dirty" | "saving" | "saved" | "error";

function autosaveSignature(value: unknown) {
  return JSON.stringify(value);
}

export function useResumeAutosave<T>({
  value,
  enabled,
  delayMs = 1400,
  onSave,
}: {
  value: T | null;
  enabled: boolean;
  delayMs?: number;
  onSave: (value: T) => Promise<void>;
}) {
  const [status, setStatus] = useState<AutosaveStatus>("idle");
  const [error, setError] = useState("");
  const [lastSavedAt, setLastSavedAt] = useState<string>("");
  const didMount = useRef(false);
  const saveRef = useRef(onSave);
  const latestValueRef = useRef<T | null>(value);
  const latestSignatureRef = useRef(value ? autosaveSignature(value) : "");
  const lastSavedSignatureRef = useRef(value ? autosaveSignature(value) : "");
  const inFlightRef = useRef(false);
  const queuedRef = useRef(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    saveRef.current = onSave;
  }, [onSave]);

  useEffect(() => {
    latestValueRef.current = value;
    latestSignatureRef.current = value ? autosaveSignature(value) : "";
  }, [value]);

  useEffect(() => {
    if (!enabled || !value) {
      didMount.current = true;
      if (timerRef.current) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      return;
    }
    const signature = autosaveSignature(value);
    latestSignatureRef.current = signature;
    if (!didMount.current) {
      didMount.current = true;
      lastSavedSignatureRef.current = signature;
      return;
    }
    if (signature === lastSavedSignatureRef.current) {
      if (timerRef.current) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      return;
    }

    setStatus("dirty");
    setError("");
    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
    }
    timerRef.current = window.setTimeout(() => {
      void runSave();
    }, delayMs);

    return () => {
      if (timerRef.current) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [delayMs, enabled, value]);

  async function runSave() {
    const nextValue = latestValueRef.current;
    const savingSignature = latestSignatureRef.current;
    if (!nextValue) return;
    if (inFlightRef.current) {
      queuedRef.current = true;
      return;
    }
    inFlightRef.current = true;
    queuedRef.current = false;
    setStatus("saving");
    try {
      await saveRef.current(nextValue);
      lastSavedSignatureRef.current = savingSignature;
      setStatus("saved");
      setLastSavedAt(new Date().toISOString());
    } catch (saveError) {
      setStatus("error");
      setError(saveError instanceof Error ? saveError.message : "Autosave failed.");
    } finally {
      inFlightRef.current = false;
      if (queuedRef.current && enabled && latestValueRef.current) {
        queuedRef.current = false;
        void runSave();
      }
    }
  }

  const markSaved = () => {
    lastSavedSignatureRef.current = latestSignatureRef.current;
    setStatus("saved");
    setError("");
    setLastSavedAt(new Date().toISOString());
  };

  return { status, error, lastSavedAt, markSaved, setStatus, setError };
}
