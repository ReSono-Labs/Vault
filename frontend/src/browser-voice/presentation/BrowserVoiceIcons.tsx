import { useRef } from "react";
type IconProps = {
  className?: string;
};

const sharedIconProps = {
  "aria-hidden": true,
  fill: "none",
  viewBox: "0 0 24 24",
} as const;

export function BrowserVoiceMicrophoneIcon({ className }: IconProps) {
  return (
    <svg {...sharedIconProps} className={className}>
      <rect height="11" rx="4" stroke="currentColor" strokeWidth="1.8" width="7" x="8.5" y="3" />
      <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3M9 21h6" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </svg>
  );
}

export function BrowserVoiceHomeIcon({ className }: IconProps) {
  return (
    <svg {...sharedIconProps} className={className}>
      <path d="m4 10 8-6 8 6v9a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1v-9Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}

export function BrowserVoiceAgentsIcon({ className }: IconProps) {
  return (
    <svg {...sharedIconProps} className={className}>
      <circle cx="12" cy="7.5" r="3.5" stroke="currentColor" strokeWidth="1.7" />
      <path d="M5.5 21v-2.2a6.5 6.5 0 0 1 13 0V21" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
    </svg>
  );
}

export function BrowserVoiceConnectionsIcon({ className }: IconProps) {
  return (
    <svg {...sharedIconProps} className={className}>
      <path d="m9.5 14.5-2 2a3.5 3.5 0 1 1-5-5l3-3a3.5 3.5 0 0 1 5 0M14.5 9.5l2-2a3.5 3.5 0 1 1 5 5l-3 3a3.5 3.5 0 0 1-5 0M8.5 15.5l7-7" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
    </svg>
  );
}

export function BrowserVoiceMemoryIcon({ className }: IconProps) {
  return (
    <svg {...sharedIconProps} className={className}>
      <path d="M9.2 5.2A3.2 3.2 0 0 0 4 7.7c0 .6.2 1.2.5 1.7A3.5 3.5 0 0 0 5.7 16c.2 2.2 2.8 3.5 4.6 2.1.6-.5 1-1.2 1-2V7.4c0-1.2-.9-2.2-2.1-2.2ZM14.8 5.2A3.2 3.2 0 0 1 20 7.7c0 .6-.2 1.2-.5 1.7a3.5 3.5 0 0 1-1.2 6.6c-.2 2.2-2.8 3.5-4.6 2.1-.6-.5-1-1.2-1-2V7.4c0-1.2.9-2.2 2.1-2.2Z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
      <path d="M7 10.2c1.4 0 2.5 1 2.5 2.4M17 10.2c-1.4 0-2.5 1-2.5 2.4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
    </svg>
  );
}

export function BrowserVoiceConnectionCategoryIcon({ category, className }: IconProps & { category: string }) {
  if (category === "email") {
    return <svg {...sharedIconProps} className={className}><rect height="14" rx="2" stroke="currentColor" strokeWidth="1.7" width="19" x="2.5" y="5" /><path d="m3.5 7 8.5 6 8.5-6" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" /></svg>;
  }
  if (category === "calendar") {
    return <BrowserVoiceCardIcon className={className} kind="calendar" />;
  }
  return <BrowserVoiceConnectionsIcon className={className} />;
}

export function BrowserVoiceDevicesIcon({ className }: IconProps) {
  return (
    <svg {...sharedIconProps} className={className}>
      <rect height="19" rx="2" stroke="currentColor" strokeWidth="1.7" width="11" x="6.5" y="2.5" />
      <path d="M10 18.5h4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
    </svg>
  );
}

export function BrowserVoiceDocumentsIcon({ className }: IconProps) {
  return <svg {...sharedIconProps} className={className}><path d="M6 3h9l3 3v15H6V3Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" /><path d="M15 3v4h4M9 11h6M9 15h6M9 19h4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" /></svg>;
}

export type BrowserVoiceCardIconKind = "contacts" | "reminders" | "calendar" | "workout";

export function BrowserVoiceCardIcon({ className, kind }: IconProps & { kind: BrowserVoiceCardIconKind }) {
  if (kind === "contacts") {
    return (
      <svg {...sharedIconProps} className={className}>
        <circle cx="9" cy="9" r="3.2" stroke="currentColor" strokeWidth="1.7" />
        <path d="M3.5 20v-1.8a5.5 5.5 0 0 1 11 0V20M16 7.2a3 3 0 0 1 0 5.6M17 14.5a4.6 4.6 0 0 1 3.5 4.5v1" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
      </svg>
    );
  }
  if (kind === "reminders") {
    return (
      <svg {...sharedIconProps} className={className}>
        <path d="M6.5 17.5h11l-1.3-2.1V10a4.2 4.2 0 0 0-8.4 0v5.4l-1.3 2.1Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
        <path d="M10 20a2.3 2.3 0 0 0 4 0M10.5 4.2a1.5 1.5 0 0 1 3 0" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
      </svg>
    );
  }
  if (kind === "calendar") {
    return (
      <svg {...sharedIconProps} className={className}>
        <rect height="16" rx="2" stroke="currentColor" strokeWidth="1.7" width="17" x="3.5" y="5" />
        <path d="M7.5 3v4M16.5 3v4M3.5 9h17M8 13h1M12 13h1M16 13h1M8 17h1M12 17h1" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
      </svg>
    );
  }
  return (
    <svg {...sharedIconProps} className={className}>
      <path d="M3 9v6M6 7v10M9 10v4M15 10v4M18 7v10M21 9v6M9 12h6" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
    </svg>
  );
}

export function browserVoiceAccountInitials(label: string) {
  const parts = label.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "U";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

export function BrowserVoiceWorkspaceIcon({ className }: { className?: string }) {
  return (
    <svg {...sharedIconProps} className={className}>
      <path d="M3.5 6.5h6l2 2h9v10.5a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19V6.5Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}

export function BrowserVoiceSettingsIcon({ className }: IconProps) {
  return (
    <svg {...sharedIconProps} className={className}>
      <circle cx="12" cy="12" r="3.2" stroke="currentColor" strokeWidth="1.7" />
      <path
        d="M12 2.8v2.1M12 19.1v2.1M4.6 4.6l1.5 1.5M17.9 17.9l1.5 1.5M2.8 12h2.1M19.1 12h2.1M4.6 19.4l1.5-1.5M17.9 6.1l1.5-1.5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.7"
      />
    </svg>
  );
}

export type BrowserVoiceDestination = "account" | "agent2agent" | "background" | "capabilities" | "chat" | "connections" | "documents" | "home" | "memory" | "settings" | "workspace";

function ChatIcon({ className }: IconProps) {
  return <svg {...sharedIconProps} className={className}><path d="M4 4h16v12H9l-5 4V4Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" /></svg>;
}

export function BrowserVoiceFutureNavigation({
  activeDestination = "home",
  onNavigate,
  placement,
}: {
  activeDestination?: BrowserVoiceDestination;
  onNavigate?: (destination: BrowserVoiceDestination) => void;
  placement: "desktop" | "mobile";
}) {
  const drawer = useRef<HTMLDialogElement>(null);
  const items = [
    { key: "home", label: placement === "desktop" ? "Overview" : "Voice", icon: BrowserVoiceHomeIcon },
    { key: "chat", label: "Chat", icon: ChatIcon },
    { key: "workspace", label: placement === "desktop" ? "Workspace" : "Files", icon: BrowserVoiceWorkspaceIcon },
    { key: "capabilities", label: placement === "desktop" ? "Library" : "Library", icon: BrowserVoiceAgentsIcon },
    { key: "connections", label: placement === "desktop" ? "Connections" : "Connect", icon: BrowserVoiceConnectionsIcon },
    { key: "memory", label: "Memory", icon: BrowserVoiceMemoryIcon },
    { key: "agent2agent", label: placement === "desktop" ? "Agent2Agent" : "Agents", icon: BrowserVoiceAgentsIcon },
    { key: "background", label: placement === "desktop" ? "Background Agent" : "Tasks", icon: BrowserVoiceAgentsIcon },
    { key: "documents", label: placement === "desktop" ? "Documents" : "Docs", icon: BrowserVoiceDocumentsIcon },
    { key: "settings", label: "Settings", icon: BrowserVoiceSettingsIcon },
    { key: "account", label: "Accounts", icon: BrowserVoiceDevicesIcon },
  ];
  const navigation = (
    <nav aria-label={`${placement === "desktop" ? "Desktop" : "Mobile"} future navigation`} className={`browser-voice-future-nav is-${placement}`}>
      {items.map((item) => {
        const Icon = item.icon;
        const available = true;
        return (
          <button
            aria-current={onNavigate && activeDestination === item.key ? "page" : undefined}
            className={onNavigate && activeDestination === item.key ? "is-active" : ""}
            disabled={!available || !onNavigate}
            key={item.key}
            onClick={() => { onNavigate?.(item.key as BrowserVoiceDestination); drawer.current?.close(); }}
            title={available ? item.label : `${item.label} is not available yet`}
            type="button"
          >
            <Icon className="browser-voice-future-nav-icon" />
            <span>{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
  if (placement === "desktop") return navigation;
  return <div className="browser-voice-mobile-menu">
    <button className="browser-voice-mobile-menu-trigger" type="button" onClick={() => drawer.current?.showModal()} aria-haspopup="dialog">Menu</button>
    <dialog ref={drawer} className="browser-voice-mobile-menu-drawer" aria-label="Navigation" onClick={event => { if (event.target === event.currentTarget) drawer.current?.close(); }}>
      <header><strong>Navigation</strong><button type="button" onClick={() => drawer.current?.close()} aria-label="Close navigation">Close</button></header>
      {navigation}
    </dialog>
  </div>;
}
