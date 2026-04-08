<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { page } from "$app/stores";
  import LoginPrompt from "$lib/LoginPrompt.svelte";
  import { isAuthenticated } from "$lib/auth-store";
  import { BenchmarkStore, fetchResultBlob } from "$lib/benchmarks.svelte";

  const store = new BenchmarkStore();

  onMount(() => {
    if (!$isAuthenticated) return;
    store.load($page.url.searchParams.get("job"));
  });

  onDestroy(() => store.stopPolling());

  // ---- Form (local UI state only) --------------------------------------------

  let form = $state({
    datasetName: "demo",
    obsDir: "/Users/hayden/code/ROMP/demo/data/obs",
    modelName: "aifs",
    modelDir: "/Users/hayden/code/ROMP/demo/data/aifs",
    startDate: "2015-05-01",
    endDate: "2015-07-31",
    startYearClim: 2013,
    endYearClim: 2015,
    region: "India",
    initDays: "2,5",
    parallel: false,
  });
  let submitting = $state(false);
  let submitError = $state<string | null>(null);

  async function handleSubmit() {
    submitting = true;
    submitError = null;
    try {
      await store.submitRun({
        datasetName: form.datasetName,
        obsDir: form.obsDir,
        modelName: form.modelName,
        modelDir: form.modelDir,
        params: {
          start_date: form.startDate,
          end_date: form.endDate,
          start_year_clim: form.startYearClim,
          end_year_clim: form.endYearClim,
          region: form.region,
          init_days: form.initDays,
          parallel: form.parallel,
        },
      });
    } catch (e) {
      submitError = e instanceof Error ? e.message : "Submission failed.";
    } finally {
      submitting = false;
    }
  }
</script>

