import { useEffect, useRef, useState, type FormEvent } from "react";
import { AccountPanel } from "@/browser-voice/AccountPanel";
import { CapabilitiesPanel } from "@/browser-voice/CapabilitiesPanel";
import { ConnectionsPanel } from "@/browser-voice/ConnectionsPanel";
import { MemoryPanel } from "@/browser-voice/MemoryPanel";
import { DocumentsPanel } from "@/browser-voice/DocumentsPanel";
import { SettingsPanel } from "@/browser-voice/SettingsPanel";
import { BrowserWorkspaceFileBrowser } from "@/browser-voice/BrowserWorkspaceFileBrowser";
import { PluginImportDialogHost } from "@/browser-voice/PluginImportDialogHost";
import { NotificationsMenu } from "@/browser-voice/NotificationsMenu";
import {
  localApi,
  type LocalUser,
  type PasswordMode,
  type RecoveryCredential,
  type A2AConnection,
  type A2ANotification,
} from "@/browser-voice/localApi";
import {
  BrowserVoiceFutureNavigation,
  BrowserVoiceConnectionsIcon,
  BrowserVoiceMicrophoneIcon,
  browserVoiceAccountInitials,
  type BrowserVoiceDestination,
} from "@/browser-voice/presentation/BrowserVoiceIcons";

type VoiceState = "idle" | "connecting" | "live" | "responding" | "error";
type OnboardingStep = "name" | "hello" | "experience" | "credentials";

