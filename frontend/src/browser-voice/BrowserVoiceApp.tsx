import { BackgroundApprovals } from "@/browser-voice/background/BackgroundApprovals";
import { LivePreparationPanel } from "./conversation/LivePreparationPanel";
import { lazy, Suspense, useEffect, useState, type FormEvent } from "react";
import { AccountPanel } from "@/browser-voice/AccountPanel";
import { CapabilitiesPanel } from "@/browser-voice/CapabilitiesPanel";
import { ConnectionsPanel } from "@/browser-voice/ConnectionsPanel";
import { MemoryPanel } from "@/browser-voice/MemoryPanel";
import { BackgroundRunsPanel } from "@/browser-voice/BackgroundRunsPanel";
import { DocumentsPanel } from "@/browser-voice/DocumentsPanel";
import { SettingsPanel } from "@/browser-voice/SettingsPanel";
import { SetupFoldersStep } from "@/browser-voice/folders/SetupFoldersStep";
import { BrowserWorkspaceFileBrowser } from "@/browser-voice/BrowserWorkspaceFileBrowser";
import { PluginImportDialogHost } from "@/browser-voice/PluginImportDialogHost";
import { NotificationsMenu } from "@/browser-voice/NotificationsMenu";
import { Agent2AgentPanel } from "@/browser-voice/Agent2AgentPanel";
import { HomeVoice } from "@/browser-voice/HomeVoice";
import { OnboardingAiConfiguration } from "@/browser-voice/OnboardingAiConfiguration";
import { OptionalAccountsPanel } from "@/browser-voice/OptionalAccountsPanel";
import { useVoiceSession } from "@/browser-voice/useVoiceSession";
import { localApi, type LocalUser } from "@/browser-voice/localApi";
import {
  BrowserVoiceFutureNavigation,
  browserVoiceAccountInitials,
  type BrowserVoiceDestination,
} from "@/browser-voice/presentation/BrowserVoiceIcons";
import { PageHeader } from "@/browser-voice/presentation/ManagementLayout";

const ChatPanel = lazy(() => import("@/browser-voice/conversation/ChatPanel").then(module => ({ default: module.ChatPanel })));
type OnboardingStep = "name" | "hello" | "experience" | "credentials";

