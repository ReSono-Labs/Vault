import { useEffect, useRef, useState } from "react";
import { conversationApi as api, type Preparation } from "./api";

/** Observer of the server's one VoiceMem loop; never a client classifier. */
export function useLivePreparation(active: boolean, draft: string, conversation: string | null,
  ensureConversation: () => Promise<string>) {
  const [value, setValue] = useState<Preparation | null>(null);
  const [composing, setComposing] = useState(false);
  const [preference, setPreference] = useState<{ enabled: boolean; epoch: number } | null>(null);
  const [preferenceBusy, setPreferenceBusy] = useState(false);
  const [preferenceError, setPreferenceError] = useState<string | null>(null);
  const epoch = useRef(0);
  const revision = useRef(0);
  const utterance = useRef(crypto.randomUUID());
  const owner = useRef<{ id: string; utterance: string } | null>(null);
  const blocked = useRef<string | null>(null);
  const ensure = useRef(ensureConversation);
  ensure.current = ensureConversation;
  const currentDraft = useRef(draft);
  const burstStarted = useRef<number | null>(null);
  currentDraft.current = draft;
  useEffect(() => {
    if (!active || typeof api.livePreference !== "function") return;
    const abort = new AbortController();
    void api.livePreference(abort.signal).then(p => { if (!abort.signal.aborted) setPreference(p); })
      .catch(() => { if (!abort.signal.aborted) setPreferenceError("Live Memory setting unavailable"); });
    return () => abort.abort();
  }, [active]);
  async function toggle() {
    if (!preference || preferenceBusy) return;
    clear(); setPreferenceBusy(true); setPreferenceError(null);
    try {
      const next = await api.setLivePreference(!preference.enabled, preference.epoch);
      blocked.current = null; setPreference(next);
    } catch { setPreferenceError("Could not change Live Memory. Reload Chat to check its current setting."); }
    finally { setPreferenceBusy(false); }
  }

  function clear(discard = true) {
    epoch.current += 1;
    blocked.current = currentDraft.current;
    setValue(null);
    const old = owner.current;
    owner.current = null;
    utterance.current = crypto.randomUUID();
    if (old && discard) void api.discardPreparation(old.id, old.utterance).catch(() => {});
  }
  useEffect(() => {
    const generation = ++epoch.current;
    if (!draft.trim()) setValue(null);
    if (!active || preference?.enabled === false || blocked.current === draft || typeof api.prepare !== "function") return;
    blocked.current = null;
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const current = () => !abort.signal.aborted && epoch.current === generation;
    const rev = ++revision.current, utteranceId = utterance.current;
    async function update() {
      try {
        // Empty/short edits still replace a previously accepted draft; never leave
        // its backend preparation current merely because the new text is short.
        if (!owner.current && (draft.trim().length < 12 || draft.trim().split(/\s+/).length < 3)) return;
        const id = conversation ?? owner.current?.id ?? await ensure.current();
        if (!current()) return;
        owner.current = { id, utterance: utteranceId };
        await api.prepare(id, { utteranceId, revision: rev, text: draft, composing });
        burstStarted.current = null;
        if (!current() || !draft.trim() || composing) return;
        setValue(previous => ({ revision: rev, state: "searching", memories: previous?.memories ?? [],
          tools: previous?.tools ?? [], toolState: previous?.toolState }));
        async function poll() {
          try {
            const next = await api.preparation(id, utteranceId, rev, abort.signal);
            if (!current() || next.revision !== rev || next.state === "stale") return;
            setValue(next);
            if (next.state === "searching") timer = setTimeout(() => void poll(), 350);
          } catch { if (current()) setValue({ revision: rev, state: "unavailable", memories: [], tools: [] }); }
        }
        await poll();
      } catch { if (current()) setValue({ revision: rev, state: "unavailable", memories: [], tools: [] }); }
    }
    burstStarted.current ??= performance.now();
    const delay = !draft.trim() || composing ? 0 : Math.max(0, Math.min(150, 800-(performance.now()-burstStarted.current)));
    timer = setTimeout(() => void update(), delay); // Input debounce; server owns the shared work loop.
    return () => { abort.abort(); clearTimeout(timer); };
  }, [active, draft, conversation, composing, preference?.enabled]);
  useEffect(() => () => {
    epoch.current += 1;
    const old = owner.current;
    if (old && typeof api.discardPreparation === "function") void api.discardPreparation(old.id, old.utterance).catch(() => {});
    owner.current = null;
    utterance.current = crypto.randomUUID();
  }, [conversation, active]);
  // Render-time equality avoids even one painted frame of a prior draft's readiness.
  return { value: active && preference?.enabled !== false && blocked.current !== draft && draft.trim() ? value : null,
    clear, setComposing, preference, preferenceBusy, preferenceError, toggle };
}
