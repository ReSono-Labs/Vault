import { useEffect, useState } from "react";
import { ExtensionSchemaForm, initialExtensionSettings, type ExtensionSchemaField } from "@/browser-voice/ExtensionSchemaForm";
import { localApi, type LocalExtension } from "@/browser-voice/localApi";

type RuntimeStatus = {
  state?: string;
  port?: number | null;
  endpoint?: string | null;
  lastError?: string | null;
};

export function McpPackageSetup({
  item,
  onBack,
  onChanged,
  onRemove,
}: {
  item: LocalExtension;
  onBack: () => void;
  onChanged: () => Promise<void>;
  onRemove?: () => Promise<void>;
}) {
  const schema = item.configuration.configurationSchema as { fields?: ExtensionSchemaField[] } | undefined;
  const saved = (item.configuration.settings as Record<string, unknown> | undefined) ?? {};
  const runtimeStatus = item.configuration.runtimeStatus as RuntimeStatus | undefined;
  const migrationStatus = item.configuration.migrationStatus as Record<string, string> | undefined;
  const hosted = item.configuration.packageType === "hosted";
  const [values, setValues] = useState(() => initialExtensionSettings(schema, saved));
  const [tools, setTools] = useState<string[]>([]);
  const [userId, setUserId] = useState("");
  const [effect, setEffect] = useState<Record<string, "read" | "write" | "delete">>({});
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void localApi.me().then((me) => setUserId(me.user.userId)).catch((caught) => {
      setError(caught instanceof Error ? caught.message : "Account details could not be loaded.");
    });
  }, []);

  const set = (key: string, value: unknown) => setValues((current) => ({ ...current, [key]: value }));

  async function saveSettings() {
    setWorking(true);
    setError(null);
    try {
      await localApi.saveExtensionSettings(item.extensionId, values);
      setMessage("MCP settings saved.");
      await onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Settings could not be saved.");
    } finally {
      setWorking(false);
    }
  }

  async function toggleEnabled() {
    setWorking(true);
    setError(null);
    try {
      await localApi.extensionState(
        item.extensionId,
        item.state === "enabled" ? "disabled" : "enabled",
      );
      setMessage(item.state === "enabled" ? "MCP stopped." : "MCP started.");
      await onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "MCP could not be updated.");
    } finally {
      setWorking(false);
    }
  }

  async function discoverTools() {
    setWorking(true);
    setError(null);
    try {
      const result = await localApi.discoverPluginTools(item.extensionId);
      setTools(result.items);
      setMessage(result.items.length ? "Tools are ready for you to choose." : "This MCP did not report any tools.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Vault could not reach this MCP.");
    } finally {
      setWorking(false);
    }
  }

  async function grant(name: string, agentKind: "voice" | "background") {
    setWorking(true);
    setError(null);
    try {
      await localApi.grantPluginTool(item.extensionId, {
        targetUserId: userId,
        agentKind,
        capabilityName: name,
        enabled: true,
        effectClass: effect[name] ?? "read",
      });
      setMessage(`${name} is now available to ${agentKind === "voice" ? "Voice" : "Background Agent"}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Tool access could not be saved.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <section className="browser-voice-plugin-setup">
      <button className="browser-voice-pill" onClick={onBack} type="button">
        ← MCP servers
      </button>
      <div className="browser-voice-section-head">
        <div>
          <span className="browser-voice-eyebrow-label">Hosted MCP</span>
          <h3>{item.displayName}</h3>
          <p>{item.description || "Imported MCP package"}</p>
        </div>
        <span className={`browser-voice-state ${item.state === "enabled" ? "is-ready" : ""}`}>
          {item.state === "enabled" ? "On" : "Off"}
        </span>
      </div>
      {hosted && runtimeStatus ? (
        <p className="browser-voice-form-note">
          Runtime: {runtimeStatus.state ?? "unknown"}
          {runtimeStatus.port ? ` · port ${runtimeStatus.port}` : ""}
          {runtimeStatus.lastError ? ` · ${runtimeStatus.lastError}` : ""}
        </p>
      ) : null}
      {migrationStatus ? (
        <p className="browser-voice-form-note">
          Package data:
          {migrationStatus.database ? ` database ${migrationStatus.database}` : ""}
          {migrationStatus.workspace ? ` · workspace ${migrationStatus.workspace}` : ""}
        </p>
      ) : null}
      {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
      {message ? <p className="browser-voice-management-message" role="status">{message}</p> : null}
      {schema ? (
        <ExtensionSchemaForm
          onSubmit={() => void saveSettings()}
          schema={schema}
          setValue={set}
          submitLabel="Save MCP settings"
          values={values}
          working={working}
        />
      ) : null}
      <div className="browser-voice-form">
        <h4>Server</h4>
        <p className="browser-voice-form-note">
          {hosted
            ? "Save settings first, then turn this MCP on. Vault starts the server and checks /health."
            : "This connection points at an external MCP URL you manage yourself."}
        </p>
        <div className="browser-voice-inline-actions">
          <button
            aria-pressed={item.state === "enabled"}
            className="browser-voice-pill"
            disabled={working}
            onClick={() => void toggleEnabled()}
            type="button"
          >
            {item.state === "enabled" ? "Turn off" : "Turn on"}
          </button>
          <button
            className="browser-voice-pill"
            disabled={working || item.state !== "enabled"}
            onClick={() => void discoverTools()}
            type="button"
          >
            Check tools
          </button>
        </div>
      </div>
      {tools.length ? (
        <div className="browser-voice-form">
          <h4>Tools</h4>
          <p className="browser-voice-form-note">Choose access level, then grant each tool to Voice or Background Agent.</p>
          <div className="browser-voice-tool-grant-list">
            <div className="browser-voice-tool-grant-head">
              <span>Tool</span>
              <span>Access</span>
              <span>Voice</span>
              <span>Background</span>
            </div>
            {tools.map((name) => (
              <div className="browser-voice-tool-grant-row" key={name}>
                <strong>{name}</strong>
                <select
                  aria-label={`${name} access`}
                  onChange={(event) =>
                    setEffect((current) => ({
                      ...current,
                      [name]: event.target.value as "read" | "write" | "delete",
                    }))
                  }
                  value={effect[name] ?? "read"}
                >
                  <option value="read">Read</option>
                  <option value="write">Write</option>
                  <option value="delete">Delete</option>
                </select>
                <button
                  className="browser-voice-pill"
                  disabled={working || !userId}
                  onClick={() => void grant(name, "voice")}
                  type="button"
                >
                  Voice
                </button>
                <button
                  className="browser-voice-pill browser-voice-pill-muted"
                  disabled={working || !userId}
                  onClick={() => void grant(name, "background")}
                  type="button"
                >
                  Background
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {onRemove ? (
        <div className="browser-voice-form">
          <h4>Remove from Vault</h4>
          <p className="browser-voice-form-note">
            {hosted
              ? "Stops the server and deletes package code, database, workspace files, settings, and tool grants from this Vault."
              : "Removes this external MCP connection and its tool grants from this Vault."}
          </p>
          <button
            className="browser-voice-account-danger"
            disabled={working}
            onClick={() => void onRemove()}
            type="button"
          >
            Remove MCP
          </button>
        </div>
      ) : null}
    </section>
  );
}
