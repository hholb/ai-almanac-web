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

// ---- Regions -----------------------------------------------------------------

export async function getRegions() {
  return request<Region[]>("/regions");
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

export async function getModels(region?: string) {
  const qs = region ? `?region=${encodeURIComponent(region)}` : "";
  return request<ModelConfig[]>(`/jobs/models${qs}`);
}

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

  // First, hit the backend with auth to get the file or a signed-URL redirect.
  const res = await fetch(`${BASE_URL}${resultUrl}`, {
    headers: authHeaders(),
    redirect: "manual",  // don't auto-follow so we can strip auth before GCS redirect
  });

  let blob: Blob;
  if (res.type === "opaqueredirect") {
    // Production: backend returned a 302 to a GCS signed URL.
    // Fetch the redirect location without the Authorization header — GCS rejects it.
    const location = res.headers.get("Location");
    if (!location) throw new Error("Redirect response missing Location header");
    const gcsRes = await fetch(location);
    if (!gcsRes.ok) throw new Error(`Failed to fetch result from GCS: ${gcsRes.status}`);
    blob = await gcsRes.blob();
  } else if (res.ok) {
    // Local dev: backend served the file directly.
    blob = await res.blob();
  } else {
    throw new Error(`Failed to fetch result: ${res.status}`);
  }

  const objectUrl = URL.createObjectURL(blob);
  blobCache.set(resultUrl, objectUrl);
  return objectUrl;
}

// ---- Types -------------------------------------------------------------------

export type Region = {
  id: string;
  display_name: string;
  romp_region: string;
  description: string;
  has_data: boolean;
};

export type Dataset = {
  id: string;
  name: string;
  status: string;
  is_demo: boolean;
  created_at: string;
  obs_file_pattern?: string | null;
  obs_year_start?: number | null;
  obs_year_end?: number | null;
};

export type JobStatus = "running" | "complete" | "failed";

export type Job = {
  id: string;
  status: JobStatus;
  dataset_id: string;
  model_name: string;
  model_dir?: string;
  obs_dir?: string;
  params?: JobParams;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  error?: string | null;
  is_owner?: boolean;
  run_id?: string | null;
};

export type JobParams = {
  // Essential
  region?: string;
  start_date?: string;
  end_date?: string;
  event_type?: string;
  // Common
  start_year_clim?: number;
  end_year_clim?: number;
  max_forecast_day?: number;
  init_days?: string;
  parallel?: boolean;
  // Advanced — obs overrides
  obs?: string;
  obs_file_pattern?: string;
  obs_var?: string;
  model_var?: string;
  file_pattern?: string;
  // Advanced — wet/dry spell thresholds
  wet_threshold?: number;
  wet_init?: number;
  wet_spell?: number;
  dry_spell?: number;
  dry_extent?: number;
  // Advanced — probabilistic
  probabilistic?: boolean;
  members?: string;
  // Advanced — reference model
  ref_model?: string;
  ref_model_dir?: string;
  // Advanced — masks/thresholds
  nc_mask?: string;
  thresh_file?: string;
};

export type SubmitJobParams = {
  dataset_id: string;
  model_name: string;
  params: JobParams;
  run_id?: string;
};

export type ModelConfig = {
  id: string;
  display_name: string;
  region: string;
  model_type: string;
  model_dir: string;
  model_var: string;
  unit_cvt: number | null;
  file_pattern: string;
  probabilistic: boolean;
  members: string | null;
  init_days: string;
  start_date: string;
  end_date: string;
  start_year_clim: number;
  end_year_clim: number;
};

export type JobResult = {
  name: string;
  type: "figure" | "output";
  url: string;
};

export type MetricStats = {
  mean: number; min: number; max: number;
  p25: number; p50: number; p75: number; p90: number;
  unit: string;
};

export type WindowMetrics = {
  window: string;
  model: string;
  tolerance_days: number | null;
  metrics: Record<string, MetricStats>;
};

export type BboxExtent = {
  lat_min: number; lat_max: number;
  lon_min: number; lon_max: number;
};

export type GridInfo = {
  lats: number[];
  lons: number[];
};

export type JobMetrics = {
  job_id: string;
  windows: WindowMetrics[];
  grid: GridInfo | null;
  bbox: BboxExtent | null;
};

export type BboxFilter = Partial<BboxExtent>;

export async function getJobMetrics(id: string, bbox?: BboxFilter): Promise<JobMetrics> {
  const params = new URLSearchParams();
  if (bbox?.lat_min != null) params.set("lat_min", String(bbox.lat_min));
  if (bbox?.lat_max != null) params.set("lat_max", String(bbox.lat_max));
  if (bbox?.lon_min != null) params.set("lon_min", String(bbox.lon_min));
  if (bbox?.lon_max != null) params.set("lon_max", String(bbox.lon_max));
  const qs = params.size ? `?${params}` : "";
  return request<JobMetrics>(`/jobs/${id}/metrics${qs}`);
}

export type JobGridResponse = {
  job_id: string;
  model: string;
  window: string;
  metric: string;
  lats: number[];
  lons: number[];
  values: (number | null)[][];
  unit: string;
  min: number;
  max: number;
};

export async function getJobGrid(
  id: string,
  model: string,
  window: string,
  metric: string
): Promise<JobGridResponse> {
  const params = new URLSearchParams({ model, window, metric });
  return request<JobGridResponse>(`/jobs/${id}/grid?${params}`);
}
