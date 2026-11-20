import { useEffect, useState } from "react";
import { localApi } from "@/browser-voice/localApi";

type AccessLevel = "read" | "write";
type RowDraft = { access: AccessLevel; voice: boolean; background: boolean };

function emptyRow(): RowDraft {
  return { access: "write", voice: false, background: false };
}

function draftsFromTools(tools: string[], grants: Awaited<ReturnType<typeof localApi.extensionGrants>>["items"]) {
  const next: Record<string, RowDraft> = {};
  for (const name of tools) {
    const matching = grants.filter((item) => item.capabilityName === name);
    const voice = matching.some((item) => item.agentKind === "voice" && item.enabled);
    const background = matching.some((item) => item.agentKind === "background" && item.enabled);
    const write = matching.some((item) => item.enabled && item.effectClass !== "read");
    next[name] = { access: write ? "write" : matching.some((item) => item.enabled) ? "read" : "write", voice, background };
  }
  return next;
}

export function ToolGrantTable({
  extensionId,
  tools,
  userId,
  working,
  onWorking,
  onMessage,
  onError,
}: {
  extensionId: string;
  tools: string[];
  userId: string;
  working: boolean;
  onWorking: (value: boolean) => void;
  onMessage: (value: string) => void;
  onError: (value: string | null) => void;
}) {
  const [drafts, setDrafts] = useState<Record<string, RowDraft>>({});
  const toolKey = tools.join("\0");

  useEffect(() => {
    const names = toolKey ? toolKey.split("\0") : [];
    if (!names.length) {
      setDrafts({});
      return;
    }
    let cancelled = false;
    void localApi.extensionGrants(extensionId).then((result) => {
      if (!cancelled) setDrafts(draftsFromTools(names, result.items));
    }).catch((caught) => {
      if (!cancelled) {
        setDrafts(Object.fromEntries(names.map((name) => [name, emptyRow()])));
        onError(caught instanceof Error ? caught.message : "Saved tool access could not be loaded.");
      }
    });
    return () => { cancelled = true; };
  }, [extensionId, toolKey]);

  function patch(name: string, patchValue: Partial<RowDraft>) {
    setDrafts((current) => ({ ...current, [name]: { ...(current[name] ?? emptyRow()), ...patchValue } }));
  }

  async function save() {
    onWorking(true);
    onError(null);
    try {
      for (const name of tools) {
        const row = drafts[name] ?? emptyRow();
        for (const agentKind of ["voice", "background"] as const) {
          await localApi.grantPluginTool(extensionId, {
            targetUserId: userId,
            agentKind,
            capabilityName: name,
            enabled: row[agentKind],
            effectClass: row.access,
          });
        }
      }
      onMessage("Tool access saved.");
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Tool access could not be saved.");
    } finally {
      onWorking(false);
    }
  }

  if (!tools.length) return null;
  return (
    <>
      <div className="browser-voice-tool-grant-list">
        <div className="browser-voice-tool-grant-head">
          <span>Tool</span>
          <span>Access</span>
          <span>Voice</span>
          <span>Background</span>
        </div>
        {tools.map((name) => {
          const row = drafts[name] ?? emptyRow();
          return (
            <div className="browser-voice-tool-grant-row" key={name}>
              <strong>{name}</strong>
              <select
                aria-label={`${name} access`}
                onChange={(event) => patch(name, { access: event.target.value as AccessLevel })}
                value={row.access}
              >
                <option value="read">Read</option>
                <option value="write">Read &amp; write</option>
              </select>
              <button
                aria-label={`${name} for Voice`}
                aria-pressed={row.voice}
                className="browser-voice-agent-switch"
                disabled={working || !userId}
                onClick={() => patch(name, { voice: !row.voice })}
                role="switch"
                type="button"
              >
                <span />
              </button>
              <button
                aria-label={`${name} for Background`}
                aria-pressed={row.background}
                className="browser-voice-agent-switch"
                disabled={working || !userId}
                onClick={() => patch(name, { background: !row.background })}
                role="switch"
                type="button"
              >
                <span />
              </button>
            </div>
          );
        })}
      </div>
      <button className="browser-voice-submit" disabled={working || !userId} onClick={() => void save()} type="button">
        {working ? "Saving…" : "Save tool access"}
      </button>
    </>
  );
}
