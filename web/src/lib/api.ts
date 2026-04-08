const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

import { getManager } from "./auth";

function authHeaders(): HeadersInit {
  const manager = getManager();
  if (!manager) throw new Error("Not authenticated");
  const authToken = manager.getGlobusAuthToken();
  const apiToken = authToken?.other_tokens?.find(
    (t: any) => t.resource_server === "50964632-afc7-4d4c-abf4-b288cc18a3af"
  );
  if (!apiToken) throw new Error("API token not found — re-login may be required");
  return { Authorization: `Bearer ${apiToken.access_token}` };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...init.headers },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${init.method ?? "GET"} ${path} failed (${res.status}): ${body}`);
  }
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }
  return res.json();
}

// ---- Datasets ----------------------------------------------------------------

export async function getDatasets() {
  return request<Dataset[]>("/datasets");
}

export async function createDatasetFromPath(name: string, obs_dir: string) {
  return request<Dataset>("/datasets/from-path", {
    method: "POST",
    body: JSON.stringify({ name, obs_dir }),
  });
}

// ---- Jobs --------------------------------------------------------------------

export async function getJobs() {
  return request<Job[]>("/jobs");
}

export async function submitJob(params: SubmitJobParams) {
  return request<Job>("/jobs", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function getJob(id: string) {
  return request<Job>(`/jobs/${id}`);
}

export async function getJobResults(id: string) {
  return request<JobResult[]>(`/jobs/${id}/results`);
}

export async function getJobLogs(id: string) {
  return request<{ logs: string }>(`/jobs/${id}/logs`);
}

export async function deleteJob(id: string): Promise<void> {
  await request<void>(`/jobs/${id}`, { method: "DELETE" });
}

/**
 * Fetch a result file (figure/output) as an object URL for display.
 * The backend requires auth headers so we can't use a plain <img src=...>.
 * Results are cached in memory by URL so repeated views don't re-fetch.
 */
const blobCache = new Map<string, string>();

export async function fetchResultBlob(resultUrl: string): Promise<string> {
  if (blobCache.has(resultUrl)) return blobCache.get(resultUrl)!;
  const res = await fetch(`${BASE_URL}${resultUrl}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch result: ${res.status}`);
  const objectUrl = URL.createObjectURL(await res.blob());
  blobCache.set(resultUrl, objectUrl);
  return objectUrl;
}

// ---- Types -------------------------------------------------------------------

export type Dataset = {
  id: string;
  name: string;
  status: string;
  obs_dir?: string;
};

export type JobStatus = "running" | "complete" | "failed";

export type Job = {
  id: string;
  status: JobStatus;
  dataset_id: string;
  model_name: string;
  params?: JobParams;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  error?: string | null;
};

export type JobParams = {
  start_date: string;
  end_date: string;
  start_year_clim: number;
  end_year_clim: number;
  region: string;
  init_days: string;
  parallel: boolean;
};

export type SubmitJobParams = {
  dataset_id: string;
  model_name: string;
  model_dir: string;
  params: JobParams;
};

export type JobResult = {
  name: string;
  type: "figure" | "output";
  url: string;
};
