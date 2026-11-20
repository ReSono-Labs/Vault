import { useEffect, useState } from "react";

import type { McpAccountStatus } from "@/browser-voice/api/extensions";
import type { ManagedLocalUser } from "@/browser-voice/api/identity";
import { localApi } from "@/browser-voice/localApi";

/** Sign-in for one remote MCP connection. Each person signs in with their own account; the
 *  device owner can share theirs with chosen people. Nobody's calls use another person's
 *  account. */
export function McpAccountControl({ extensionId, isDeviceOwner }: { extensionId: string; isDeviceOwner: boolean }) {
  const [status, setStatus] = useState<McpAccountStatus | null>(null);
  const [users, setUsers] = useState<ManagedLocalUser[]>([]);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsClient, setNeedsClient] = useState(false);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");

  useEffect(() => {
    void localApi.mcpAccount(extensionId).then(setStatus).catch(() => setStatus(null));
  }, [extensionId]);
  useEffect(() => {
    if (isDeviceOwner && status?.isSharedAccount)
      void localApi.localUsers().then((result) => setUsers(result.items)).catch(() => setUsers([]));
  }, [isDeviceOwner, status?.isSharedAccount]);

  async function run(work: () => Promise<McpAccountStatus | void>) {
    setWorking(true);
    setError(null);
    try {
      const next = await work();
      if (next) setStatus(next);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Vault could not update this account.";
      setError(message);
      if (/client ID/i.test(message)) setNeedsClient(true);
    } finally {
      setWorking(false);
    }
  }

  async function signIn() {
    await run(async () => {
      const redirectUri = `${window.location.origin}/extensions/oauth/callback`;
      const started = await localApi.mcpAccountAction<{ authorizationUrl: string }>(
        extensionId, { action: "sign-in", redirectUri });
      window.location.assign(started.authorizationUrl);
    });
  }

  if (!status) return null;
  const describe = status.account === "personal"
    ? status.isSharedAccount ? "Your account, shared with people you chose." : "Signed in with your own account."
    : status.account === "shared" ? "Using the shared account the device owner set up."
      : "Not signed in. Tools that need an account will ask you to sign in.";
  return (
    <div className="browser-voice-form">
      <h4>Account</h4>
      <p className="browser-voice-form-note">{describe}{status.account === "shared" ? <> <strong>Shared</strong></> : null}</p>
      {status.expiresAt ? <p className="browser-voice-form-note">
        Sign-in valid until {new Date(status.expiresAt * 1000).toLocaleString()}{status.renewable ? " (renews automatically)" : ""}.
      </p> : null}
      <div className="browser-voice-capability-actions">
        <button className="browser-voice-pill" disabled={working} onClick={() => void signIn()} type="button">
          {status.account === "personal" && status.kind === "oauth" ? "Sign in again" : "Sign in"}
        </button>
        {status.account === "personal" ? (
          <button className="browser-voice-pill browser-voice-pill-muted" disabled={working}
            onClick={() => void run(() => localApi.mcpAccountAction(extensionId, { action: "disconnect" }))} type="button">
            Disconnect
          </button>
        ) : null}
        {isDeviceOwner && status.account === "personal" ? (
          <button className="browser-voice-pill browser-voice-pill-muted" disabled={working}
            onClick={() => void run(() => localApi.mcpAccountAction(extensionId, { action: "share", shared: !status.isSharedAccount }))}
            type="button">
            {status.isSharedAccount ? "Stop sharing" : "Share this account"}
          </button>
        ) : null}
      </div>
      {isDeviceOwner && status.isSharedAccount ? (
        <fieldset className="browser-voice-form">
          <legend>Who may use the shared account</legend>
          {users.filter((user) => !user.isDeviceOwner).map((user) => (
            <label key={user.userId}>
              <input checked={status.sharedWith?.includes(user.userId) ?? false} disabled={working}
                onChange={(event) => void run(() => localApi.mcpAccountAction(extensionId, {
                  action: "share-grant", userId: user.userId, granted: event.currentTarget.checked }))}
                type="checkbox" />
              <span>{user.displayName}</span>
            </label>
          ))}
        </fieldset>
      ) : null}
      {isDeviceOwner && needsClient ? (
        <form className="browser-voice-form" onSubmit={(event) => {
          event.preventDefault();
          void run(async () => {
            await localApi.mcpAccountAction(extensionId, { action: "client", clientId, clientSecret: clientSecret || undefined });
            setNeedsClient(false);
            setClientSecret("");
          });
        }}>
          <p className="browser-voice-form-note">This service needs Vault registered with it. Create an OAuth client at the provider with the return address {window.location.origin}/extensions/oauth/callback and enter it here.</p>
          <label><span>Client ID</span><input onChange={(event) => setClientId(event.currentTarget.value)} required value={clientId} /></label>
          <label><span>Client secret (optional)</span><input autoComplete="off" onChange={(event) => setClientSecret(event.currentTarget.value)} type="password" value={clientSecret} /></label>
          <button className="browser-voice-submit" disabled={working} type="submit">Save client</button>
        </form>
      ) : null}
      {error ? <p className="browser-voice-management-error" role="alert">{error}</p> : null}
    </div>
  );
}
