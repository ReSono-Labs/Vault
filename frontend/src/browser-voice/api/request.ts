export type ApiError = { error?: { message?: string } };

export function csrfToken() {
  const match = document.cookie.match(/(?:^|; )resono_csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body !== undefined)
    headers.set("Content-Type", "application/json");
  if ((options.method ?? "GET").toUpperCase() !== "GET") {
    const csrf = csrfToken();
    if (csrf) headers.set("X-ReSono-CSRF", csrf);
  }
  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  const value = (await response.json().catch(() => ({}))) as T & ApiError;
  if (!response.ok)
    throw new Error(
      value.error?.message ||
        `Local Vault request failed (${response.status}).`,
    );
  return value;
}

export async function fileBase64(file: File) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}
