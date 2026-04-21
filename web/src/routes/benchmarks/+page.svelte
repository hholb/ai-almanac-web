<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { page } from "$app/stores";
  import LoginPrompt from "$lib/LoginPrompt.svelte";
  import { isAuthenticated } from "$lib/auth-store";
  import { BenchmarkStore } from "$lib/benchmarks.svelte";
  import ResultsViewer from "$lib/components/ResultsViewer.svelte";
  import ChatPanel from "$lib/components/ChatPanel.svelte";
  import JobLogs from "$lib/components/JobLogs.svelte";
  import { getDatasets, getRegions, type Dataset, type Region } from "$lib/api";
  import BenchmarkSidebar from "./BenchmarkSidebar.svelte";
  import BenchmarkForm from "./BenchmarkForm.svelte";

  const store = new BenchmarkStore();
  let chatCollapsed = $state(false);

  let regions = $state<Region[]>([]);
  let datasets = $state<Dataset[]>([]);
  let dataLoaded = $state(false);

  onMount(async () => {
    if (!$isAuthenticated) return;
    const groupKey = $page.url.searchParams.get("group");
    store.load(groupKey);
    const [fetchedRegions, fetchedDatasets] = await Promise.allSettled([
      getRegions(), getDatasets(),
    ]);
    if (fetchedRegions.status === "fulfilled") regions = fetchedRegions.value;
    if (fetchedDatasets.status === "fulfilled") datasets = fetchedDatasets.value;
    dataLoaded = true;
  });

  onDestroy(() => store.stopPolling());

  function selectGroup(key: string) {
    store.selectGroup(key);
    history.replaceState(null, "", `?group=${encodeURIComponent(key)}`);
  }

  function startNew() {
    store.showForm = true;
    store.selectedGroupKey = null;
  }

  function handleSubmitted(groupKey: string) {
    history.replaceState(null, "", `?group=${encodeURIComponent(groupKey)}`);
  }
</script>