export function BrowserVoiceApp() {
  const [onboardingDraft] = useState(readOnboardingDraft);
  const [ready, setReady] = useState(false);
  const [setupComplete, setSetupComplete] = useState(false);
  const [user, setUser] = useState<LocalUser | null>(null);
  const [destination, setDestination] =
    useState<BrowserVoiceDestination>(() => {
      const query = new URLSearchParams(window.location.search);
      return query.has("memoryPairing") ? "memory" : query.has("providerOAuth") ? "connections" : "home";
    });
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [statusText, setStatusText] = useState("Touch to Start");
  const [subStatus, setSubStatus] = useState("Press to start a voice session");
  const [error, setError] = useState<string | null>(null);
  const [recovery, setRecovery] = useState<RecoveryCredential | null>(null);
  const [optionalAccounts, setOptionalAccounts] = useState(false);
  const [aiConfiguration, setAiConfiguration] = useState(false);
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
  const peerRef = useRef<RTCPeerConnection | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const channelRef = useRef<RTCDataChannel | null>(null);
  const websocketRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const audioSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const playbackAtRef = useRef(0);
  const providerProtocolRef = useRef("openai-realtime");
  const sendProviderEventRef = useRef<((event: Record<string, unknown>) => void) | null>(null);
  const pendingConnectGreetingRef = useRef<Record<string, unknown> | null>(null);
  const awaitingInitialSessionUpdateRef = useRef(false);
  const voiceSessionIdRef = useRef<string | null>(null);
  const transcriptEntryIndexRef = useRef(0);
  const pendingTranscriptWritesRef = useRef<Promise<unknown>[]>([]);
  const assistantDraftRef = useRef("");
  const lastUserUtteranceRef = useRef<{ text: string; index: number } | null>(
    null,
  );
  const toolCallQueueRef = useRef<Promise<void>>(Promise.resolve());
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null);

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
    if (setupComplete || recovery) return;
    sessionStorage.setItem("resono_vault_onboarding", JSON.stringify({ name, experience, step: onboardingStep }));
  }, [experience, name, onboardingStep, recovery, setupComplete]);

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
    const newPassword = String(
      new FormData(event.currentTarget).get("newPassword") || "",
    );
    try {
      await localApi.changePassword(password, newPassword);
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

  async function toggleVoice() {
    if (voiceState === "connecting") return;
    if (voiceState === "live" || voiceState === "responding") {
      await closeVoice(true);
      return;
    }
    setError(null);
    setVoiceState("connecting");
    setStatusText("Opening voice session");
    setSubStatus("Connecting to Voice…");
    assistantDraftRef.current = "";
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;
      const catalog = await localApi.providers().catch(async () => {
        const fallback = await localApi.voiceProvider("openai");
        return { selectedProviderKey: "openai", items: [{ ...fallback, connectionMode: "webrtc" as const }] };
      });
      const provider = catalog.items.find((item) => item.providerKey === catalog.selectedProviderKey);
      if (!provider) throw new Error("Select an AI provider in Connections first.");
      if (!provider.configured)
        throw new Error(
          "Configure a local Voice provider in Connections first.",
        );
      let preparedPeer: RTCPeerConnection | null = null;
      let preparedChannel: RTCDataChannel | null = null;
      let offerSdp: string | undefined;
      if ((provider.connectionMode ?? "webrtc") === "webrtc") {
        const negotiatedChannel = provider.negotiatedDataChannel ?? false;
        preparedPeer = new RTCPeerConnection();
        peerRef.current = preparedPeer;
        for (const track of stream.getTracks()) preparedPeer.addTrack(track, stream);
        preparedPeer.ontrack = (event) => {
          if (remoteAudioRef.current) remoteAudioRef.current.srcObject = event.streams[0];
        };
        preparedChannel = preparedPeer.createDataChannel(
          "oai-events",
          negotiatedChannel ? { negotiated: true, id: provider.dataChannelId ?? 0 } : undefined,
        );
        channelRef.current = preparedChannel;
        sendProviderEventRef.current = (event) => preparedChannel?.send(JSON.stringify(event));
        preparedChannel.onmessage = (event) => receiveRealtimeEvent(String(event.data));
        if (negotiatedChannel) {
          offerSdp = await collectWebRtcOffer(preparedPeer);
        } else {
          const offer = await preparedPeer.createOffer();
          await preparedPeer.setLocalDescription(offer);
          await waitForIceGathering(preparedPeer);
          if (provider.authMethod === "chatgpt_oauth")
            offerSdp = preparedPeer.localDescription?.sdp;
        }
      }
      const started = await localApi.startVoice({
        providerKey: provider.providerKey,
        modelKey: provider.modelKey,
        connectionMode: provider.connectionMode ?? "webrtc",
        voice: provider.voice,
        offerSdp,
      });
      voiceSessionIdRef.current = started.voiceRealtimeSessionId;
      transcriptEntryIndexRef.current = 0;
      pendingTranscriptWritesRef.current = [];
      lastUserUtteranceRef.current = null;
      toolCallQueueRef.current = Promise.resolve();
      providerProtocolRef.current = started.protocol;
      if (started.connectionMode === "provider-websocket") {
        await openProviderWebSocket(started, stream);
        return;
      }
      const peer = preparedPeer;
      const channel = preparedChannel;
      if (!peer || !channel) throw new Error("Voice WebRTC could not be prepared.");
      let answer = started.sdpAnswer;
      if (!answer && started.clientSecret) {
        const response = await fetch(
          "https://api.openai.com/v1/realtime/calls",
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${started.clientSecret}`,
              "Content-Type": "application/sdp",
            },
            body: peer.localDescription?.sdp ?? "",
          },
        );
        if (!response.ok)
          throw new Error(
            "The configured Voice provider rejected the session.",
          );
        answer = await response.text();
      }
      if (!answer)
        throw new Error("The Voice provider did not return a WebRTC answer.");
      await peer.setRemoteDescription({ type: "answer", sdp: answer });
      channel.onopen = () => {
        pendingConnectGreetingRef.current = started.connectGreetingEvent;
        if (started.sessionUpdate && Object.keys(started.sessionUpdate).length > 0) {
          awaitingInitialSessionUpdateRef.current = true;
          channel.send(JSON.stringify(started.sessionUpdate));
        } else {
          sendConnectGreeting();
        }
        setVoiceState("live");
        setStatusText("Listening");
        setSubStatus("I’m listening");
      };
    } catch (caught) {
      await closeVoice(voiceSessionIdRef.current !== null);
      setVoiceState("error");
      setStatusText("Voice unavailable");
      setSubStatus(voiceStartErrorMessage(caught));
      setError(null);
    }
  }

  async function openProviderWebSocket(
    started: Awaited<ReturnType<typeof localApi.startVoice>>, stream: MediaStream,
  ) {
    if (!started.websocketUrl || !started.clientSecret)
      throw new Error("The selected Voice provider did not return a browser connection.");
    const url = started.protocol === "google-live-bidi"
      ? `${started.websocketUrl}?access_token=${encodeURIComponent(started.clientSecret)}`
      : started.websocketUrl;
    const socket = started.websocketProtocol
      ? new WebSocket(url, [started.websocketProtocol]) : new WebSocket(url);
    websocketRef.current = socket;
    socket.onmessage = (message) => receiveProviderWebSocketEvent(String(message.data), started.outputSampleRate ?? 24_000);
    await new Promise<void>((resolve, reject) => {
      socket.onopen = () => {
        sendProviderEventRef.current = (event) => socket.send(JSON.stringify(event));
        if (started.sessionUpdate) socket.send(JSON.stringify(started.sessionUpdate));
        startPcmCapture(stream, started.inputSampleRate ?? 24_000, started.protocol, socket);
        setVoiceState("live"); setStatusText("Listening"); setSubStatus("I’m listening"); resolve();
      };
      socket.onerror = () => reject(new Error("The selected Voice provider connection failed."));
    });
  }

  function startPcmCapture(stream: MediaStream, targetRate: number, protocol: string, socket: WebSocket) {
    const context = new AudioContext();
    const source = context.createMediaStreamSource(stream);
    const processor = context.createScriptProcessor(4096, 1, 1);
    audioContextRef.current = context; audioSourceRef.current = source; audioProcessorRef.current = processor;
    processor.onaudioprocess = (event) => {
      if (socket.readyState !== WebSocket.OPEN) return;
      const pcm = floatToPcm16(resampleAudio(event.inputBuffer.getChannelData(0), context.sampleRate, targetRate));
      const audio = bytesToBase64(new Uint8Array(pcm.buffer));
      const payload = protocol === "google-live-bidi"
        ? { realtimeInput: { audio: { data: audio, mimeType: `audio/pcm;rate=${targetRate}` } } }
        : { type: "input_audio_buffer.append", audio };
      socket.send(JSON.stringify(payload));
    };
    source.connect(processor); processor.connect(context.destination);
  }

  function receiveProviderWebSocketEvent(raw: string, outputRate: number) {
    try {
      const event = JSON.parse(raw) as Record<string, unknown>;
      if (providerProtocolRef.current === "google-live-bidi") {
        const content = event.serverContent as Record<string, unknown> | undefined;
        const modelTurn = content?.modelTurn as { parts?: Array<Record<string, unknown>> } | undefined;
        for (const part of modelTurn?.parts ?? []) {
          const inline = part.inlineData as Record<string, unknown> | undefined;
          if (typeof inline?.data === "string") playPcmAudio(inline.data, outputRate);
        }
        const input = content?.inputTranscription as Record<string, unknown> | undefined;
        const output = content?.outputTranscription as Record<string, unknown> | undefined;
        if (typeof input?.text === "string") captureNormalizedTranscript("user", input.text, "gemini.input_transcription", event);
        if (typeof output?.text === "string") captureNormalizedTranscript("assistant", output.text, "gemini.output_transcription", event);
        const toolCall = event.toolCall as { functionCalls?: Array<Record<string, unknown>> } | undefined;
        for (const call of toolCall?.functionCalls ?? []) void executeVoiceToolCall({
          type: "gemini.tool_call", name: call.name, call_id: call.id, arguments: JSON.stringify(call.args ?? {}),
        });
        if (content?.turnComplete) { setVoiceState("live"); setStatusText("Listening"); }
        return;
      }
      if (event.type === "response.output_audio.delta" && typeof event.delta === "string") playPcmAudio(event.delta, outputRate);
      receiveRealtimeEvent(raw);
    } catch { /* provider noise is ignored */ }
  }

  function captureNormalizedTranscript(role: "user" | "assistant", text: string, eventType: string, payload: Record<string, unknown>) {
    const sessionId = voiceSessionIdRef.current;
    if (!sessionId || !text.trim()) return;
    setSubStatus(text);
    const entryIndex = transcriptEntryIndexRef.current++;
    if (role === "user") lastUserUtteranceRef.current = { text, index: entryIndex };
    const write = localApi.captureVoiceEvent(sessionId, {
      providerEventId: crypto.randomUUID(), eventType, role, transcriptText: text,
      transcriptEntryIndex: entryIndex, providerPayload: payload,
    });
    pendingTranscriptWritesRef.current.push(write);
  }

  function playPcmAudio(encoded: string, sampleRate: number) {
    const bytes = base64ToBytes(encoded);
    const samples = new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 2));
    const context = audioContextRef.current ?? new AudioContext();
    audioContextRef.current = context;
    const buffer = context.createBuffer(1, samples.length, sampleRate);
    const channel = buffer.getChannelData(0);
    for (let index = 0; index < samples.length; index += 1) channel[index] = samples[index] / 32768;
    const source = context.createBufferSource(); source.buffer = buffer; source.connect(context.destination);
    const at = Math.max(context.currentTime, playbackAtRef.current); source.start(at); playbackAtRef.current = at + buffer.duration;
  }

  function receiveRealtimeEvent(raw: string) {
    try {
      const event = JSON.parse(raw) as Record<string, unknown>;
      const type = String(event.type || "");
      if (type === "session.updated" && awaitingInitialSessionUpdateRef.current)
        sendConnectGreeting();
      if (type === "response.function_call_arguments.done") {
        toolCallQueueRef.current = toolCallQueueRef.current
          .then(() => executeVoiceToolCall(event))
          .catch((caught) => {
            setError(
              caught instanceof Error
                ? caught.message
                : "Voice tool call could not be completed.",
            );
          });
      }
      if (type === "input_audio_buffer.speech_started") {
        setVoiceState("live");
        setStatusText("Listening");
        setSubStatus("Listening…");
      }
      if (type === "input_audio_buffer.speech_stopped") {
        setVoiceState("responding");
        setStatusText("Responding");
        setSubStatus("Generating reply…");
      }
      if (type === "response.created") {
        setVoiceState("responding");
        setStatusText("Responding");
        setSubStatus("Generating reply…");
      }
      if (type === "response.done") {
        setVoiceState("live");
        setStatusText("Listening");
      }
      const userFinal =
        type === "conversation.item.input_audio_transcription.completed" ||
        type === "conversation.item.input_audio_transcript.completed";
      const assistantFinal =
        type === "response.audio_transcript.done" ||
        type === "response.output_audio_transcript.done";
      const assistantDelta =
        type === "response.audio_transcript.delta" ||
        type === "response.output_audio_transcript.delta";
      if (assistantDelta) {
        assistantDraftRef.current +=
          typeof event.delta === "string" ? event.delta : "";
        if (assistantDraftRef.current) {
          setVoiceState("responding");
          setStatusText("Responding");
          setSubStatus(assistantDraftRef.current);
        }
      }
      const role = userFinal ? "user" : "assistant";
      const text =
        typeof event.transcript === "string" ? event.transcript : null;
      if (text && (userFinal || assistantFinal)) {
        setSubStatus(text);
        if (assistantFinal) assistantDraftRef.current = "";
        const sessionId = voiceSessionIdRef.current;
        if (sessionId) {
          const entryIndex = transcriptEntryIndexRef.current++;
          if (userFinal)
            lastUserUtteranceRef.current = { text, index: entryIndex };
          const write = localApi.captureVoiceEvent(sessionId, {
            providerEventId:
              typeof event.event_id === "string"
                ? event.event_id
                : crypto.randomUUID(),
            eventType: type,
            role,
            transcriptText: text,
            transcriptEntryIndex: entryIndex,
            providerPayload: event,
          });
          pendingTranscriptWritesRef.current.push(write);
          void write.catch((caught) =>
            setError(
              caught instanceof Error
                ? caught.message
                : "Voice transcript could not be saved.",
            ),
          );
        }
      }
    } catch {
      /* provider noise is ignored without exposing it */
    }
  }

  function sendConnectGreeting() {
    const greeting = pendingConnectGreetingRef.current;
    const send = sendProviderEventRef.current;
    if (!greeting || !send) return;
    pendingConnectGreetingRef.current = null;
    awaitingInitialSessionUpdateRef.current = false;
    send(greeting);
  }

  async function executeVoiceToolCall(event: Record<string, unknown>) {
    const sessionId = voiceSessionIdRef.current;
    const send = sendProviderEventRef.current;
    const name = typeof event.name === "string" ? event.name : "";
    const callId = typeof event.call_id === "string" ? event.call_id : "";
    if (!sessionId || !send || !name || !callId)
      return;
    let args: Record<string, unknown> = {};
    if (typeof event.arguments === "string" && event.arguments.trim()) {
      const parsed = JSON.parse(event.arguments) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
        throw new Error("Voice produced invalid tool arguments.");
      args = parsed as Record<string, unknown>;
    }
    const utterance = lastUserUtteranceRef.current;
    const result = await localApi.callVoiceTool(sessionId, {
      name,
      toolCallId: callId,
      arguments: args,
      userUtterance: utterance?.text,
      userUtteranceId: utterance?.index,
    });
    if (result.resonoSessionUpdate) send(result.resonoSessionUpdate);
    if (providerProtocolRef.current === "google-live-bidi") {
      send({ toolResponse: { functionResponses: [{ id: callId, name, response: result }] } });
      return;
    }
    send({
        type: "conversation.item.create",
        item: {
          type: "function_call_output",
          call_id: callId,
          output: JSON.stringify(result),
        },
      });
    send({ type: "response.create" });
  }

  async function closeVoice(notifyServer: boolean) {
    const id = voiceSessionIdRef.current;
    voiceSessionIdRef.current = null;
    channelRef.current?.close();
    channelRef.current = null;
    peerRef.current?.close();
    peerRef.current = null;
    websocketRef.current?.close(); websocketRef.current = null;
    pendingConnectGreetingRef.current = null;
    awaitingInitialSessionUpdateRef.current = false;
    audioProcessorRef.current?.disconnect(); audioProcessorRef.current = null;
    audioSourceRef.current?.disconnect(); audioSourceRef.current = null;
    if (audioContextRef.current) void audioContextRef.current.close();
    audioContextRef.current = null; playbackAtRef.current = 0; sendProviderEventRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (notifyServer && id) {
      const pending = pendingTranscriptWritesRef.current.splice(0);
      await Promise.allSettled(pending);
      try {
        await localApi.closeVoice(id);
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "Voice learning could not be finalized.",
        );
      }
    }
    setVoiceState("idle");
    setStatusText("Touch to Start");
    setSubStatus("Press to start a voice session");
    assistantDraftRef.current = "";
    lastUserUtteranceRef.current = null;
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

  const shellTitle =
    destination === "capabilities"
      ? "Capabilities"
      : destination === "documents"
        ? "Documents"
      : destination === "workspace"
        ? "Your workspace"
      : destination === "memory"
        ? "Memory"
      : destination === "agent2agent"
        ? "Agent2Agent"
      : destination === "connections"
        ? "Connections"
        : destination === "settings"
          ? "Settings"
        : destination === "account"
          ? "Account"
          : "Voice";
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
        className={`browser-voice-card ${activeUser ? `browser-voice-app-frame${destination === "workspace" ? " is-workspace-page" : ""}` : "is-login-page"}`}
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
                  disabled={submitting || !experience}
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
            ) : recovery ? (
              <RecoveryPanel
                recovery={recovery}
                onContinue={() => {
                  setRecovery(null);
                  setOptionalAccounts(true);
                }}
              />
            ) : optionalAccounts ? (
              <OptionalAccountsPanel
                onDone={() => {
                  setOptionalAccounts(false);
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
          <div className={`browser-voice-content-surface ${destination === "workspace" ? "is-workspace" : "is-management"}`}>
            {destination === "home" ? (
              <HomeVoice
                voiceState={voiceState}
                statusText={statusText}
                subStatus={subStatus}
                isLive={isLive}
                onToggle={() => void toggleVoice()}
              />
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
                <SettingsPanel user={activeUser} />
              </div>
            ) : null}
            {destination === "workspace" ? (
              <div className="browser-voice-management-page browser-voice-workspace-page">
                <header className="browser-voice-page-heading">
                  <div>
                    <h2>Your workspace</h2>
                    <p>Private files from your Vault, available before or during voice.</p>
                  </div>
                </header>
                <BrowserWorkspaceFileBrowser initiallyExpanded />
              </div>
            ) : null}
            {destination === "agent2agent" ? (
              <div className="browser-voice-management-page">
                <Agent2AgentPanel />
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
        {activeUser ? (
          <BrowserVoiceFutureNavigation
            activeDestination={destination}
            onNavigate={setDestination}
            placement="mobile"
          />
        ) : null}
      </section>
      {activeUser ? <PluginImportDialogHost /> : null}
    </main>
  );
}

function resampleAudio(input: Float32Array, sourceRate: number, targetRate: number): Float32Array {
  if (sourceRate === targetRate) return input;
  const ratio = sourceRate / targetRate;
  const output = new Float32Array(Math.max(1, Math.round(input.length / ratio)));
  for (let index = 0; index < output.length; index += 1) {
    const position = index * ratio;
    const left = Math.floor(position);
    const right = Math.min(input.length - 1, left + 1);
    const weight = position - left;
    output[index] = input[left] * (1 - weight) + input[right] * weight;
  }
  return output;
}

function floatToPcm16(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length);
  for (let index = 0; index < input.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, input[index]));
    output[index] = sample < 0 ? sample * 32768 : sample * 32767;
  }
  return output;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let index = 0; index < bytes.length; index += 1) binary += String.fromCharCode(bytes[index]);
  return btoa(binary);
}

function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

function HomeVoice({
  voiceState,
  statusText,
  subStatus,
  isLive,
  onToggle,
}: {
  voiceState: VoiceState;
  statusText: string;
  subStatus: string;
  isLive: boolean;
  onToggle: () => void;
}) {
  const responseTextRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    const responseText = responseTextRef.current;
    if (responseText) responseText.scrollTop = responseText.scrollHeight;
  }, [subStatus]);

  return (
    <>
      <section
        aria-label="Connection status"
        className="browser-voice-health-row"
      >
        <div className="browser-voice-health-status is-green" role="status">
          <span aria-hidden="true" />
          <span>
            <strong>Runtime</strong>
            <small>Ready</small>
          </span>
        </div>
        <div className="browser-voice-health-status is-green" role="status">
          <span aria-hidden="true" />
          <span>
            <strong>Local Vault</strong>
            <small>Connected</small>
          </span>
        </div>
        <div className="browser-voice-health-status is-green" role="status">
          <span aria-hidden="true" />
          <span>
            <strong>Privacy</strong>
            <small>Local authority</small>
          </span>
        </div>
      </section>
      <div className="browser-voice-pages">
        <section className="browser-voice-console browser-voice-landing">
          <div
            className={`browser-voice-voice-center is-${voiceState} ${isLive ? "is-live" : ""}`}
          >
            <button
              aria-label={
                isLive
                  ? "End voice session"
                  : voiceState === "error"
                    ? "Try voice session again"
                    : "Start voice session"
              }
              className={`browser-voice-toggle browser-voice-microphone is-${voiceState}`}
              onClick={onToggle}
              type="button"
            >
              <BrowserVoiceMicrophoneIcon className="browser-voice-microphone-icon" />
            </button>
            <div className="browser-voice-voice-copy" aria-live="polite">
              <strong>
                {voiceState === "idle" ? "Touch to Start" : statusText}
              </strong>
              <span>
                {voiceState === "idle"
                  ? "SESSION: IDLE"
                  : `STATE: ${voiceState.toUpperCase()}`}
              </span>
              <p ref={responseTextRef}>{subStatus}</p>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}

function Agent2AgentPanel() {
  const [connections, setConnections] = useState<A2AConnection[]>([]);
  const [notifications, setNotifications] = useState<A2ANotification[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [selectedActivity, setSelectedActivity] = useState<A2ANotification | null>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const connectDialogRef = useRef<HTMLDialogElement | null>(null);
  const detailDialogRef = useRef<HTMLDialogElement | null>(null);
  const activityDialogRef = useRef<HTMLDialogElement | null>(null);

  useEffect(() => {
    const dialog = connectDialogRef.current;
    if (!dialog) return;
    if (adding && !dialog.open) typeof dialog.showModal === "function" ? dialog.showModal() : dialog.setAttribute("open", "");
    if (!adding && dialog.open) typeof dialog.close === "function" ? dialog.close() : dialog.removeAttribute("open");
  }, [adding]);
  useEffect(() => {
    const dialog = detailDialogRef.current;
    if (!dialog) return;
    if (selectedAgent && !dialog.open) typeof dialog.showModal === "function" ? dialog.showModal() : dialog.setAttribute("open", "");
    if (!selectedAgent && dialog.open) typeof dialog.close === "function" ? dialog.close() : dialog.removeAttribute("open");
  }, [selectedAgent]);
  useEffect(() => {
    const dialog = activityDialogRef.current;
    if (!dialog) return;
    if (selectedActivity && !dialog.open) typeof dialog.showModal === "function" ? dialog.showModal() : dialog.setAttribute("open", "");
    if (!selectedActivity && dialog.open) typeof dialog.close === "function" ? dialog.close() : dialog.removeAttribute("open");
  }, [selectedActivity]);

  async function refresh() {
    try {
      const [connected, activity] = await Promise.all([
        localApi.a2aConnections(), localApi.a2aNotifications(),
      ]);
      setConnections(Array.isArray(connected?.items) ? connected.items : []);
      setNotifications(Array.isArray(activity?.items) ? activity.items : []);
      setError(null);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Agent2Agent could not be loaded."); }
  }
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, []);
  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget; const data = new FormData(form);
    try {
      await localApi.connectA2A({ displayName: String(data.get("displayName") || "").trim(), cardUrl: String(data.get("cardUrl") || "").trim(), token: String(data.get("token") || "") });
      form.reset(); setAdding(false); await refresh();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "External agent could not be connected."); }
  }
  async function remove(connectionId: string) {
    try { await localApi.removeA2A(connectionId); await refresh(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "External agent could not be removed."); }
  }
  const agents = connections.map((connection) => ({ key: `a2a-${connection.connectionId}`, connection }));
  const selected = agents.find((item) => item.key === selectedAgent);
  const selectedCard = selected?.connection?.agentCard;
  return <section aria-labelledby="agent2agent-title" className="browser-voice-connections browser-voice-a2a">
    <header className="browser-voice-management-heading"><div><span className="browser-voice-eyebrow-label">Agent network</span><h2 id="agent2agent-title">External agents</h2><p>Agents available to Voice and the Background Agent through the A2A standard.</p></div></header>
    <section className="browser-voice-management-section">
      <div className="browser-voice-section-head"><div><span className="browser-voice-eyebrow-label">Connections</span><h3>Agent connections</h3><p>Select an agent to view its Agent Card, access, skills, and connection details.</p></div><button className="browser-voice-submit" onClick={() => setAdding(true)} type="button">Connect agent</button></div>
      {agents.map((item) => <button className="browser-voice-connection-row browser-voice-a2a-standard-row" key={item.key} onClick={() => setSelectedAgent(item.key)} type="button"><span className="browser-voice-connection-mark"><BrowserVoiceConnectionsIcon /></span><span><strong>{item.connection.displayName}</strong><small>A2A connected · Voice and Background Agent available</small></span><span className="browser-voice-state is-ready">Connected</span></button>)}
      {!agents.length ? <p className="browser-voice-management-empty">No external agents are connected.</p> : null}
    </section>
    <section className="browser-voice-management-section">
      <div className="browser-voice-section-head"><div><span className="browser-voice-eyebrow-label">Activity</span><h3>Recent agent work</h3><p>The five most recent completed requests.</p></div></div>
      {notifications.map((item) => <button className="browser-voice-connection-row browser-voice-a2a-activity-row" key={item.taskId} onClick={() => setSelectedActivity(item)} type="button"><span className="browser-voice-connection-mark"><BrowserVoiceConnectionsIcon /></span><span><strong>{item.agentName}</strong><small>{item.summary || "Completed without a summary."}</small></span><span className="browser-voice-state is-ready">Completed</span></button>)}
      {!notifications.length ? <p className="browser-voice-management-empty">No completed agent work yet.</p> : null}
    </section>
    <dialog aria-labelledby="a2a-connect-title" className="browser-voice-modal" onCancel={() => setAdding(false)} onClose={() => setAdding(false)} ref={connectDialogRef}><form onSubmit={(event) => void connect(event)}><div className="browser-voice-modal-head"><div><span className="browser-voice-eyebrow-label">Agent connection</span><h2 id="a2a-connect-title">Connect external agent</h2></div><button aria-label="Close agent connection" className="browser-voice-modal-close" onClick={() => setAdding(false)} type="button">×</button></div><div className="browser-voice-modal-fields"><label><span>Name</span><input name="displayName" placeholder="Hermes" required /></label><label><span>Agent Card URL</span><input name="cardUrl" placeholder="https://agent.example/.well-known/agent-card.json" required type="url" /></label><label className="browser-voice-modal-wide"><span>Bearer token (if required)</span><input autoComplete="off" name="token" type="password" /></label></div><p className="browser-voice-form-note">Vault validates the Agent Card and encrypts the credential locally.</p><div className="browser-voice-modal-actions"><button className="browser-voice-pill" onClick={() => setAdding(false)} type="button">Cancel</button><button className="browser-voice-submit" type="submit">Connect agent</button></div></form></dialog>
    <dialog aria-labelledby="a2a-detail-title" className="browser-voice-modal" onCancel={() => setSelectedAgent(null)} onClose={() => setSelectedAgent(null)} ref={detailDialogRef}>{selected ? <div className="browser-voice-a2a-dialog"><div className="browser-voice-modal-head"><div><span className="browser-voice-eyebrow-label">A2A Agent Card</span><h2 id="a2a-detail-title">{selected.connection.displayName}</h2></div><button aria-label="Close agent details" className="browser-voice-modal-close" onClick={() => setSelectedAgent(null)} type="button">×</button></div><p>{selectedCard?.description || "Connected external agent."}</p><dl className="browser-voice-a2a-facts"><div><dt>A2A</dt><dd>Connected</dd></div><div><dt>Voice</dt><dd>Available</dd></div><div><dt>Background Agent</dt><dd>Available</dd></div><div><dt>Protocol</dt><dd>{`${selectedCard?.supportedInterfaces?.[0]?.protocolBinding || "JSONRPC"} ${selectedCard?.supportedInterfaces?.[0]?.protocolVersion || "1.0"}`}</dd></div>{selectedCard?.version ? <div><dt>Version</dt><dd>{selectedCard.version}</dd></div> : null}<div className="is-wide"><dt>Agent Card</dt><dd>{selected.connection.cardUrl}</dd></div></dl>{selectedCard?.skills?.length ? <div className="browser-voice-a2a-skills"><h5>Skills</h5><div>{selectedCard.skills.map((skill, index) => <span key={skill.id || `${skill.name}-${index}`}>{skill.name || skill.id}</span>)}</div></div> : null}<div className="browser-voice-modal-actions"><button className="browser-voice-account-danger" onClick={() => { setSelectedAgent(null); void remove(selected.connection.connectionId); }} type="button">Remove connection</button><button className="browser-voice-pill" onClick={() => setSelectedAgent(null)} type="button">Close</button></div></div> : null}</dialog>
    <dialog aria-labelledby="a2a-activity-title" className="browser-voice-modal" onCancel={() => setSelectedActivity(null)} onClose={() => setSelectedActivity(null)} ref={activityDialogRef}>{selectedActivity ? <div className="browser-voice-a2a-dialog"><div className="browser-voice-modal-head"><div><span className="browser-voice-eyebrow-label">Completed agent work</span><h2 id="a2a-activity-title">{selectedActivity.agentName}</h2></div><button aria-label="Close activity details" className="browser-voice-modal-close" onClick={() => setSelectedActivity(null)} type="button">×</button></div><dl className="browser-voice-a2a-facts"><div><dt>Requested by</dt><dd>{selectedActivity.ownerKind === "voice" ? "Voice" : "Background Agent"}</dd></div><div><dt>Completed</dt><dd>{selectedActivity.completedAt ? new Date(selectedActivity.completedAt).toLocaleString() : "Completed"}</dd></div></dl><div className="browser-voice-a2a-review"><h5>Summary</h5><p>{selectedActivity.summary || "Completed without a summary."}</p></div><div className="browser-voice-modal-actions"><button className="browser-voice-pill" onClick={() => setSelectedActivity(null)} type="button">Close</button></div></div> : null}</dialog>
    {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
  </section>;
}

function RecoveryPanel({
  recovery,
  onContinue,
}: {
  recovery: RecoveryCredential;
  onContinue: () => void;
}) {
  return (
    <div className="browser-voice-management-message" role="status">
      <strong>Save your local recovery login now.</strong>
      <p>
        Username: <code>{recovery.username}</code>
      </p>
      <p>
        Password: <code>{recovery.generatedPassword}</code>
      </p>
      <p>This is shown once and never sent to ReSono Labs.</p>
      <button
        className="browser-voice-submit"
        onClick={onContinue}
        type="button"
      >
        I saved it
      </button>
    </div>
  );
}

function OptionalAccountsPanel({ onDone }: { onDone: () => void }) {
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

function OnboardingAiConfiguration({ onDone }: { onDone: () => void }) {
  const [configuring, setConfiguring] = useState(false);
  const [providers, setProviders] = useState<Array<{ providerKey: string; displayName?: string; modelKey: string; backgroundModelKey: string; voice: string; voices?: string[]; voiceModels?: string[] }>>([]);
  const [providerKey, setProviderKey] = useState("openai");
  const [apiKey, setApiKey] = useState("");
  const [modelKey, setModelKey] = useState("gpt-realtime-2.1");
  const [backgroundModelKey, setBackgroundModelKey] = useState("gpt-5.6-sol");
  const [voice, setVoice] = useState("alloy");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!configuring) return;
    void localApi.providers().then((catalog) => setProviders(catalog.items)).catch(() => undefined);
  }, [configuring]);

  function chooseProvider(nextKey: string) {
    setProviderKey(nextKey);
    const next = providers.find((item) => item.providerKey === nextKey);
    if (!next) return;
    setModelKey(next.modelKey); setBackgroundModelKey(next.backgroundModelKey); setVoice(next.voice);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      await localApi.setVoiceProvider(providerKey, {
        apiKey,
        modelKey,
        backgroundModelKey,
        voice,
      });
      setApiKey("");
      setSaved(true);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "AI provider could not be saved.",
      );
    }
  }

  return (
    <div className="browser-voice-onboarding-choice">
      {!configuring ? <><p>Would you like to connect an AI provider now? The encrypted key will be shared for use by all active Vault users, while only the master can change it.</p><div className="browser-voice-choice-actions"><button className="browser-voice-submit" onClick={() => setConfiguring(true)} type="button">Connect and share provider</button><button className="browser-voice-pill browser-voice-pill-muted" onClick={onDone} type="button">Not now</button></div></> : null}
      {configuring ? <form
        className="browser-voice-form browser-voice-onboarding-later-form"
        onSubmit={(event) => void save(event)}
      >
        <label>
          <span>AI provider</span>
          <select aria-label="AI provider" onChange={(event) => chooseProvider(event.target.value)} value={providerKey}>
            {(providers.length ? providers : [{ providerKey: "openai", displayName: "OpenAI", modelKey, backgroundModelKey, voice }]).map((item) => <option key={item.providerKey} value={item.providerKey}>{item.displayName ?? item.providerKey}</option>)}
          </select>
        </label>
        <label>
          <span>{providers.find((item) => item.providerKey === providerKey)?.displayName ?? "OpenAI"} API key</span>
          <input
            autoComplete="off"
            onChange={(event) => setApiKey(event.target.value)}
            required
            type="password"
            value={apiKey}
          />
        </label>
        <label>
          <span>Realtime model</span>
          {providers.find((item) => item.providerKey === providerKey)?.voiceModels?.length ? <select onChange={(event) => setModelKey(event.target.value)} value={modelKey}>{providers.find((item) => item.providerKey === providerKey)?.voiceModels?.map((item) => <option key={item} value={item}>{item}</option>)}</select> : <input
            onChange={(event) => setModelKey(event.target.value)}
            required
            value={modelKey}
          />}
        </label>
        <label>
          <span>Background model</span>
          <input
            onChange={(event) => setBackgroundModelKey(event.target.value)}
            required
            value={backgroundModelKey}
          />
        </label>
        <label>
          <span>Voice</span>
          {providers.find((item) => item.providerKey === providerKey)?.voices?.length ? <select onChange={(event) => setVoice(event.target.value)} value={voice}>{providers.find((item) => item.providerKey === providerKey)?.voices?.map((item) => <option key={item} value={item}>{item}</option>)}</select> : <input
            onChange={(event) => setVoice(event.target.value)}
            required
            value={voice}
          />}
        </label>
        <p className="browser-voice-form-note">This provider runs Voice and background AI work. Embeddings remain separately controlled.</p>
        {saved ? <div className="browser-voice-management-message" role="status">AI configuration saved locally.</div> : null}
        {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
        <div className="browser-voice-onboarding-actions">
          {!saved ? <button className="browser-voice-submit" type="submit">Save AI configuration</button> : null}
          <button className={saved ? "browser-voice-submit" : "browser-voice-pill browser-voice-pill-muted"} onClick={onDone} type="button">{saved ? "Enter Vault" : "Skip for now"}</button>
        </div>
      </form> : null}
    </div>
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

export function voiceStartErrorMessage(caught: unknown) {
  const errorName =
    typeof caught === "object" && caught !== null && "name" in caught
      ? String(caught.name)
      : "";
  if (errorName === "NotFoundError")
    return "No microphone was found. Connect or enable a microphone, then try again.";
  if (errorName === "NotAllowedError" || errorName === "SecurityError")
    return "Microphone access is blocked. Allow microphone access for Vault, then try again.";
  if (errorName === "NotReadableError" || errorName === "AbortError")
    return "The microphone is unavailable or already in use. Close other audio apps, then try again.";
  return caught instanceof Error ? caught.message : "Voice could not start.";
}

function normalizeWebRtcSdp(sdp: string) {
  const lines = sdp.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n").map((line) => line.trimEnd());
  while (lines.length && !lines[0]) lines.shift();
  while (lines.length && !lines[lines.length - 1]) lines.pop();
  return `${lines.join("\r\n")}\r\n`;
}

async function collectWebRtcOffer(peer: RTCPeerConnection) {
  const offer = await peer.createOffer();
  await peer.setLocalDescription(offer);
  await waitForIceGathering(peer);
  await new Promise<void>((resolve) => window.setTimeout(resolve, 300));
  const sdp = peer.localDescription?.sdp;
  if (!sdp?.startsWith("v=0")) throw new Error("Voice WebRTC offer could not be prepared.");
  const normalized = normalizeWebRtcSdp(sdp);
  if (!/\nm=audio /.test(normalized)) throw new Error("Voice WebRTC offer is missing audio.");
  return normalized;
}

function waitForIceGathering(peer: RTCPeerConnection) {
  if (peer.iceGatheringState === "complete") return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    const timeout = window.setTimeout(() => finish(new Error("Voice network setup timed out.")), 10_000);
    const finish = (error?: Error) => {
      clearTimeout(timeout);
      peer.removeEventListener("icegatheringstatechange", onGathering);
      peer.removeEventListener("icecandidate", onCandidate);
      if (error) reject(error);
      else resolve();
    };
    const onGathering = () => {
      if (peer.iceGatheringState === "complete") finish();
    };
    const onCandidate = (event: RTCPeerConnectionIceEvent) => {
      if (!event.candidate) finish();
    };
    peer.addEventListener("icegatheringstatechange", onGathering);
    peer.addEventListener("icecandidate", onCandidate);
  });
}
