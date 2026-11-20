import { useState, type FormEvent } from "react";
import { localApi, type PasswordMode } from "@/browser-voice/localApi";

export function OptionalAccountsPanel({ onDone }: { onDone: () => void }) {
  const [adding, setAdding] = useState(false);
  const [mode, setMode] = useState<PasswordMode>("setup_link");
  const [created, setCreated] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    const text = (name: string) => String(data.get(name) || "").trim();
    try {
      const result = await localApi.createLocalUser({
        username: text("username"),
        displayName: text("displayName"),
        experienceStyle: text("experienceStyle"),
        passwordMode: mode,
        password: text("password") || undefined,
        ageGroup: text("ageGroup") as "under_18" | "adult",
      });
      setCreated((value) => value + 1);
      form.reset();
      setMode("setup_link");
      setMessage(
        result.setupCredential
          ? `Copy this one-time setup link now: ${location.origin}${location.pathname}#activate=${encodeURIComponent(result.setupCredential)}`
          : "Account created. The password control you selected is active.",
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Account could not be created.",
      );
    }
  }

  return (
    <div className="browser-voice-onboarding-choice">
      {!adding && created === 0 ? <><p>Would you like to add other users now? You can always manage accounts later.</p><div className="browser-voice-choice-actions"><button className="browser-voice-submit" onClick={() => setAdding(true)} type="button">Add users now</button><button className="browser-voice-pill browser-voice-pill-muted" onClick={onDone} type="button">Not now</button></div></> : null}
      {adding && created < 3 ? (
        <form
          className="browser-voice-form browser-voice-onboarding-later-form"
          onSubmit={(event) => void create(event)}
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
            <span>Age group</span>
            <select defaultValue="adult" name="ageGroup">
              <option value="adult">18 or older</option>
              <option value="under_18">Under 18</option>
            </select>
          </label>
          <label>
            <span>Password control</span>
            <select
              onChange={(event) => setMode(event.target.value as PasswordMode)}
              value={mode}
            >
              <option value="setup_link">User chooses from setup link</option>
              <option value="temporary_password">
                Temporary password; change at login
              </option>
              <option value="master_managed">Master-managed password</option>
            </select>
          </label>
          {mode !== "setup_link" ? (
            <label>
              <span>
                {mode === "temporary_password"
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
          {message ? <div className="browser-voice-management-message" role="status">{message}</div> : null}
          {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
          <div className="browser-voice-onboarding-actions">
            <button className="browser-voice-submit" type="submit">Add account</button>
            <button className="browser-voice-pill browser-voice-pill-muted" onClick={onDone} type="button">{created ? "Continue" : "Not now"}</button>
          </div>
        </form>
      ) : null}
      {!adding && message ? (
        <div className="browser-voice-management-message" role="status">
          {message}
        </div>
      ) : null}
      {!adding && error ? (
        <div className="browser-voice-management-error" role="alert">
          {error}
        </div>
      ) : null}
      {adding && created >= 3 ? <div className="browser-voice-onboarding-actions"><button className="browser-voice-submit" onClick={onDone} type="button">Continue</button></div> : null}
    </div>
  );
}