{#if !$isAuthenticated}
  <LoginPrompt message="Sign in to view and run benchmarks." />
{:else}
<div class="page-layout">

  <BenchmarkSidebar {store} onNewBenchmark={startNew} onSelectGroup={selectGroup} />

  <div class="main-content">

    {#if store.showForm}
      <BenchmarkForm {store} {regions} {datasets} {dataLoaded} onSubmitted={handleSubmitted} />

    {:else if store.selectedGroup}
      <!-- Benchmark Results -->
      {@const group = store.selectedGroup}
      {@const completeJobs = group.jobs.filter((j) => j.status === "complete")}
      {@const failedJobs = group.jobs.filter((j) => j.status === "failed")}

      <div class="results-with-chat" class:chat-hidden={chatCollapsed}>

        <!-- Left column: header + results -->
        <div class="results-main">
          <header class="detail-header">
            <div>
              <p class="detail-eyebrow">Benchmark · {group.jobs.length} model{group.jobs.length !== 1 ? 's' : ''}</p>
              <h1 class="detail-title">{group.region}</h1>
              {#if group.startDate && group.endDate}
                <p class="detail-dates">{group.startDate} – {group.endDate}</p>
              {/if}
            </div>
          </header>

          <div class="model-status-row">
            {#each group.jobs as job}
              <div class="model-pill" class:running={job.status === "running"} class:failed={job.status === "failed"} class:complete={job.status === "complete"}>
                <span class="pill-name">{job.model_name.toUpperCase()}</span>
                {#if job.status === "running"}
                  <span class="pill-spinner"></span>
                {:else if job.status === "failed"}
                  <span class="pill-icon fail" title={job.error ?? "Failed"}>✕</span>
                {:else}
                  <span class="pill-icon ok">✓</span>
                {/if}
              </div>
            {/each}
          </div>

          <hr class="divider" />

          {#if group.jobs.some((j) => j.status === "running") && completeJobs.length === 0}
            <div class="running-state">
              <div class="spinner"></div>
              <p>Running benchmarks… checking every 3 s</p>
            </div>
          {/if}

          {#if failedJobs.length > 0}
            <div class="failed-runs">
              {#each failedJobs as job}
                <div class="job-error">
                  <p class="job-error-title">{job.model_name.toUpperCase()} failed</p>
                  {#if job.error}
                    <pre class="job-error-msg">{job.error}</pre>
                  {/if}
                  <JobLogs jobId={job.id} />
                </div>
              {/each}
            </div>
          {/if}

          {#if completeJobs.length > 0}
            <ResultsViewer jobs={completeJobs} />
          {/if}
        </div>

        <!-- Right column: chat panel (full height from top of content) -->
        <div class="chat-sidebar" class:collapsed={chatCollapsed}>
          <div class="chat-panel-wrap">
            <button
              class="chat-toggle-btn"
              onclick={() => { chatCollapsed = !chatCollapsed; }}
              title={chatCollapsed ? "Show AI analysis" : "Hide AI analysis"}
            >
              <span class="toggle-icon">✦</span>
              <span class="toggle-label">{chatCollapsed ? "AI Analysis" : "Hide"}</span>
            </button>
            {#if !chatCollapsed}
              <ChatPanel jobs={completeJobs} />
            {/if}
          </div>
        </div>

      </div>

    {:else}
      <div class="empty-state">
        <p class="empty-title">No run set selected</p>
        <p class="muted">Click <strong>+ New Benchmark</strong> in the sidebar to benchmark one or more models against ground-truth observations. Select a region, date range, and at least one model — results include spatial maps and per-grid-point skill metrics (MAE, FAR, MR) across forecast lead-time windows.</p>
      </div>
    {/if}

  </div>
</div>
{/if}

<style>
  .page-layout {
    display: flex;
    min-height: calc(100vh - 3.5rem);
    max-width: 1800px;
    margin: 0 auto;
    padding: 1rem 1.75rem;
    gap: 1.5rem;
    align-items: flex-start;
  }

  .main-content {
    flex: 1;
    min-width: 0;
    background: var(--color-surface-raised);
    border: 1px solid var(--color-border);
    border-radius: 0.6rem;
    padding: 1.5rem;
  }

  .results-with-chat {
    display: flex;
    gap: 0;
    align-items: flex-start;
  }

  .results-main {
    flex: 3;
    min-width: 0;
    min-width: 520px;
    padding-right: 1.25rem;
  }

  .chat-sidebar {
    flex: 2;
    min-width: 400px;
    position: sticky;
    /* nav (3.5rem) + page padding (2rem) + main-content padding (1.5rem) = 7rem;
       subtract a little so it doesn't kiss the nav */
    top: calc(3.5rem + 0.5rem);
    height: calc(100vh - 3.5rem - 1rem);
    display: flex;
    flex-direction: column;
    border-left: 1px solid var(--color-border-subtle);
    padding-left: 1.25rem;
  }

  .chat-sidebar.collapsed {
    flex: none;
    min-width: unset;
    height: auto;
    border-left: none;
    padding-left: 0;
  }

  .chat-panel-wrap {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }

  .chat-toggle-btn {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.3rem 0.6rem 0.3rem 0.5rem;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: 6px;
    color: var(--color-text-muted);
    font-size: 0.7rem;
    font-weight: 600;
    font-family: var(--font-body);
    cursor: pointer;
    transition: color 0.15s, border-color 0.15s, background-color 0.15s;
    align-self: flex-start;
    margin-bottom: 0.6rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .chat-toggle-btn:hover {
    color: var(--color-accent);
    border-color: var(--color-accent-border);
    background: var(--color-accent-glow);
  }
  .toggle-icon {
    color: var(--color-accent);
    font-size: 0.6rem;
    line-height: 1;
  }
  .toggle-label {
    letter-spacing: 0.08em;
  }
  .chat-sidebar.collapsed .chat-toggle-btn {
    margin-bottom: 0;
  }

  .results-with-chat .chat-panel-wrap > :global(.chat-panel) {
    flex: 1;
    min-width: 0;
  }

  /* ---- Results header ---- */
  .detail-header { margin-bottom: 1.25rem; }
  .detail-eyebrow {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--color-accent);
    margin: 0 0 0.2rem;
  }
  .detail-title {
    font-size: 1.75rem;
    font-weight: 400;
    font-family: var(--font-display);
    margin: 0;
    color: var(--color-text);
  }
  .detail-dates {
    font-size: 0.8rem;
    color: var(--color-text-muted);
    margin: 0.2rem 0 0;
    font-family: var(--font-mono);
  }
  .divider {
    border: none;
    border-top: 1px solid var(--color-border-subtle);
    margin: 0 0 1.5rem;
  }

  /* ---- Model status pills ---- */
  .model-status-row {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-bottom: 1rem;
  }
  .model-pill {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.3rem 0.65rem;
    border-radius: 0.3rem;
    font-size: 0.75rem;
    font-weight: 600;
    font-family: var(--font-mono);
    border: 1px solid var(--color-border-subtle);
    background: var(--color-surface);
  }
  .model-pill.running  { background: var(--color-status-running-bg);  border-color: var(--color-status-running);  color: var(--color-status-running);  }
  .model-pill.failed   { background: var(--color-status-failed-bg);   border-color: var(--color-status-failed);   color: var(--color-status-failed);   }
  .model-pill.complete { background: var(--color-status-complete-bg); border-color: var(--color-status-complete); color: var(--color-status-complete); }
  .pill-name { letter-spacing: 0.05em; }
  .pill-icon { font-size: 0.7rem; }
  .pill-spinner {
    width: 0.6rem; height: 0.6rem;
    border: 1.5px solid rgba(251, 191, 36, 0.3);
    border-top-color: var(--color-status-running);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .running-state {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    color: var(--color-text-muted);
    font-size: 0.9rem;
    padding: 1rem 0;
  }
  .spinner {
    width: 1.1rem; height: 1.1rem;
    border: 2px solid var(--color-border-subtle);
    border-top-color: var(--color-accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    flex-shrink: 0;
  }

  .failed-runs { display: flex; flex-direction: column; gap: 1.25rem; }
  .job-error {
    border: 1px solid var(--color-danger-border);
    border-radius: 6px;
    padding: 0.75rem 1rem;
    background: var(--color-danger-bg);
  }
  .job-error-title {
    margin: 0 0 0.35rem;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--color-danger);
  }
  .job-error-msg {
    margin: 0 0 0.5rem;
    font-size: 0.78rem;
    color: var(--color-text-muted);
    white-space: pre-wrap;
    word-break: break-word;
    font-family: var(--font-mono);
  }

  /* ---- Empty state ---- */
  .empty-state { padding: 2rem 0; }
  .empty-title { font-size: 0.95rem; font-weight: 600; color: var(--color-text-muted); margin: 0 0 0.5rem; }
  .muted { color: var(--color-text-dim); font-size: 0.9rem; margin: 0; }
</style>
