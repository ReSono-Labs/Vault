# UI component cleanup queue

Authority: owner items listed here; visual lock remains `GROUNDING.md` / D-02 unless an item explicitly reopens it.  
Implementation: owner authorized the batch on 2026-09-11 (“get those done, built and deployed to docker”).

Status: implemented (awaiting owner live check)  
Batch authorized: yes

| ID | Surface | Request | Type | Primary files | Status |
|---|---|---|---|---|---|
| UIC-Q-001 | Workspace page | See below | copy + layout | `frontend/src/browser-voice/BrowserVoiceApp.tsx`, `frontend/src/browser-voice/BrowserWorkspaceFileBrowser.tsx` | implemented |
| UIC-Q-002 | Workspace page | File preview has no dismiss; add **Close** | missing control | `frontend/src/browser-voice/BrowserWorkspaceFileBrowser.tsx` | implemented |
| UIC-Q-003 | Connections · AI & Voice | OAuth/API/provider action buttons | control visibility | `frontend/src/browser-voice/ConnectionsPanel.tsx` | implemented |
| UIC-Q-004 | Settings · Computer folders | Enlarge/center **Linked folders** below the separator | layout | `frontend/src/browser-voice/styles/browser-voice-agents.css` | implemented |

## UIC-Q-001 — Workspace page

Owner 2026-09-11.

### Heading copy

Current:

- `h2`: `Your workspace`
- subtitle: `Private files from your Vault, available before or during voice.`

Required:

- Title becomes `{signed-in user display name}'s Workspace` (owner wrote `$USER$'s Workspace`).
- Remove the private-files subtitle. Do not replace it with other explanatory copy.

Related strings to keep consistent in the same batch (same page family, not extra invented items):

- Shell title in `BrowserVoiceApp.tsx` currently `Your workspace`.
- Collapsed file-browser copy `Private files from your Vault.`

### Folder chrome layout

Current (`BrowserWorkspaceFileBrowser.tsx`): when not at the folder root, `Up one folder` renders **above** the directory title row (`local` / `Swipe left for actions`), which pushes that title down.

Required:

- Keep the directory title row **at the top** of the file list (`{currentDirectoryLabel}` + `Swipe left for actions`).
- Place the `Up one folder` control **at the bottom** (below the file rows), not above the title.

Visual lock: this is a reorder of existing chrome, not a new design system.

## UIC-Q-002 — File preview Close

Owner 2026-09-11.

Current: clicking a file opens preview/editor in `.browser-voice-files-preview`. There is Save for editable files, but no control to clear the selection. Empty state copy is `Open a file to preview or edit it.`

Required:

- Add a **Close** button (owner prefers Close over Clear).
- Close dismisses the open preview/editor and returns the preview pane to the empty state.
- Apply whenever a file is open (text edit, image, PDF, and non-editable fallback), not only for one preview kind.

Visual lock: add the missing control using existing button/chip patterns; do not invent a new preview chrome.

## UIC-Q-003 — Connections, AI & Voice actions

Owner 2026-09-11. Screenshot showed `ChatGPT OAuth`, `Use API key`, `Disconnect OAuth`, `Save settings`, and `Disconnect provider` all visible together.

Current (`ConnectionsPanel.tsx`): `ChatGPT OAuth` / `Gemini OAuth` is always shown for those providers. `Use API key` shows when an API key is stored while auth method is not `api_key`. `Disconnect OAuth` already gates on `oauthConnected`. `Disconnect provider` shows whenever the provider is `configured`. `Save settings` remains.

Required:

- Remove **Use API key**.
- Remove **Disconnect provider**.
- **Connect OAuth** (`ChatGPT OAuth` / `Gemini OAuth`) shows only when OAuth is **not** connected.
- **Disconnect OAuth** shows only when OAuth **is** connected (and therefore Connect OAuth is hidden).
- Keep **Save settings**.

This is button visibility/removal on the existing form, not a restyle of the Connections page.

## UIC-Q-004 — Settings, Linked folders heading

Owner 2026-09-11.

Required:

- **Linked folders** text is enlarged.
- Centered on its line.
- Sits well below the horizontal separator (extra top padding after a top border).

Visual lock: spacing/size of this heading only; do not restyle the rest of Settings.
