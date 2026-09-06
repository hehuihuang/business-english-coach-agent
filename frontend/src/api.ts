const API_ORIGIN = import.meta.env.VITE_API_ORIGIN ?? "";
const API = `${API_ORIGIN}/api/v1`;

export type CoachResponse = {
  run_id: string;
  trace_id: string;
  content: string;
  plan: string[];
  assessment: Record<string, number>;
  citations: string[];
  tool_events: Array<Record<string, unknown>>;
  usage: { input_tokens: number; output_tokens: number; latency_ms: number };
};

export class ApiClient {
  accessToken = localStorage.getItem("coach_access") || "";
  refreshToken = localStorage.getItem("coach_refresh") || "";

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
    if (this.accessToken) headers.set("Authorization", `Bearer ${this.accessToken}`);
    const response = await fetch(`${API}${path}`, { ...init, headers });
    if (!response.ok) {
      const problem = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(typeof problem.detail === "string" ? problem.detail : JSON.stringify(problem.detail));
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }

  async bootstrapDemo() {
    await fetch(`${API}/demo/bootstrap`, { method: "POST" });
    return this.login("learner@example.com", "learn-english");
  }

  async login(email: string, password: string) {
    const tokens = await this.request<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }),
    });
    this.accessToken = tokens.access_token;
    this.refreshToken = tokens.refresh_token;
    localStorage.setItem("coach_access", tokens.access_token);
    localStorage.setItem("coach_refresh", tokens.refresh_token);
    return tokens;
  }

  logout() {
    this.accessToken = "";
    this.refreshToken = "";
    localStorage.removeItem("coach_access");
    localStorage.removeItem("coach_refresh");
  }

  me = () => this.request<any>("/me");
  dashboard = () => this.request<any>("/dashboard");
  memories = () => this.request<any[]>("/memories");
  documents = () => this.request<any[]>("/knowledge/documents");
  conversations = () => this.request<any[]>("/conversations");
  evaluations = () => this.request<any[]>("/evaluations");
  improvements = () => this.request<any[]>("/improvements");
  trace = (runId: string) => this.request<any>(`/runs/${runId}/trace`);

  createConversation(mode = "coach") {
    return this.request<{ id: string }>("/conversations", {
      method: "POST", body: JSON.stringify({ title: "Editorial coaching session", mode }),
    });
  }

  sendMessage(conversationId: string, content: string) {
    return this.request<CoachResponse>(`/conversations/${conversationId}/messages`, {
      method: "POST", body: JSON.stringify({ content }),
    });
  }

  transcribe(blob: Blob) {
    const form = new FormData();
    form.append("audio", blob, "practice.webm");
    return this.request<{ text: string }>("/speech/transcriptions", { method: "POST", body: form });
  }

  async speak(text: string) {
    const response = await fetch(`${API}/speech/synthesis`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${this.accessToken}` },
      body: JSON.stringify({ content: text }),
    });
    if (!response.ok) throw new Error("Speech synthesis failed");
    return response.blob();
  }

  upload(title: string, file: File) {
    const form = new FormData();
    form.append("title", title);
    form.append("document", file);
    return this.request<any>("/knowledge/documents", { method: "POST", body: form });
  }
}

export const api = new ApiClient();
