import {
  getJobs, getJob, getJobResults, getJobLogs, fetchResultBlob,
  submitJob, deleteJob,
  type Job, type JobResult, type JobParams,
} from "./api";

export type { Job, JobResult };

export type RunFormData = {
  datasetId: string;
  modelName: string;
  params: JobParams;
};

export class BenchmarkStore {
  jobs = $state<Job[]>([]);
  selectedId = $state<string | null>(null);
  showForm = $state(true);
  resultsPromise = $state<Promise<JobResult[]> | null>(null);
  logsPromise = $state<Promise<string> | null>(null);

  private resultsCache = new Map<string, JobResult[]>();

  selectedJob = $derived(this.jobs.find((j) => j.id === this.selectedId) ?? null);

  private pollInterval: ReturnType<typeof setInterval> | null = null;

  async load(jobId?: string | null) {
    try {
      this.jobs = await getJobs();
    } catch (e) {
      console.error("failed to fetch jobs", e);
    }
    if (jobId) {
      this.selectedId = jobId;
      this.showForm = false;
      const job = this.jobs.find((j) => j.id === jobId);
      if (job) {
        if (job.status === "running") this.startPolling();
        else this.loadDetail(job);
      }
    }
  }

  selectJob(job: Job) {
    this.selectedId = job.id;
    this.showForm = false;
    this.stopPolling();
    if (job.status === "running") this.startPolling();
    else this.loadDetail(job);
  }

  loadDetail(job: Job) {
    this.resultsPromise = null;
    this.logsPromise = null;
    if (job.status === "complete") {
      const cached = this.resultsCache.get(job.id);
      if (cached) {
        this.resultsPromise = Promise.resolve(cached);
      } else {
        this.resultsPromise = getJobResults(job.id).then((results) => {
          this.resultsCache.set(job.id, results);
          return results;
        });
      }
    } else if (job.status === "failed") {
      this.logsPromise = getJobLogs(job.id).then((d) => d.logs);
    }
  }

  startPolling() {
    if (this.pollInterval) return;
    this.pollInterval = setInterval(async () => {
      if (!this.selectedId) return;
      const updated = await getJob(this.selectedId);
      this.jobs = this.jobs.map((j) => (j.id === updated.id ? updated : j));
      if (updated.status !== "running") {
        this.stopPolling();
        this.loadDetail(updated);
      }
    }, 3000);
  }

  stopPolling() {
    if (this.pollInterval) { clearInterval(this.pollInterval); this.pollInterval = null; }
  }

  async deleteJob(id: string): Promise<void> {
    await deleteJob(id);
    this.jobs = this.jobs.filter((j) => j.id !== id);
    if (this.selectedId === id) {
      this.selectedId = null;
      this.showForm = true;
      this.stopPolling();
    }
  }

  /** Submits a job and adds it to the list. */
  async submitRun(data: RunFormData): Promise<void> {
    const job = await submitJob({
      dataset_id: data.datasetId,
      model_name: data.modelName,
      params: data.params,
    });
    this.jobs = [job, ...this.jobs];
    this.selectJob(job);
  }
}

export { fetchResultBlob };
