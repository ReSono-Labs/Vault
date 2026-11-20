import { useEffect, useRef } from "react";
import { BrowserVoiceMicrophoneIcon } from "@/browser-voice/presentation/BrowserVoiceIcons";
import type { VoiceState } from "@/browser-voice/useVoiceSession";

export function HomeVoice({
  voiceState,
  statusText,
  subStatus,
  isLive,
  onToggle,
  activity,
}: {
  voiceState: VoiceState;
  statusText: string;
  subStatus: string;
  isLive: boolean;
  onToggle: () => void;
  activity: string[];
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
      {activity.length ? <aside className="browser-voice-live-activity" aria-label="Voice reasoning and tool activity" aria-live="polite">
        <strong>Live activity</strong>
        {activity.map((text, index) => <p key={index}>{text}</p>)}
      </aside> : null}
    </>
  );
}
