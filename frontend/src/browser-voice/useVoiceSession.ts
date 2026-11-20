import { useEffect, useRef, useState } from "react";
import type { Preparation } from "./conversation/api";
import { localApi } from "@/browser-voice/localApi";
import { normalizeWorkspaceToolArguments } from "@/browser-voice/workspaceToolArguments";
import { VoiceLivePreparation } from "./voiceLivePreparation";

export type VoiceState = "idle" | "connecting" | "live" | "responding" | "error";

export async function countFailedTranscriptWrites(pending: Promise<unknown>[]): Promise<number> {
  const settled = await Promise.allSettled(pending);
  return settled.filter((result) => result.status === "rejected").length;
}

/** The browser Voice engine: microphone, provider connection, transcript capture and tool calls. */
export function useVoiceSession(setError: (message: string | null) => void) {
  const voicePreparationRef = useRef<VoiceLivePreparation | null>(null);
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [voicePreparation, setVoicePreparation] = useState<Preparation | null>(null);
  const [voiceActivity, setVoiceActivity] = useState<string[]>([]);
  const activityTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  function clearVoiceActivity() {
    if (activityTimerRef.current) clearTimeout(activityTimerRef.current);
    activityTimerRef.current = null;
    setVoiceActivity([]);
  }
  function showVoiceActivity(text: string) {
    if (activityTimerRef.current) clearTimeout(activityTimerRef.current);
    activityTimerRef.current = null;
    setVoiceActivity(items => [...items, text].slice(-20));
  }
  useEffect(() => () => { if (activityTimerRef.current) clearTimeout(activityTimerRef.current); }, []);
  const [statusText, setStatusText] = useState("Touch to Start");
  const [subStatus, setSubStatus] = useState("Press to start a voice session");
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
      // Live memory search needs a live text feed: the dedicated transcription session (API key)
      // or the conversation connection's own transcript events (ChatGPT OAuth).
      // The conversation may run on OAuth while a dedicated API-key transcription session supplies the text.
      const nativeTranscript = !started.liveTranscription && provider.authMethod === "chatgpt_oauth";
      if (provider.providerKey === "openai" && (started.liveTranscription || nativeTranscript)) voicePreparationRef.current = new VoiceLivePreparation(
        started.voiceRealtimeSessionId,event => sendProviderEventRef.current?.(event),
        setVoicePreparation, nativeTranscript);
      clearVoiceActivity();
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
          channel.send(JSON.stringify(voicePreparationRef.current?.sessionUpdate(started.sessionUpdate) ?? started.sessionUpdate));
        } else {
          sendConnectGreeting();
        }
        setVoiceState("live");
        setStatusText("Listening");
        setSubStatus("I’m listening");
      };
      if (started.liveTranscription && voicePreparationRef.current) {
        const preparation = voicePreparationRef.current;
        void preparation.start(stream,waitForIceGathering).catch(() => {
          preparation.stopTranscription(); // The conversation itself is unaffected.
          if (voicePreparationRef.current===preparation)
            setError("Live transcription unavailable; Voice continues without live memory search.");
        });
      }
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
        if (started.sessionUpdate) socket.send(JSON.stringify(voicePreparationRef.current?.sessionUpdate(started.sessionUpdate) ?? started.sessionUpdate));
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
          if (part.thought === true && typeof part.text === "string") showVoiceActivity(part.text);
        }
        const input = content?.inputTranscription as Record<string, unknown> | undefined;
        const output = content?.outputTranscription as Record<string, unknown> | undefined;
        if (typeof input?.text === "string") captureNormalizedTranscript("user", input.text, "gemini.input_transcription", event);
        if (typeof output?.text === "string") captureNormalizedTranscript("assistant", output.text, "gemini.output_transcription", event);
        const toolCall = event.toolCall as { functionCalls?: Array<Record<string, unknown>> } | undefined;
        for (const call of toolCall?.functionCalls ?? []) void executeVoiceToolCall({
          type: "gemini.tool_call", name: call.name, call_id: call.id, arguments: JSON.stringify(call.args ?? {}),
        });
        if (content?.turnComplete) {
          setVoiceState("live"); setStatusText("Listening");
          if (activityTimerRef.current) clearTimeout(activityTimerRef.current);
          activityTimerRef.current = setTimeout(() => setVoiceActivity([]), 4000);
        }
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
    // Observe rejection now, but retain the original promise for close-time
    // acknowledgment. Catching it must not turn failed capture into success.
    void write.catch(() => setError("A transcript update could not be saved."));
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
      if (type === "response.reasoning_summary_text.done" && typeof event.text === "string")
        showVoiceActivity(event.text);
      if (type === "response.done") {
        const response = event.response as { output?: Array<{ type?: string; summary?: Array<{ text?: string }> }> } | undefined;
        for (const item of response?.output ?? [])
          if (item.type === "reasoning") for (const summary of item.summary ?? [])
            if (summary.text) setVoiceActivity(items => items.includes(summary.text!) ? items : [...items, summary.text!].slice(-20));
        if (!(response?.output ?? []).some(item => item.type === "function_call"))
          activityTimerRef.current = setTimeout(() => setVoiceActivity([]), 4000);
      }

      if ((type === "response.done" || type === "response.function_call_arguments.done") && voiceSessionIdRef.current) {
        const write = localApi.captureVoiceEvent(voiceSessionIdRef.current, {
          providerEventId: typeof event.event_id === "string" ? event.event_id : crypto.randomUUID(),
          eventType: type, role: "assistant", providerPayload: event,
        });
        pendingTranscriptWritesRef.current.push(write);
        void write.catch(() => setError("Original response evidence could not be saved."));
      }
      if (type === "session.updated" && awaitingInitialSessionUpdateRef.current)
        sendConnectGreeting();
      if (type === "response.function_call_arguments.done") {
        toolCallQueueRef.current = toolCallQueueRef.current
          .then(() => executeVoiceToolCall(event))
          .catch((caught) => {
            showVoiceActivity("Tool execution failed.");
            activityTimerRef.current = setTimeout(() => setVoiceActivity([]), 4000);
            setError(
              caught instanceof Error
                ? caught.message
                : "Voice tool call could not be completed.",
            );
          });
      }
      if (type === "conversation.item.input_audio_transcription.delta") voicePreparationRef.current?.conversationDelta(event);
      if (type === "input_audio_buffer.speech_started") {
        clearVoiceActivity();
        if (typeof event.item_id === "string") voicePreparationRef.current?.speechStarted(event.item_id);
        setVoiceState("live");
        setStatusText("Listening");
        setSubStatus("Listening…");
      }
      if (type === "input_audio_buffer.speech_stopped") {
        if (typeof event.item_id === "string") voicePreparationRef.current?.speechStopped(event.item_id);
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
          if (userFinal && typeof event.item_id === "string") {
            const preparation=voicePreparationRef.current, item=event.item_id;
            void write.then(() => {
              if (voicePreparationRef.current === preparation) preparation?.completedTranscript(item,text);
            }).catch(() => {});
          }
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
    } else if (event.arguments && typeof event.arguments === "object" && !Array.isArray(event.arguments)) {
      args = event.arguments as Record<string, unknown>;
    }
    showVoiceActivity(`Running ${name}`);
    args = normalizeWorkspaceToolArguments(name, args);
    const utterance = lastUserUtteranceRef.current;
    const result = await localApi.callVoiceTool(sessionId, {
      name,
      toolCallId: callId,
      arguments: args,
      userUtterance: utterance?.text,
      userUtteranceId: utterance?.index,
    });
    showVoiceActivity(`${name}: ${result.isError ? "failed" : "completed"}`);
    if (result.resonoSessionUpdate) send(voicePreparationRef.current?.sessionUpdate(result.resonoSessionUpdate) ?? result.resonoSessionUpdate);
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
    clearVoiceActivity();
    voicePreparationRef.current?.close(); voicePreparationRef.current = null;
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
      const transcriptCaptureFailures = await countFailedTranscriptWrites(pending);
      try {
        await localApi.closeVoice(id, { transcriptCaptureFailures });
        if (transcriptCaptureFailures)
          setError("Some transcript updates could not be saved. Session review was blocked to avoid learning from incomplete history.");
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

  return { voiceState, statusText, subStatus, voicePreparation, voiceActivity, voiceSessionIdRef, remoteAudioRef, toggleVoice, closeVoice };
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
