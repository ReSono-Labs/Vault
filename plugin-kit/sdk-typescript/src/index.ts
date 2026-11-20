export type VaultInvocationContext = {
  serviceUrl: string;
  capabilityToken: string;
  invocationId: string;
  configuration: Record<string, unknown>;
};

export function contextFromHeaders(headers: Headers): VaultInvocationContext {
  const serviceUrl = headers.get("x-vault-service-url");
  const capabilityToken = headers.get("x-vault-capability");
  const invocationId = headers.get("x-vault-invocation-id");
  if (!serviceUrl || !capabilityToken || !invocationId) {
    throw new Error("This request is missing its Vault invocation information.");
  }
  const encoded = headers.get("x-vault-configuration");
  const configuration = encoded ? JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(encoded.replace(/-/g, "+").replace(/_/g, "/")), (character) => character.charCodeAt(0)))) as Record<string, unknown> : {};
  return {serviceUrl: serviceUrl.replace(/\/$/, ""), capabilityToken, invocationId, configuration};
}

export class VaultServiceClient {
  constructor(private readonly context: VaultInvocationContext) {}

  async call<T extends Record<string, unknown>>(service: string, payload: Record<string, unknown>): Promise<T> {
    const response = await fetch(`${this.context.serviceUrl}/${service}`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${this.context.capabilityToken}`,
        "content-type": "application/json",
        "x-vault-invocation-id": this.context.invocationId,
      },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error("Vault service request failed.");
    return await response.json() as T;
  }

  searchMemory(query: string, limit = 5) {
    return this.call("memory/search", {query, limit});
  }

  proposeMemory(text: string, source = "plugin") {
    return this.call("memory/propose", {text, source});
  }

  locale() {
    return this.call("context/locale", {});
  }

  reportActivity(message: string) {
    return this.call("activity/report", {message});
  }
}
