import { untrack } from "svelte";
import {
  getJobs, getJob, getJobMetrics, getJobGrid, deleteJob, submitJob,
  type Job, type JobParams, type JobMetrics, type BboxFilter, type JobGridResponse,
} from "./api";

// Module-level cache so metrics survive component unmount/remount.
// Only caches the no-bbox baseline fetch — bbox-filtered requests always go to the server.
const _metricsCache = new Map<string, JobMetrics>();

export async function getCachedJobMetrics(jobId: string, bbox?: BboxFilter): Promise<JobMetrics> {
  if (!bbox) {
    const hit = _metricsCache.get(jobId);
    if (hit) return hit;
    const data = await getJobMetrics(jobId);
    _metricsCache.set(jobId, data);
    return data;
  }
  return getJobMetrics(jobId, bbox);
}

const _gridCache = new Map<string, JobGridResponse>();

export async function getCachedJobGrid(
  jobId: string, model: string, window: string, metric: string
): Promise<JobGridResponse> {
  const key = `${jobId}||${model}||${window}||${metric}`;
  const hit = _gridCache.get(key);
  if (hit) return hit;
  const data = await getJobGrid(jobId, model, window, metric);
  _gridCache.set(key, data);
  return data;
}

export type { Job };

export type RunGroup = {
  key: string;           // `${region}||${start_date}||${end_date}`
  region: string;
  startDate: string;
  endDate: string;
  jobs: Job[];
  mostRecentAt: string;  // for sort order
};

export type MultiRunFormData = {
  datasetId: string;
  modelNames: string[];
  sharedParams: JobParams;
  perModelOverrides?: Record<string, Partial<JobParams>>;
};

function buildRunGroups(jobs: Job[]): RunGroup[] {
  const map = new globalThis.Map<string, Job[]>();
  for (const job of jobs) {
    const region = job.params?.region ?? "unknown";
    const start  = job.params?.start_date ?? "unknown";
    const end    = job.params?.end_date   ?? "unknown";
    const key    = `${region}||${start}||${end}`;
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(job);
  }
  return [...map.entries()]
    .map(([key, groupJobs]) => {
      const mostRecentAt = groupJobs
        .map((j) => j.created_at ?? "")
        .sort()
        .at(-1) ?? "";
      const first = groupJobs[0];
      return {
        key,
        region:    first.params?.region     ?? "Unknown",
        startDate: first.params?.start_date ?? "",
        endDate:   first.params?.end_date   ?? "",
        jobs: groupJobs,
        mostRecentAt,
      } satisfies RunGroup;
    })
    .sort((a, b) => b.mostRecentAt.localeCompare(a.mostRecentAt));
}

export class BenchmarkStore {
  jobs = $state<Job[]>([]);
  selectedGroupKey = $state<string | null>(null);
  showForm = $state(true);

  runGroups = $derived(buildRunGroups(this.jobs));
  selectedGroup = $derived(
    this.runGroups.find((g) => g.key === this.selectedGroupKey) ?? null
  );

  private pollTimer: ReturnType<typeof setInterval> | null = null;

  async load(groupKey?: string | null) {
    try {
      this.jobs = await getJobs();
    } catch (e) {
      console.error("Failed to fetch jobs", e);
    }
    if (groupKey) {
      const exists = buildRunGroups(this.jobs).some((g) => g.key === groupKey);
      if (exists) {
        this.selectedGroupKey = groupKey;
        this.showForm = false;
      }
    }
    this.startPolling();
  }

  selectGroup(key: string) {
    this.selectedGroupKey = key;
    this.showForm = false;
  }

  async deleteGroup(key: string) {
    const group = untrack(() => this.runGroups.find((g) => g.key === key));
    if (!group) return;
    await Promise.all(group.jobs.map((j) => deleteJob(j.id)));
    const removedIds = new Set(group.jobs.map((j) => j.id));
    this.jobs = untrack(() => this.jobs.filter((j) => !removedIds.has(j.id)));
    if (untrack(() => this.selectedGroupKey) === key) {
      this.selectedGroupKey = null;
      this.showForm = true;
    }
  }

  startPolling() {
    if (this.pollTimer) return;
    this.pollTimer = setInterval(async () => {
      const running = untrack(() => this.jobs.filter((j) => j.status === "running"));
      if (running.length === 0) return;
      const updated = await Promise.all(running.map((j) => getJob(j.id)));
      for (const u of updated) {
        const idx = untrack(() => this.jobs.findIndex((j) => j.id === u.id));
        if (idx !== -1) this.jobs[idx] = u;
      }
    }, 3000);
  }

  stopPolling() {
    if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null; }
  }

  async submitRuns(data: MultiRunFormData): Promise<void> {
    const results = await Promise.all(
      data.modelNames.map((modelName) =>
        submitJob({
          dataset_id: data.datasetId,
          model_name: modelName,
          params: {
            ...data.sharedParams,
            ...(data.perModelOverrides?.[modelName] ?? {}),
          },
        })
      )
    );
    this.jobs = [...results, ...untrack(() => this.jobs)];
    const first = results[0];
    const key = `${first.params?.region ?? "unknown"}||${first.params?.start_date ?? "unknown"}||${first.params?.end_date ?? "unknown"}`;
    this.selectedGroupKey = key;
    this.showForm = false;
  }

  /** Fetch metrics for a specific job (used for grid resolution chip) */
  getJobMetrics(id: string): Promise<JobMetrics> {
    return getJobMetrics(id);
  }
}

export { getJobMetrics };
export { fetchResultBlob } from "./api";
export type { JobMetrics };
