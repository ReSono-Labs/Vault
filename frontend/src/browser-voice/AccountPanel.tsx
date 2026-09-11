import { useEffect, useState, type FormEvent } from "react";
import {
  localApi,
  type AccountProviderAccess,
  type LocalUser,
  type ManagedLocalUser,
  type PasswordMode,
} from "@/browser-voice/localApi";

export function AccountPanel({
  onLogout,
  user,
}: {
  onLogout: () => void;
  user: LocalUser;
}) {
  const [error, setError] = useState<string | null>(null);
  const [users, setUsers] = useState<ManagedLocalUser[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [createMode, setCreateMode] = useState<PasswordMode>("setup_link");
  const [setupLink, setSetupLink] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [resetUserId, setResetUserId] = useState<string | null>(null);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [providerAccess, setProviderAccess] = useState<AccountProviderAccess | null>(null);
  const [providerMode, setProviderMode] = useState<"shared" | "individual">("shared");
  useEffect(() => {
    if (user.isDeviceOwner)
      localApi
        .localUsers()
        .then((value) => setUsers(value.items))
        .catch((caught) => setError(String(caught)));
  }, [user.isDeviceOwner]);
  async function selectManagedUser(userId: string) {
    if (selectedUserId === userId) {
      setSelectedUserId(null);
      setResetUserId(null);
      setProviderAccess(null);
      return;
    }
    setSelectedUserId(userId);
    setResetUserId(null);
    const target = users.find((item) => item.userId === userId);
    if (!target || target.isDeviceOwner) {
      setProviderAccess(null);
      return;
    }
    try {
      const access = await localApi.accountProviderAccess(userId);
      setProviderAccess(access);
      setProviderMode(access.accessMode);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Provider access could not be loaded.");
    }
  }
  async function saveProviderAccess(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedUserId) return;
    const data = new FormData(event.currentTarget);
    try {
      const access = await localApi.setAccountProviderAccess(selectedUserId, {
        accessMode: providerMode,
        apiKey: providerMode === "individual" ? String(data.get("apiKey") || "") : undefined,
      });
      setProviderAccess(access);
      event.currentTarget.reset();
      setMessage(providerMode === "shared" ? "Account now uses the Vault shared provider." : "Individual provider key encrypted and assigned.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Provider access could not be saved.");
    }
  }
  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    const value = (name: string) => String(data.get(name) || "").trim();
    try {
      const created = await localApi.createLocalUser({
        username: value("username"),
        password: value("password") || undefined,
        passwordMode: createMode,
        ageGroup: value("ageGroup") as "under_18" | "adult",
        displayName: value("displayName"),
        experienceStyle: value("experienceStyle"),
      });
      setUsers((await localApi.localUsers()).items);
      form.reset();
      setCreateMode("setup_link");
      setSetupLink(
        created.setupCredential
          ? `${location.origin}${location.pathname}#activate=${encodeURIComponent(created.setupCredential)}`
          : null,
      );
      setMessage(
        created.setupCredential
          ? "Local user created. Copy the setup link now; it is shown only once."
          : "Local user created.",
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Local user could not be created.",
      );
    }
  }
  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      await localApi.changePassword(
        String(data.get("currentPassword") || ""),
        String(data.get("newPassword") || ""),
      );
      form.reset();
      setMessage("Password changed. Other signed-in sessions were revoked.");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Password could not be changed.",
      );
    }
  }
  async function resetUserPassword(
    event: FormEvent<HTMLFormElement>,
    target: ManagedLocalUser,
  ) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      const mode = String(
        data.get("passwordMode") || "temporary_password",
      ) as PasswordMode;
      const result = await localApi.resetLocalUserPassword(
        target.userId,
        mode,
        String(data.get("newPassword") || "") || undefined,
      );
      form.reset();
      setSetupLink(
        result.setupCredential
          ? `${location.origin}${location.pathname}#activate=${encodeURIComponent(result.setupCredential)}`
          : null,
      );
      setMessage(
        result.setupCredential
          ? `${target.displayName}'s setup link is ready and shown only once.`
          : `${target.displayName}'s password was reset and all sessions were revoked.`,
      );
      setUsers((await localApi.localUsers()).items);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Password could not be reset.",
      );
    }
  }
  async function removeUser(target: ManagedLocalUser) {
    if (
      !window.confirm(
        `Remove ${target.displayName}'s local account? They will be signed out immediately.`,
      )
    )
      return;
    setError(null);
    setMessage(null);
    try {
      await localApi.removeLocalUser(target.userId);
      setUsers((await localApi.localUsers()).items);
      setSelectedUserId(null);
      setProviderAccess(null);
      setMessage(`${target.displayName}'s local account was removed.`);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Local account could not be removed.",
      );
    }
  }
  return (
    <section className="browser-voice-account" aria-labelledby="account-title">
      <header className="browser-voice-management-heading">
        <div>
          <span className="browser-voice-eyebrow-label">Accounts</span>
          <h2 id="account-title">People and access</h2>
          <p>Manage your profile, password, and isolated local workspaces.</p>
        </div>
      </header>
      <div className="browser-voice-account-section">
        <dl className="browser-voice-account-facts">
          <div>
            <dt>Name</dt>
            <dd>{user.displayName}</dd>
          </div>
          <div>
            <dt>Experience</dt>
            <dd>{user.experienceStyle}</dd>
          </div>
          <div>
            <dt>Authority</dt>
            <dd>{user.isDeviceOwner ? "Master account" : "Local user"}</dd>
          </div>
        </dl>
      </div>
      <header className="browser-voice-management-heading">
        <div>
          <h3>Password</h3>
          <p>
            {user.passwordMode === "master_managed"
              ? "This password is controlled by the master account."
              : "Change this local account password."}
          </p>
        </div>
      </header>
      {user.passwordMode !== "master_managed" ? (
        <form
          className="browser-voice-form"
          onSubmit={(event) => void changePassword(event)}
        >
          <label>
            <span>Current password</span>
            <input
              autoComplete="current-password"
              name="currentPassword"
              required
              type="password"
            />
          </label>
          <label>
            <span>New password</span>
            <input
              autoComplete="new-password"
              minLength={10}
              name="newPassword"
              required
              type="password"
            />
          </label>
          <button className="browser-voice-submit" type="submit">
            Change password
          </button>
        </form>
      ) : null}
      {user.isDeviceOwner ? (
        <>
          <header className="browser-voice-management-heading">
            <div>
              <h3>Local users</h3>
              <p>{users.length} of 4 accounts configured.</p>
            </div>
            {users.length < 4 ? <button className="browser-voice-submit" onClick={() => setShowCreate((value) => !value)} type="button">{showCreate ? "Close" : "Add user"}</button> : null}
          </header>
          <div className="browser-voice-account-directory">
            {users.map((item) => (
              <button aria-expanded={selectedUserId === item.userId} className={selectedUserId === item.userId ? "is-selected" : ""} key={item.userId} onClick={() => void selectManagedUser(item.userId)} type="button">
                <span>
                  <strong>{item.displayName}</strong>
                  <small>
                    {item.username} ·{" "}
                    {item.isDeviceOwner
                      ? "Master account"
                      : item.activationPending
                        ? "setup pending"
                        : (item.passwordMode || "user_managed").replaceAll(
                            "_",
                            " ",
                          )}{" "}
                    ·{" "}
                    {item.ageGroup === "under_18" ? "under 18" : "18 or older"}
                  </small>
                </span>
                <b aria-hidden="true">{selectedUserId === item.userId ? "−" : "+"}</b>
              </button>
            ))}
          </div>
          {selectedUserId ? (() => {
            const item = users.find((candidate) => candidate.userId === selectedUserId);
            if (!item) return null;
            return <section className="browser-voice-account-detail">
              <div className="browser-voice-section-head"><div><span className="browser-voice-eyebrow-label">Selected account</span><h3>{item.displayName}</h3><p>@{item.username} · {item.ageGroup === "under_18" ? "Under 18" : "18 or older"}</p></div></div>
              {item.isDeviceOwner ? <p className="browser-voice-form-note">This is the protected master account. Manage its password under Your account.</p> : <>
                <div className="browser-voice-inline-actions"><button className="browser-voice-pill" onClick={() => setResetUserId((value) => value === item.userId ? null : item.userId)} type="button">{resetUserId === item.userId ? "Cancel password reset" : "Reset password"}</button>
                <button className="browser-voice-account-danger" onClick={() => void removeUser(item)} type="button">Delete account</button></div>
                {resetUserId === item.userId ? <form
                      className="browser-voice-form"
                      onSubmit={(event) => void resetUserPassword(event, item)}
                    >
                      <label>
                        <span>Password control</span>
                        <select
                          name="passwordMode"
                          defaultValue="temporary_password"
                        >
                          <option value="setup_link">
                            User chooses from setup link
                          </option>
                          <option value="temporary_password">
                            Temporary password; change at login
                          </option>
                          <option value="master_managed">
                            Master-managed password
                          </option>
                        </select>
                      </label>
                      <label>
                        <span>Password (not needed for setup link)</span>
                        <input
                          aria-label={`New password for ${item.displayName}`}
                          autoComplete="new-password"
                          minLength={10}
                          name="newPassword"
                          type="password"
                        />
                      </label>
                      <button className="browser-voice-pill" type="submit">
                        Apply password reset
                      </button>
                    </form> : null}
                <form className="browser-voice-form" onSubmit={(event) => void saveProviderAccess(event)}>
                  <label><span>Provider access</span><select onChange={(event) => setProviderMode(event.target.value as "shared" | "individual")} value={providerMode}><option value="shared">Use Vault shared key</option><option value="individual">Use an individual key</option></select></label>
                  {providerMode === "individual" ? <label><span>Individual API key</span><input autoComplete="off" name="apiKey" required type="password" /></label> : null}
                  <p className="browser-voice-form-note">{providerMode === "shared" ? (providerAccess?.sharedConfigured ? "The shared Vault key is configured." : "The shared Vault key still needs to be configured in Connections.") : (providerAccess?.individualConfigured ? "An individual encrypted key is currently configured. Saving replaces it." : "This account does not have an individual key yet.")}</p>
                  <button className="browser-voice-submit" type="submit">Save provider access</button>
                </form>
              </>}
            </section>;
          })() : <p className="browser-voice-management-empty">Select an account to manage access.</p>}
          {setupLink ? (
            <div className="browser-voice-management-message" role="status">
              <strong>One-time local setup link</strong>
              <p>
                <code>{setupLink}</code>
              </p>
            </div>
          ) : null}
          {users.length < 4 && showCreate ? (
            <form
              className="browser-voice-form"
              onSubmit={(event) => void createUser(event)}
            >
              <label>
                <span>Name</span>
                <input autoComplete="name" name="displayName" required />
              </label>
              <label>
                <span>Username</span>
                <input autoComplete="username" name="username" required />
              </label>
              <label>
                <span>Password control</span>
                <select
                  name="passwordMode"
                  onChange={(event) =>
                    setCreateMode(event.target.value as PasswordMode)
                  }
                  value={createMode}
                >
                  <option value="setup_link">
                    User chooses from setup link
                  </option>
                  <option value="temporary_password">
                    Temporary password; change at login
                  </option>
                  <option value="master_managed">
                    Master-managed password
                  </option>
                </select>
              </label>
              <label>
                <span>Age group</span>
                <select defaultValue="adult" name="ageGroup">
                  <option value="adult">18 or older</option>
                  <option value="under_18">Under 18</option>
                </select>
              </label>
              {createMode !== "setup_link" ? (
                <label>
                  <span>
                    {createMode === "temporary_password"
                      ? "Temporary password"
                      : "Master-managed password"}
                  </span>
                  <input
                    autoComplete="new-password"
                    minLength={10}
                    name="password"
                    required
                    type="password"
                  />
                </label>
              ) : null}
              <label>
                <span>Experience</span>
                <select defaultValue="warm" name="experienceStyle">
                  <option value="strict">Strict</option>
                  <option value="concise">Concise</option>
                  <option value="warm">Warm</option>
                  <option value="funny">Funny</option>
                </select>
              </label>
              <button className="browser-voice-submit" type="submit">
                Create local user
              </button>
            </form>
          ) : null}
        </>
      ) : null}
      <button
        className="browser-voice-account-danger browser-voice-account-logout"
        onClick={onLogout}
        type="button"
      >
        Sign out
      </button>
      {message ? (
        <div className="browser-voice-management-message" role="status">
          {message}
        </div>
      ) : null}
      {error ? (
        <div className="browser-voice-management-error" role="alert">
          {error}
        </div>
      ) : null}
    </section>
  );
}
