/** Typed client for the API. All API types live in this file. */

export const API_BASE_URL: string =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface HealthResponse {
  status: string;
  renderer: string;
  ocr: string;
}

export interface ApiErrorBody {
  error: { code: string; message: string };
}

export type HandStatus = "empty" | "learning" | "ready" | "failed";

export interface HandDocument {
  id: string;
  page_count: number;
  status: string;
  created_at: string;
  own_hand_confirmed_at: string | null;
  own_hand_statement: string;
}

export interface Hand {
  id: string | null;
  status: HandStatus;
  status_reason: string | null;
  status_message: string | null;
  sample_count: number;
  own_hand_confirmed_at: string | null;
  own_hand_statement: string;
  documents: HandDocument[];
}

export interface Chat {
  id: string;
  hand_id: string | null;
  title: string;
  created_at: string;
}

export interface ChatFile {
  id: string;
  kind: "pdf" | "image";
  page_count: number;
  safety_status: "ok" | "refused";
  safety_reason: string | null;
  safety_message: string | null;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "tool";
  content_json: { text?: string; reply?: string } | null;
  created_at: string;
}

export interface ChatDetail extends Chat {
  latest_render_version: number | null;
  files: ChatFile[];
  messages: ChatMessage[];
}

export interface MessageReply {
  reply: string;
  render_version: number | null;
  preview_url: string | null;
}

export interface AnalysisRegion {
  id: string;
  page: number;
  kind: "line" | "box" | "blank";
  bbox_px: [number, number, number, number];
  signature: boolean;
}

export interface PageAnalysis {
  width: number;
  height: number;
  regions: AnalysisRegion[];
}

export interface FileAnalysis {
  pages: PageAnalysis[];
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

/** Error codes that are a safety refusal, shown as a friendly notice rather than an error. */
export const REFUSAL_CODES: readonly string[] = [
  "document_refused",
  "file_refused",
  "signature_blocked",
];

export function isRefusal(err: unknown): err is ApiError {
  return err instanceof ApiError && REFUSAL_CODES.includes(err.code);
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const err = (value as { error: unknown }).error;
  return (
    typeof err === "object" &&
    err !== null &&
    typeof (err as { code?: unknown }).code === "string" &&
    typeof (err as { message?: unknown }).message === "string"
  );
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(
      "network",
      "Cannot reach the API. Check that the server is running and try again.",
      0,
    );
  }
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = undefined;
    }
    if (isApiErrorBody(body)) {
      throw new ApiError(body.error.code, body.error.message, res.status);
    }
    throw new ApiError("unknown", `The API returned an unexpected error (${res.status}).`, res.status);
  }
  return res;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await send(path, init);
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError("bad_response", "The API sent a response we could not read.", res.status);
  }
}

function jsonBody(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export function getHand(): Promise<Hand> {
  return request<Hand>("/hand");
}

export function uploadHandDocument(file: File, ownHandConfirmed: boolean): Promise<HandDocument> {
  const form = new FormData();
  form.append("file", file);
  form.append("own_hand_confirmed", ownHandConfirmed ? "true" : "false");
  return request<HandDocument>("/hand/documents", { method: "POST", body: form });
}

export function listChats(): Promise<Chat[]> {
  return request<Chat[]>("/chats");
}

export function createChat(): Promise<Chat> {
  return request<Chat>("/chats", { method: "POST" });
}

export function getChat(id: string): Promise<ChatDetail> {
  return request<ChatDetail>(`/chats/${id}`);
}

export function uploadChatFile(chatId: string, file: File): Promise<ChatFile> {
  const form = new FormData();
  form.append("file", file);
  return request<ChatFile>(`/chats/${chatId}/files`, { method: "POST", body: form });
}

export function sendMessage(chatId: string, text: string): Promise<MessageReply> {
  return request<MessageReply>(`/chats/${chatId}/messages`, jsonBody({ text }));
}

export function getAnalysis(chatId: string, fileId: string): Promise<FileAnalysis> {
  return request<FileAnalysis>(`/chats/${chatId}/files/${fileId}/analysis`);
}

export function filePageUrl(chatId: string, fileId: string, page: number): string {
  return `${API_BASE_URL}/chats/${chatId}/files/${fileId}/pages/${page}.png`;
}

export function renderPreviewUrl(chatId: string, version: number, page: number): string {
  return `${API_BASE_URL}/chats/${chatId}/renders/${version}/preview.png?page=${page}`;
}

export type ExportFormat = "pdf" | "png";

/** Export a render and hand the bytes back as a Blob plus a suggested file name. */
export async function exportRender(
  chatId: string,
  version: number,
  format: ExportFormat,
  page = 1,
): Promise<{ blob: Blob; filename: string }> {
  const res = await send(
    `/chats/${chatId}/export?version=${version}&format=${format}&page=${page}`,
    { method: "POST" },
  );
  return { blob: await res.blob(), filename: `handwriting-v${version}.${format}` };
}

/** Message shown for a failed call; refusals keep the API's own friendly wording. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return "Something went wrong. Please try again.";
}