export function BrowserVoiceApp() {
  const [chatMounted, setChatMounted] = useState(false);
  const [onboardingDraft] = useState(readOnboardingDraft);
  const [ready, setReady] = useState(false);
  const [setupComplete, setSetupComplete] = useState(false);
  const [user, setUser] = useState<LocalUser | null>(null);
  const [destination, setDestination] =
    useState<BrowserVoiceDestination>(() => {
      const query = new URLSearchParams(window.location.search);
      return query.has("memoryPairing") ? "memory" : query.has("providerOAuth") ? "connections" : query.has("mcpSignIn") ? "capabilities" : "home";
    });
  useEffect(() => { if (destination === "chat") setChatMounted(true); }, [destination]);
  const [error, setError] = useState<string | null>(null);
  const { voiceState, statusText, subStatus, voicePreparation, voiceActivity, voiceSessionIdRef, remoteAudioRef, toggleVoice, closeVoice } = useVoiceSession(setError);
  const [optionalAccounts, setOptionalAccounts] = useState(false);
  const [aiConfiguration, setAiConfiguration] = useState(false);
  const [folderSetup, setFolderSetup] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [name, setName] = useState(onboardingDraft.name);
  const [experience, setExperience] = useState(onboardingDraft.experience);
  const [onboardingStep, setOnboardingStep] = useState<OnboardingStep>(onboardingDraft.step);
  const [setupCredential] = useState(() => {
    const fragmentCredential = setupCredentialFromFragment();
    return fragmentCredential;
  });
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [activationCredential] = useState(() =>
    credentialFromFragment("activate"),
  );

  useEffect(() => {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, [destination]);

  useEffect(() => {
    if (new URLSearchParams(location.search).get("setup") === "fresh")
      // Drop any stale legacy fragment while retaining the server-validated
      // bootstrap query through refresh and owner registration.
      history.replaceState({}, "", `${location.pathname}${location.search}`);
  }, []);

  useEffect(() => {
    if (onboardingStep !== "hello") return;
    const timer = window.setTimeout(() => setOnboardingStep("experience"), 1800);
    return () => window.clearTimeout(timer);
  }, [onboardingStep]);

  useEffect(() => {
    if (!setupCredential) return;
    void localApi.establishSetupSession(setupCredential).catch((caught) =>
      setError(caught instanceof Error ? caught.message : "First-run setup could not be resumed."),
    );
  }, [setupCredential]);

  useEffect(() => {
    if (setupComplete) return;
    sessionStorage.setItem("resono_vault_onboarding", JSON.stringify({ name, experience, step: onboardingStep }));
  }, [experience, name, onboardingStep, setupComplete]);

  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        const status = await localApi.setupStatus();
        if (!live) return;
        setSetupComplete(status.setupComplete);
        if (status.setupComplete) {
          try {
            const current = (await localApi.me()).user;
            const phase = sessionStorage.getItem("resono_vault_onboarding_phase");
            if (phase === "accounts") setOptionalAccounts(true);
            else if (phase === "folders") setFolderSetup(true);
            else if (phase === "provider") setAiConfiguration(true);
            else setUser(current);
          } catch {
            /* signed out */
          }
        }
      } catch (caught) {
        if (live)
          setError(
            caught instanceof Error
              ? caught.message
              : "Local Vault is unavailable.",
          );
      } finally {
        if (live) setReady(true);
      }
    })();
    return () => {
      live = false;
      void closeVoice(true);
    };
  }, []);

  async function registerOwner(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const data = new FormData(event.currentTarget);
    const selectedPassword = String(data.get("password") || "");
    try {
      if (selectedPassword !== String(data.get("confirmation") || "")) throw new Error("Passwords do not match.");
      await localApi.registerOwner({ setupCredential, username: String(data.get("username") || ""), password: selectedPassword, displayName: name, experienceStyle: experience });
      history.replaceState({}, "", location.pathname);
      sessionStorage.removeItem("resono_vault_onboarding");
      sessionStorage.setItem("resono_vault_onboarding_phase", "accounts");
      setSetupComplete(true);
      setOptionalAccounts(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Master account could not be created.");
    } finally {
      setSubmitting(false);
    }
  }

  async function login(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const signedIn = (await localApi.login(username, password)).user;
      setUser(signedIn);
      if (!signedIn.mustChangePassword) setPassword("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign in failed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function activate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const data = new FormData(event.currentTarget);
    const newPassword = String(data.get("newPassword") || "");
    try {
      if (!activationCredential)
        throw new Error(
          "This account setup link is missing its local credential.",
        );
      if (newPassword !== String(data.get("confirmation") || ""))
        throw new Error("Passwords do not match.");
      const result = await localApi.activate(activationCredential, newPassword);
      history.replaceState({}, "", `${location.pathname}${location.search}`);
      setUser(result.user);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Account setup failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function finishTemporaryPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const newPassword = String(form.get("newPassword") || "");
    // After a reload the sign-in password is gone from memory; the form then asks for it.
    const currentPassword = password || String(form.get("currentPassword") || "");
    try {
      await localApi.changePassword(currentPassword, newPassword);
      setUser((await localApi.me()).user);
      setPassword("");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Password could not be changed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function logout() {
    await closeVoice(true);
    try {
      await localApi.logout();
    } finally {
      setUser(null);
      setDestination("home");
    }
  }

  if (!ready)
    return (
      <main className="browser-voice-shell">
        <section className="browser-voice-card is-login-page">
          <div className="browser-voice-login-brand">
            <img alt="ReSono Labs" src="/resono-logo.svg" />
            <p>Browser Voice</p>
          </div>
          <p className="browser-voice-management-empty">Opening local Vault…</p>
        </section>
      </main>
    );

  const shellTitle = "Voice"; // The title only renders on the Voice page.
  const isLive = voiceState === "live" || voiceState === "responding";
  const activeUser = user && !user.mustChangePassword ? user : null;
  return (
    <main className={`browser-voice-shell${activeUser ? " is-b0r" : ""}`}>
      <audio
        ref={remoteAudioRef}
        autoPlay
        playsInline
        style={{ display: "none" }}
      />
      <section
        className={`browser-voice-card ${activeUser ? `browser-voice-app-frame${destination === "chat" ? " is-chat-page" : destination === "workspace" ? " is-workspace-page" : ""}` : "is-login-page"}`}
      >
        {activeUser ? (
          <aside className="browser-voice-desktop-rail">
            <img alt="ReSono Labs" src="/resono-logo.svg" />
            <BrowserVoiceFutureNavigation
              activeDestination={destination}
              onNavigate={setDestination}
              placement="desktop"
            />
          </aside>
        ) : null}
        <header className={`browser-voice-header${destination !== "home" ? " is-management" : ""}`}>
          {activeUser ? (
            <>
              {destination === "home" ? <div className="browser-voice-desktop-title">
                <p className="browser-voice-eyebrow">Browser Voice</p>
                <h1 className="browser-voice-title">{shellTitle}</h1>
              </div> : <span />}
              <div className="browser-voice-mobile-brand">
                <img alt="ReSono Labs" src="/resono-logo.svg" />
              </div>
              <div className="browser-voice-header-actions">
                <div className="browser-voice-header-action-row">
                  <span id="vault-header-slot" className="vault-header-slot" />
                  <NotificationsMenu />
                  <details className="browser-voice-account-menu">
                  <summary aria-label="Account">
                    {browserVoiceAccountInitials(activeUser.displayName)}
                  </summary>
                  <div>
                    <button
                      className="browser-voice-pill"
                      onClick={() => setDestination("account")}
                      type="button"
                    >
                      Account
                    </button>
                    <button
                      className="browser-voice-pill browser-voice-pill-muted"
                      onClick={() => void logout()}
                      type="button"
                    >
                      Logout
                    </button>
                    </div>
                  </details>
                  <BrowserVoiceFutureNavigation
                    activeDestination={destination}
                    onNavigate={setDestination}
                    placement="mobile"
                  />
                </div>
              </div>
            </>
          ) : (
            <div className="browser-voice-login-brand">
              <img alt="ReSono Labs" src="/resono-logo.svg" />
              <p>Browser Voice</p>
            </div>
          )}
        </header>
        {!activeUser ? (
          <section className="browser-voice-login-panel">
            <h1>
              {user?.mustChangePassword
                ? "Choose a new password"
                : activationCredential
                  ? "Finish account setup"
                  : optionalAccounts
                    ? "Add people to your Vault"
                    : folderSetup
                      ? "Choose folders for your agents"
                    : aiConfiguration
                      ? "Configure AI"
                      : setupComplete
                        ? "Sign in"
                        : onboardingStep === "hello"
                          ? `Hello, ${name}`
                        : onboardingStep === "credentials"
                          ? "Secure your Vault"
                        : onboardingStep === "experience"
                            ? "Make it yours"
                            : "Meet your Vault"}
            </h1>
            {user?.mustChangePassword ? (
              <form
                className="browser-voice-form"
                onSubmit={(event) => void finishTemporaryPassword(event)}
              >
                <p>
                  Your temporary password must be replaced before Vault opens.
                </p>
                {password ? null : (
                  <label>
                    <span>Temporary password</span>
                    <input autoComplete="current-password" name="currentPassword" required type="password" />
                  </label>
                )}
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
                <button
                  className="browser-voice-submit"
                  disabled={submitting}
                  type="submit"
                >
                  Set password
                </button>
                <button
                  className="browser-voice-pill browser-voice-pill-muted"
                  onClick={() => void logout()}
                  type="button"
                >
                  Logout
                </button>
              </form>
            ) : activationCredential ? (
              <form
                className="browser-voice-form"
                onSubmit={(event) => void activate(event)}
              >
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
                <label>
                  <span>Confirm password</span>
                  <input
                    autoComplete="new-password"
                    minLength={10}
                    name="confirmation"
                    required
                    type="password"
                  />
                </label>
                <button
                  className="browser-voice-submit"
                  disabled={submitting}
                  type="submit"
                >
                  Finish setup
                </button>
              </form>
            ) : optionalAccounts ? (
              <OptionalAccountsPanel
                onDone={() => {
                  setOptionalAccounts(false);
                  sessionStorage.setItem("resono_vault_onboarding_phase", "folders");
                  setFolderSetup(true);
                }}
              />
            ) : folderSetup ? (
              <SetupFoldersStep
                onDone={() => {
                  setFolderSetup(false);
                  sessionStorage.setItem("resono_vault_onboarding_phase", "provider");
                  setAiConfiguration(true);
                }}
              />
            ) : aiConfiguration ? (
              <OnboardingAiConfiguration
                onDone={() => {
                  setAiConfiguration(false);
                  sessionStorage.removeItem("resono_vault_onboarding_phase");
                  void localApi
                    .me()
                    .then((value) => setUser(value.user))
                    .catch((caught) => setError(String(caught)));
                }}
              />
            ) : setupComplete ? (
              <form
                className="browser-voice-form"
                onSubmit={(event) => void login(event)}
              >
                <label>
                  <span>Username</span>
                  <input
                    autoComplete="username"
                    onChange={(event) => setUsername(event.target.value)}
                    required
                    value={username}
                  />
                </label>
                <label>
                  <span>Password</span>
                  <input
                    autoComplete="current-password"
                    onChange={(event) => setPassword(event.target.value)}
                    required
                    type="password"
                    value={password}
                  />
                </label>
                <button
                  className="browser-voice-submit"
                  disabled={submitting}
                  type="submit"
                >
                  {submitting ? "Signing in..." : "Sign in"}
                </button>
              </form>
            ) : onboardingStep === "hello" ? (
              <section className="browser-voice-onboarding-hello" aria-live="polite">
                <span className="browser-voice-onboarding-orbit" aria-hidden="true" />
                <p>Welcome to your Vault.</p>
                <button className="browser-voice-text-action" onClick={() => setOnboardingStep("experience")} type="button">Continue</button>
              </section>
            ) : onboardingStep === "credentials" ? (
              <form className="browser-voice-form browser-voice-onboarding-step" onSubmit={(event) => void registerOwner(event)}>
                <p className="browser-voice-onboarding-prompt">Create the master account used to manage this Vault.</p>
                <label><span>Username</span><input autoComplete="username" defaultValue={name.trim().toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"") || "owner"} name="username" required /></label>
                <label><span>Password</span><input autoComplete="new-password" minLength={10} name="password" required type="password" /></label>
                <label><span>Confirm password</span><input autoComplete="new-password" minLength={10} name="confirmation" required type="password" /></label>
                <button className="browser-voice-submit" disabled={submitting} type="submit">{submitting ? "Securing..." : "Continue"}</button>
              </form>
            ) : onboardingStep === "experience" ? (
              <form
                className="browser-voice-form browser-voice-onboarding-step"
                onSubmit={(event) => { event.preventDefault(); setOnboardingStep("credentials"); }}
              >
                <p className="browser-voice-onboarding-prompt">How should Vault feel when it speaks with you?</p>
                <div className="browser-voice-experience-grid" role="group" aria-label="Experience">
                  {(["strict", "concise", "warm", "funny"] as const).map((option) => <button aria-pressed={experience === option} className={experience === option ? "is-selected" : ""} key={option} onClick={() => setExperience(option)} type="button"><strong>{option[0].toUpperCase() + option.slice(1)}</strong><small>{{strict:"Direct and disciplined",concise:"Brief and efficient",warm:"Thoughtful and welcoming",funny:"Playful when it fits"}[option]}</small></button>)}
                </div>
                <button
                  className="browser-voice-submit"
                  disabled={submitting}
                  type="submit"
                >
                  {submitting ? "Creating..." : "Continue"}
                </button>
              </form>
            ) : (
              <form className="browser-voice-form browser-voice-onboarding-step" onSubmit={(event) => { event.preventDefault(); setOnboardingStep("hello"); }}>
                <p className="browser-voice-onboarding-prompt">What should your Vault call you?</p>
                <label><span>Your name</span><input autoComplete="name" autoFocus onChange={(event) => setName(event.target.value)} required value={name} /></label>
                <button className="browser-voice-submit" type="submit">Continue</button>
              </form>
            )}
          </section>
        ) : (
          <div className={`browser-voice-content-surface ${destination === "chat" ? "is-chat" : destination === "workspace" ? "is-workspace" : "is-management"}`}>
            {chatMounted ? <Suspense fallback={destination === "chat" ? <p role="status">Loading Chat…</p> : null}>
              <ChatPanel key={`${activeUser.userId}:${activeUser.activeWorkspaceId}`} active={destination === "chat"}
                voiceActive={isLive} voiceBusy={voiceState === "connecting"} onToggleVoice={() => void toggleVoice()} />
            </Suspense> : null}
            {destination === "home" ? (
              <>
                <HomeVoice
                  voiceState={voiceState}
                  statusText={statusText}
                  subStatus={subStatus}
                  isLive={isLive}
                  activity={voicePreparation ? [] : voiceActivity}
                  onToggle={() => void toggleVoice()}
                />
                {isLive && voiceSessionIdRef.current ? (
                  <BackgroundApprovals key={voiceSessionIdRef.current}
                    voiceSessionId={voiceSessionIdRef.current} pollIntervalMs={1500} pollWhileHidden />
                ) : null}
              </>
            ) : null}
            {destination === "capabilities" ? (
              <div className="browser-voice-management-page">
                <CapabilitiesPanel />
              </div>
            ) : null}
            {destination === "connections" ? (
              <div className="browser-voice-management-page">
                <ConnectionsPanel />
              </div>
            ) : null}
            {destination === "memory" ? (
              <div className="browser-voice-management-page">
                <MemoryPanel />
              </div>
            ) : null}
            {destination === "documents" ? (
              <div className="browser-voice-management-page">
                <DocumentsPanel />
              </div>
            ) : null}
            {destination === "settings" ? (
              <div className="browser-voice-management-page">
                <SettingsPanel isAdmin={activeUser.isDeviceOwner} onOpenBackgroundWork={() => setDestination("background")} />
              </div>
            ) : null}
            {destination === "workspace" ? (
              <div className="browser-voice-management-page browser-voice-workspace-page">
                <PageHeader title={`${activeUser.displayName}'s Workspace`} titleId="workspace-title" />
                <BrowserWorkspaceFileBrowser initiallyExpanded />
              </div>
            ) : null}
            {destination === "agent2agent" ? (
              <div className="browser-voice-management-page">
                <Agent2AgentPanel />
              </div>
            ) : null}
            {destination === "background" ? (
              <div className="browser-voice-management-page">
                <BackgroundRunsPanel isDeviceOwner={activeUser.isDeviceOwner} />
              </div>
            ) : null}
            {destination === "account" ? (
              <div className="browser-voice-management-page">
                <AccountPanel
                  onLogout={() => void logout()}
                  user={activeUser}
                />
              </div>
            ) : null}
          </div>
        )}
        {error ? (
          <div
            className="browser-voice-feedback browser-voice-feedback-error"
            role="alert"
          >
            {error}
          </div>
        ) : null}
      </section>
      {activeUser && destination === "home" && voicePreparation ? <div className="browser-voice-live-preparation"><LivePreparationPanel value={voicePreparation} surface="voice" /></div> : null}
      {activeUser ? <PluginImportDialogHost /> : null}
    </main>
  );
}

function setupCredentialFromFragment() {
  const serverCredential = new URLSearchParams(location.search).get("bootstrap")?.trim();
  if (serverCredential) return serverCredential;
  // A server-validated fresh setup uses the HttpOnly resume cookie. Never let
  // a fragment retained by browser history from an older factory-reset run
  // replace that authority during the first render.
  if (new URLSearchParams(location.search).get("setup") === "fresh") return "";
  return credentialFromFragment("setup");
}

function readOnboardingDraft(): { name: string; experience: string; step: OnboardingStep } {
  try {
    const setupQuery = new URLSearchParams(location.search);
    if (setupQuery.get("setup") === "fresh" || setupQuery.has("bootstrap")) {
      sessionStorage.removeItem("resono_vault_setup");
      sessionStorage.removeItem("resono_vault_onboarding");
      sessionStorage.removeItem("resono_vault_onboarding_phase");
      return { name: "", experience: "", step: "name" };
    }
    const value = JSON.parse(sessionStorage.getItem("resono_vault_onboarding") || "{}") as Record<string, unknown>;
    const step: OnboardingStep = value.step === "hello" || value.step === "experience" || value.step === "credentials" ? value.step : "name";
    return {
      name: typeof value.name === "string" ? value.name : "",
      experience: typeof value.experience === "string" ? value.experience : "",
      step,
    };
  } catch {
    return { name: "", experience: "", step: "name" };
  }
}

function credentialFromFragment(key: "setup" | "activate") {
  const value = new URLSearchParams(location.hash.replace(/^#/, "")).get(key);
  return value?.trim() || "";
}