{#if !$isAuthenticated}
  <LoginPrompt message="Sign in to view and run benchmarks." />
{:else}
<div class="flex min-h-[calc(100vh-3.5rem)] max-w-[1200px] mx-auto px-7 py-8 gap-6 items-start">

  <!-- Sidebar -->
  <aside class="w-[210px] shrink-0 flex flex-col gap-3">
    <button
      class="new-run-btn"
      class:active={store.showForm}
      onclick={() => { store.showForm = true; store.selectedId = null; store.stopPolling(); }}
    >
      + New Run
    </button>

    {#if store.jobs.length > 0}
      <p class="sidebar-title">Runs</p>
      <ul class="job-list">
        {#each store.jobs as job}
          <li class="job-list-item">
            <button
              class="job-item"
              class:selected={store.selectedId === job.id && !store.showForm}
              onclick={() => store.selectJob(job)}
            >
              <span class="job-region">{job.params?.region ?? job.model_name.toUpperCase()}</span>
              <div class="job-meta">
                <span class="job-model">{job.created_at ? new Date(job.created_at).toLocaleDateString() : ""}</span>
                <span class="status-badge {job.status}">{job.status}</span>
              </div>
            </button>
            <button
              class="job-delete"
              title="Delete run"
              onclick={(e) => { e.stopPropagation(); store.deleteJob(job.id); }}
            >&times;</button>
          </li>
        {/each}
      </ul>
    {/if}
  </aside>

  <!-- Detail -->
  <div class="flex-1 bg-[var(--color-surface-raised)] border border-[var(--color-border-subtle)] rounded-[0.6rem] px-8 py-7 min-w-0">

    {#if store.showForm}
      <header class="flex items-start justify-between mb-5">
        <div>
          <p class="detail-eyebrow">Configure</p>
          <h1 class="detail-region">New Benchmark Run</h1>
        </div>
      </header>
      <hr class="border-none border-t border-[var(--color-border-subtle)] mb-6" />

      <form class="run-form" onsubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
        <fieldset>
          <legend>Dataset</legend>
          <div class="field-row">
            <label>Name <input bind:value={form.datasetName} required /></label>
            <label class="grow">Observations Directory <input bind:value={form.obsDir} required /></label>
          </div>
        </fieldset>

        <fieldset>
          <legend>Model</legend>
          <div class="field-row">
            <label>Model
              <select bind:value={form.modelName}>
                <option value="aifs">AIFS</option>
              </select>
            </label>
            <label class="grow">Model Directory <input bind:value={form.modelDir} required /></label>
          </div>
        </fieldset>

        <fieldset>
          <legend>Parameters</legend>
          <div class="field-row">
            <label>Region <input bind:value={form.region} required /></label>
            <label>Start Date <input type="date" bind:value={form.startDate} required /></label>
            <label>End Date <input type="date" bind:value={form.endDate} required /></label>
          </div>
          <div class="field-row">
            <label>Clim Start Year <input type="number" bind:value={form.startYearClim} required /></label>
            <label>Clim End Year <input type="number" bind:value={form.endYearClim} required /></label>
            <label>Init Days <input bind:value={form.initDays} placeholder="e.g. 2,5" required /></label>
            <label class="checkbox-label">
              <input type="checkbox" bind:checked={form.parallel} />
              Parallel
            </label>
          </div>
        </fieldset>

        {#if submitError}
          <p class="form-error">{submitError}</p>
        {/if}

        <button class="btn-submit" type="submit" disabled={submitting}>
          {submitting ? "Submitting…" : "Run Benchmark"}
        </button>
      </form>

    {:else if store.selectedJob}
      <header class="flex items-start justify-between mb-5">
        <div>
          <p class="detail-eyebrow">Benchmark Results</p>
          <h1 class="detail-region">{store.selectedJob.params?.region ?? store.selectedJob.model_name.toUpperCase()}</h1>
        </div>
        <div class="flex flex-col items-end gap-1">
          <span class="detail-meta-label">Model</span>
          <span class="detail-meta-value">{store.selectedJob.model_name.toUpperCase()}</span>
          {#if store.selectedJob.completed_at}
            <span class="detail-meta-label">Completed</span>
            <span class="detail-meta-value">{new Date(store.selectedJob.completed_at).toLocaleString()}</span>
          {/if}
        </div>
      </header>
      <hr class="border-none border-t border-[var(--color-border-subtle)] mb-6" />

      {#if store.selectedJob.status === "running"}
        <div class="flex items-center gap-3 text-[var(--color-text-muted)] text-[0.9rem] py-4">
          <div class="spinner"></div>
          <p class="m-0">Running… checking every 3 seconds</p>
        </div>

      {:else if store.selectedJob.status === "failed"}
        <p class="metrics-heading">Error Logs</p>
        {#await store.logsPromise}
          <p class="muted">Loading logs…</p>
        {:then logs}
          {#if logs}<pre class="logs">{logs}</pre>{/if}
        {:catch e}
          <p class="muted">Failed to load logs: {e.message}</p>
        {/await}

      {:else if store.selectedJob.status === "complete"}
        <p class="metrics-heading">Figures</p>
        {#await store.resultsPromise}
          <p class="muted">Loading results…</p>
        {:then results}
          <div class="flex flex-col gap-6">
            {#each (results ?? []).filter((r) => r.type === "figure") as fig}
              <div class="figure-card">
                {#await fetchResultBlob(fig.url)}
                  <div class="figure-loading">Loading…</div>
                {:then src}
                  <img {src} alt={fig.name} />
                {:catch}
                  <div class="figure-loading">Failed to load image.</div>
                {/await}
                <p class="figure-name">{fig.name}</p>
              </div>
            {/each}
          </div>
        {:catch e}
          <p class="muted">Failed to load results: {e.message}</p>
        {/await}
      {/if}

    {:else}
      <div class="flex items-center py-4">
        <p class="muted">Select a run from the sidebar.</p>
      </div>
    {/if}

  </div>
</div>
{/if}

<style>
  /* ---- Sidebar ---- */
  .new-run-btn {
    width: 100%;
    padding: 0.6rem 0.75rem;
    background: var(--color-accent);
    color: var(--color-bg);
    border: none;
    border-radius: 0.4rem;
    font-family: var(--font-body);
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    transition: background-color 0.12s, transform 0.1s;
    letter-spacing: 0.02em;
  }

  .new-run-btn:hover, .new-run-btn.active {
    background: var(--color-accent-hover);
    transform: translateY(-1px);
  }

  .sidebar-title {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--color-text-dim);
    margin: 0 0 0.1rem 0.25rem;
  }

  .job-list {
    list-style: none;
    padding: 0.4rem;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    background: var(--color-surface-raised);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.6rem;
  }

  .job-list-item {
    position: relative;
    display: flex;
    align-items: stretch;
  }

  .job-delete {
    position: absolute;
    top: 0.3rem;
    right: 0.3rem;
    padding: 0.15rem 0.3rem;
    background: none;
    border: none;
    color: var(--color-text-dim);
    font-size: 0.75rem;
    line-height: 1;
    cursor: pointer;
    border-radius: 0.2rem;
    transition: color 0.12s, background-color 0.12s;
  }

  .job-delete:hover {
    color: var(--color-danger);
    background-color: var(--color-danger-bg);
  }

  /* Repeated pattern — keep in CSS */
  .job-item {
    width: 100%;
    text-align: left;
    padding: 0.55rem 0.65rem;
    border-radius: 0.3rem;
    border: none;
    background: none;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    transition: background-color 0.12s;
    color: var(--color-text);
  }

  .job-item:hover { background: var(--color-accent-glow); }
  .job-item.selected {
    background: var(--color-accent-light);
    box-shadow: inset 2px 0 0 var(--color-accent);
  }
  .job-item.selected .job-region { color: var(--color-accent); }

  .job-region { font-size: 0.875rem; font-weight: 500; color: var(--color-text); }

  .job-meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.4rem;
  }

  .job-model { font-size: 0.68rem; color: var(--color-text-dim); text-transform: uppercase; letter-spacing: 0.05em; }

  /* Repeated pattern — all 3 badge variants share base styles */
  .status-badge {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    font-weight: 500;
    padding: 0.1rem 0.4rem;
    border-radius: 0.2rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .status-badge.running  { background: var(--color-status-running-bg);  color: var(--color-status-running); }
  .status-badge.complete { background: var(--color-status-complete-bg); color: var(--color-status-complete); }
  .status-badge.failed   { background: var(--color-status-failed-bg);   color: var(--color-status-failed); }

  /* ---- Detail panel typography ---- */
  .detail-eyebrow {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--color-accent);
    margin: 0 0 0.3rem 0;
    opacity: 0.8;
  }

  .detail-region {
    font-family: var(--font-display);
    font-size: 2.25rem;
    font-weight: 400;
    font-style: italic;
    letter-spacing: -0.01em;
    margin: 0;
    color: var(--color-text);
  }

  .detail-meta-label {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--color-text-dim);
  }

  .detail-meta-value { font-size: 0.9rem; font-weight: 500; color: var(--color-text-muted); }

  .metrics-heading {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--color-text-dim);
    margin: 0 0 0.85rem 0;
  }

  .muted { color: var(--color-text-muted); font-size: 0.9rem; margin: 0; }

  /* ---- Form — all form elements share styles, keep in CSS ---- */
  .run-form { display: flex; flex-direction: column; gap: 1.25rem; }

  fieldset {
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.5rem;
    padding: 1rem 1.25rem;
    margin: 0;
    background: var(--color-surface);
  }

  legend {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--color-text-dim);
    padding: 0 0.4rem;
  }

  .field-row { display: flex; gap: 1rem; flex-wrap: wrap; align-items: flex-end; }

  label {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    font-size: 0.78rem;
    font-weight: 500;
    color: var(--color-text-muted);
  }

  label.grow { flex: 1; min-width: 200px; }

  label.checkbox-label {
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
    color: var(--color-text-muted);
    padding-bottom: 0.1rem;
  }

  input, select {
    padding: 0.45rem 0.65rem;
    border: 1px solid var(--color-border);
    border-radius: 0.35rem;
    font-family: var(--font-body);
    font-size: 0.875rem;
    color: var(--color-text);
    background: var(--color-bg);
    outline: none;
    transition: border-color 0.12s, box-shadow 0.12s;
  }

  input:focus, select:focus {
    border-color: var(--color-accent);
    box-shadow: 0 0 0 2px var(--color-accent-light);
  }

  select option { background: var(--color-surface); }

  input[type="checkbox"] { width: 1rem; height: 1rem; padding: 0; cursor: pointer; accent-color: var(--color-accent); }
  input[type="number"] { width: 90px; }
  input[type="date"]   { width: 140px; color-scheme: dark; }

  .form-error { color: var(--color-danger); font-size: 0.875rem; margin: 0; }

  .btn-submit {
    align-self: flex-start;
    padding: 0.65rem 1.5rem;
    background: var(--color-accent);
    color: var(--color-bg);
    border: none;
    border-radius: 0.4rem;
    font-family: var(--font-body);
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    transition: background-color 0.15s;
    letter-spacing: 0.02em;
  }

  .btn-submit:hover:not(:disabled) { background: var(--color-accent-hover); }
  .btn-submit:disabled { opacity: 0.5; cursor: not-allowed; }

  /* ---- Status / results ---- */
  .spinner {
    width: 1.1rem;
    height: 1.1rem;
    border: 2px solid var(--color-border);
    border-top-color: var(--color-accent);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    flex-shrink: 0;
  }

  @keyframes spin { to { transform: rotate(360deg); } }

  .logs {
    background: var(--color-logs-bg);
    color: var(--color-text-muted);
    font-family: var(--font-mono);
    font-size: 0.76rem;
    line-height: 1.7;
    padding: 1rem 1.25rem;
    border-radius: 0.4rem;
    border: 1px solid var(--color-border-subtle);
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 500px;
    overflow-y: auto;
  }

  .figure-card {
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.5rem;
    overflow: hidden;
    background: var(--color-bg);
  }

  .figure-card img { width: 100%; display: block; }

  .figure-loading {
    padding: 2rem;
    text-align: center;
    color: var(--color-text-dim);
    font-size: 0.85rem;
  }

  .figure-name {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    color: var(--color-text-dim);
    padding: 0.5rem 0.75rem;
    margin: 0;
    border-top: 1px solid var(--color-border-subtle);
    letter-spacing: 0.02em;
  }
</style>
