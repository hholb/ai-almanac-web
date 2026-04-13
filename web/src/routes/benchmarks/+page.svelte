<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { page } from "$app/stores";
  import LoginPrompt from "$lib/LoginPrompt.svelte";
  import { isAuthenticated } from "$lib/auth-store";
  import { BenchmarkStore, type MultiRunFormData } from "$lib/benchmarks.svelte";
  import ResultsViewer from "$lib/components/ResultsViewer.svelte";
  import JobLogs from "$lib/components/JobLogs.svelte";
  import { getModels, getDatasets, type ModelConfig, type Dataset, type JobParams } from "$lib/api";

  const store = new BenchmarkStore();

  let models = $state<ModelConfig[]>([]);
  let datasets = $state<Dataset[]>([]);

  onMount(async () => {
    if (!$isAuthenticated) return;
    const groupKey = $page.url.searchParams.get("group");
    store.load(groupKey);
    const [fetchedModels, fetchedDatasets] = await Promise.allSettled([getModels(), getDatasets()]);
    if (fetchedModels.status === "fulfilled" && fetchedModels.value.length > 0) {
      models = fetchedModels.value;
    }
    if (fetchedDatasets.status === "fulfilled") {
      datasets = fetchedDatasets.value;
      const first = datasets[0];
      if (first) {
        form.datasetId = first.id;
        form.obsFilePattern = first.obs_file_pattern ?? "";
      }
    }
  });

  onDestroy(() => store.stopPolling());

  // ---- Multi-model form -------------------------------------------------------

  let form = $state({
    datasetId: "",
    region: "India",
    startDate: "2015-05-01",
    endDate: "2015-07-31",
    startYearClim: 2013,
    endYearClim: 2015,
    maxForecastDay: null as number | null,
    initDays: "2,5",
    parallel: false,
    // Advanced — obs overrides
    obs: "",
    obsFilePattern: "",
    obsVar: "",
    // Advanced — wet/dry
    wetThreshold: null as number | null,
    wetSpell: null as number | null,
    drySpell: null as number | null,
    // Advanced — masks
    ncMask: "",
    threshFile: "",
  });

  let selectedModelIds = $state<string[]>([]);
  let perModelOverrides = $state<Record<string, Record<string, string | boolean | number>>>({});
  let submitting = $state(false);
  let submitError = $state<string | null>(null);

  function toggleModel(id: string) {
    if (selectedModelIds.includes(id)) {
      selectedModelIds = selectedModelIds.filter((m) => m !== id);
      return;
    }
    const cfg = models.find((m) => m.id === id);
    selectedModelIds = [...selectedModelIds, id];
    if (!cfg) return;

    // First model selected → seed shared params from it
    if (selectedModelIds.length === 1) {
      form.startDate      = cfg.start_date;
      form.endDate        = cfg.end_date;
      form.startYearClim  = cfg.start_year_clim;
      form.endYearClim    = cfg.end_year_clim;
      form.initDays       = cfg.init_days;
    }

    // Seed per-model overrides with model-specific technical params only.
    // Date ranges are shared across all models in a run (the evaluation window).
    perModelOverrides = {
      ...perModelOverrides,
      [id]: {
        init_days:     cfg.init_days,
        probabilistic: cfg.probabilistic,
        members:       cfg.members ?? "",
        model_var:     cfg.model_var !== "tp" ? cfg.model_var : "",
        file_pattern:  cfg.file_pattern !== "{}.nc" ? cfg.file_pattern : "",
      },
    };
  }

  function setOverride(modelId: string, key: string, value: string | boolean | number) {
    perModelOverrides = {
      ...perModelOverrides,
      [modelId]: { ...(perModelOverrides[modelId] ?? {}), [key]: value },
    };
  }

  function getOverride<T>(modelId: string, key: string, fallback: T): T {
    const v = perModelOverrides[modelId]?.[key];
    return v !== undefined ? (v as T) : fallback;
  }

  async function handleSubmit() {
    if (selectedModelIds.length === 0) { submitError = "Select at least one model."; return; }
    submitting = true;
    submitError = null;
    try {
      const sharedParams: JobParams = {
        region: form.region,
        start_date: form.startDate,
        end_date: form.endDate,
        start_year_clim: form.startYearClim,
        end_year_clim: form.endYearClim,
        init_days: form.initDays,
        parallel: form.parallel,
        ...(form.maxForecastDay != null && { max_forecast_day: form.maxForecastDay }),
        ...(form.obs            && { obs: form.obs }),
        ...(form.obsFilePattern && { obs_file_pattern: form.obsFilePattern }),
        ...(form.obsVar         && { obs_var: form.obsVar }),
        ...(form.wetThreshold != null && { wet_threshold: form.wetThreshold }),
        ...(form.wetSpell     != null && { wet_spell: form.wetSpell }),
        ...(form.drySpell     != null && { dry_spell: form.drySpell }),
        ...(form.ncMask       && { nc_mask: form.ncMask }),
        ...(form.threshFile   && { thresh_file: form.threshFile }),
      };

      // Per-model overrides: technical model params only (dates are shared).
      const overrides: Record<string, Partial<JobParams>> = {};
      for (const mid of selectedModelIds) {
        const overrideMap = perModelOverrides[mid] ?? {};
        const o: Partial<JobParams> = {};
        if (overrideMap.init_days)   o.init_days   = String(overrideMap.init_days);
        if (overrideMap.model_var)   o.model_var   = String(overrideMap.model_var);
        if (overrideMap.file_pattern) o.file_pattern = String(overrideMap.file_pattern);
        if (overrideMap.members)     o.members     = String(overrideMap.members);
        if (overrideMap.probabilistic !== undefined) o.probabilistic = Boolean(overrideMap.probabilistic);
        overrides[mid] = o;
      }

      await store.submitRuns({
        datasetId: form.datasetId,
        modelNames: selectedModelIds,
        sharedParams,
        perModelOverrides: overrides,
      } satisfies MultiRunFormData);

      // Update URL to reflect selected group
      const g = store.selectedGroupKey;
      if (g) history.replaceState(null, "", `?group=${encodeURIComponent(g)}`);
    } catch (e) {
      submitError = e instanceof Error ? e.message : "Submission failed.";
    } finally {
      submitting = false;
    }
  }

  function selectGroup(key: string) {
    store.selectGroup(key);
    history.replaceState(null, "", `?group=${encodeURIComponent(key)}`);
  }
</script>

{#if !$isAuthenticated}
  <LoginPrompt message="Sign in to view and run benchmarks." />
{:else}
<div class="page-layout">

  <!-- Sidebar -->
  <aside class="sidebar">
    <button
      class="new-run-btn"
      class:active={store.showForm}
      onclick={() => { store.showForm = true; store.selectedGroupKey = null; }}
    >
      + New Run Set
    </button>

    {#if store.runGroups.length > 0}
      <p class="sidebar-title">Run Sets</p>
      <ul class="group-list">
        {#each store.runGroups as group}
          <li class="group-list-item">
            <button
              class="group-item"
              class:selected={store.selectedGroupKey === group.key && !store.showForm}
              onclick={() => selectGroup(group.key)}
            >
              <span class="group-region">{group.region}</span>
              {#if group.startDate && group.endDate}
                <span class="group-dates">{group.startDate} – {group.endDate}</span>
              {/if}
              <div class="group-badges">
                <span class="badge-count">{group.jobs.length} model{group.jobs.length !== 1 ? "s" : ""}</span>
                {#if group.jobs.some((j) => j.status === "running")}
                  <span class="status-badge running">running</span>
                {:else if group.jobs.every((j) => j.status === "complete")}
                  <span class="status-badge complete">complete</span>
                {:else if group.jobs.every((j) => j.status === "failed")}
                  <span class="status-badge failed">failed</span>
                {:else}
                  <span class="status-badge mixed">mixed</span>
                {/if}
              </div>
            </button>
            <button
              class="group-delete"
              title="Delete run set"
              onclick={(e) => { e.stopPropagation(); store.deleteGroup(group.key); }}
            >&times;</button>
          </li>
        {/each}
      </ul>
    {/if}
  </aside>

  <!-- Main content -->
  <div class="main-content">

    {#if store.showForm}
      <!-- ---- New Run Set form ---- -->
      <header class="detail-header">
        <p class="detail-eyebrow">Configure</p>
        <h1 class="detail-title">New Run Set</h1>
      </header>
      <hr class="divider" />

      <form class="run-form" onsubmit={(e) => { e.preventDefault(); handleSubmit(); }}>

        <fieldset>
          <legend>Dataset</legend>
          <div class="field-row">
            <label class="grow">Observations
              <select
                bind:value={form.datasetId}
                required
                onchange={(e) => {
                  const ds = datasets.find((d) => d.id === (e.target as HTMLSelectElement).value);
                  form.obsFilePattern = ds?.obs_file_pattern ?? "";
                }}
              >
                {#if datasets.length === 0}
                  <option value="">Loading…</option>
                {:else}
                  {@const demoDatasets = datasets.filter((d) => d.is_demo)}
                  {@const userDatasets = datasets.filter((d) => !d.is_demo)}
                  {#if demoDatasets.length > 0}
                    <optgroup label="Demo Data">
                      {#each demoDatasets as d}
                        <option value={d.id}>{d.name}</option>
                      {/each}
                    </optgroup>
                  {/if}
                  {#if userDatasets.length > 0}
                    <optgroup label="My Datasets">
                      {#each userDatasets as d}
                        <option value={d.id}>{d.name}</option>
                      {/each}
                    </optgroup>
                  {/if}
                {/if}
              </select>
            </label>
          </div>
        </fieldset>

        <fieldset>
          <legend>Models</legend>
          {#if models.length === 0}
            <p class="loading-hint">Loading models…</p>
          {:else}
            <div class="model-chip-grid">
              {#each models as m}
                <button
                  type="button"
                  class="model-chip"
                  class:active={selectedModelIds.includes(m.id)}
                  onclick={() => toggleModel(m.id)}
                >
                  <span class="chip-name">{m.display_name}</span>
                  <span class="chip-years">{m.start_date.slice(0,4)}–{m.end_date.slice(0,4)}</span>
                </button>
              {/each}
            </div>
          {/if}
        </fieldset>

        <fieldset>
          <legend>Parameters</legend>
          <div class="field-row">
            <label>Region <input bind:value={form.region} required /></label>
            <label>Start Date <input type="date" bind:value={form.startDate} required /></label>
            <label>End Date <input type="date" bind:value={form.endDate} required /></label>
          </div>
        </fieldset>

        <details class="param-section" open>
          <summary>Common Options</summary>
          <fieldset class="nested-fieldset">
            <div class="field-row">
              <label>Clim Start Year <input type="number" bind:value={form.startYearClim} /></label>
              <label>Clim End Year <input type="number" bind:value={form.endYearClim} /></label>
              <label>Max Forecast Day <input type="number" bind:value={form.maxForecastDay} placeholder="optional" /></label>
              <label>Init Days <input bind:value={form.initDays} placeholder="e.g. 2,5" /></label>
              <label class="checkbox-label"><input type="checkbox" bind:checked={form.parallel} /> Parallel</label>
            </div>
          </fieldset>
        </details>

        {#if selectedModelIds.length > 0}
          <details class="param-section" open>
            <summary>Per-model Configuration</summary>
            {#each selectedModelIds as modelId}
              {@const cfg = models.find((m) => m.id === modelId)}
              <fieldset class="nested-fieldset">
                <div class="model-fieldset-header">
                  <span class="model-fieldset-name">{cfg?.display_name ?? modelId}</span>
                  {#if cfg}
                    <span class="model-avail-range">available {cfg.start_date.slice(0,7)} – {cfg.end_date.slice(0,7)}</span>
                  {/if}
                </div>
                <div class="field-row">
                  <label>Init Days
                    <input
                      value={getOverride(modelId, "init_days", cfg?.init_days ?? "")}
                      oninput={(e) => setOverride(modelId, "init_days", (e.target as HTMLInputElement).value)}
                    />
                  </label>
                  <label class="checkbox-label">
                    <input
                      type="checkbox"
                      checked={getOverride(modelId, "probabilistic", cfg?.probabilistic ?? false)}
                      onchange={(e) => setOverride(modelId, "probabilistic", (e.target as HTMLInputElement).checked)}
                    />
                    Probabilistic
                  </label>
                  {#if getOverride(modelId, "probabilistic", cfg?.probabilistic ?? false)}
                    <label>Members
                      <input
                        value={getOverride(modelId, "members", cfg?.members ?? "")}
                        placeholder="e.g. 11 or All"
                        oninput={(e) => setOverride(modelId, "members", (e.target as HTMLInputElement).value)}
                      />
                    </label>
                  {/if}
                </div>
              </fieldset>
            {/each}
          </details>
        {/if}

        <details class="param-section">
          <summary>Advanced Options</summary>
          <fieldset class="nested-fieldset">
            <legend>Observation Overrides</legend>
            <div class="field-row">
              <label>obs <input bind:value={form.obs} /></label>
              <label>obs_file_pattern <input bind:value={form.obsFilePattern} /></label>
              <label>obs_var <input bind:value={form.obsVar} /></label>
            </div>
          </fieldset>
          <fieldset class="nested-fieldset">
            <legend>Wet / Dry Spell</legend>
            <div class="field-row">
              <label>wet_threshold <input type="number" step="any" bind:value={form.wetThreshold} /></label>
              <label>wet_spell <input type="number" bind:value={form.wetSpell} /></label>
              <label>dry_spell <input type="number" bind:value={form.drySpell} /></label>
            </div>
          </fieldset>
          <fieldset class="nested-fieldset">
            <legend>Masks &amp; Thresholds</legend>
            <div class="field-row">
              <label class="grow">nc_mask path <input bind:value={form.ncMask} /></label>
              <label class="grow">thresh_file path <input bind:value={form.threshFile} /></label>
            </div>
          </fieldset>
        </details>

        {#if submitError}
          <p class="form-error">{submitError}</p>
        {/if}

        <button class="btn-submit" type="submit" disabled={submitting || selectedModelIds.length === 0}>
          {submitting ? "Submitting…" : `Run ${selectedModelIds.length > 1 ? selectedModelIds.length + " Models" : "Benchmark"}`}
        </button>
      </form>

    {:else if store.selectedGroup}
      <!-- ---- Run Set Results ---- -->
      {@const group = store.selectedGroup}
      <header class="detail-header">
        <div>
          <p class="detail-eyebrow">Run Set</p>
          <h1 class="detail-title">{group.region}</h1>
          {#if group.startDate && group.endDate}
            <p class="detail-dates">{group.startDate} – {group.endDate}</p>
          {/if}
        </div>
      </header>

      <!-- Per-model status pills -->
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

      {@const completeJobs = group.jobs.filter((j) => j.status === "complete")}

      {#if completeJobs.length > 0}
        <ResultsViewer jobs={completeJobs} />
      {:else if group.jobs.some((j) => j.status === "running")}
        <div class="running-state">
          <div class="spinner"></div>
          <p>Running benchmarks… checking every 3 s</p>
        </div>
      {:else}
        <div class="failed-runs">
          {#each group.jobs.filter((j) => j.status === "failed") as job}
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

    {:else}
      <div class="empty-state">
        <p class="muted">Select a run set from the sidebar or create a new one.</p>
      </div>
    {/if}

  </div>
</div>
{/if}

<style>
  .page-layout {
    display: flex;
    min-height: calc(100vh - 3.5rem);
    max-width: 1400px;
    margin: 0 auto;
    padding: 2rem 1.75rem;
    gap: 1.5rem;
    align-items: flex-start;
  }

  /* ---- Sidebar ---- */
  .sidebar {
    width: 220px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

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
  .new-run-btn:hover, .new-run-btn.active { background: var(--color-accent-hover); transform: translateY(-1px); }

  .sidebar-title {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--color-text-dim);
    margin: 0.25rem 0 0 0.25rem;
  }

  .group-list {
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

  .group-list-item {
    position: relative;
    display: flex;
    align-items: stretch;
  }

  .group-item {
    width: 100%;
    text-align: left;
    padding: 0.55rem 1.5rem 0.55rem 0.65rem;
    border-radius: 0.3rem;
    border: none;
    background: none;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    transition: background-color 0.12s;
    color: var(--color-text);
  }
  .group-item:hover { background: var(--color-accent-glow); }
  .group-item.selected {
    background: var(--color-accent-light);
    box-shadow: inset 2px 0 0 var(--color-accent);
  }
  .group-item.selected .group-region { color: var(--color-accent); }

  .group-region { font-size: 0.875rem; font-weight: 500; }
  .group-dates { font-size: 0.65rem; color: var(--color-text-dim); font-family: var(--font-mono); }

  .group-badges {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    margin-top: 0.1rem;
    flex-wrap: wrap;
  }

  .badge-count {
    font-size: 0.6rem;
    font-weight: 600;
    color: var(--color-text-dim);
  }

  .group-delete {
    position: absolute;
    top: 0.35rem;
    right: 0.35rem;
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
  .group-delete:hover { color: var(--color-danger); background-color: var(--color-danger-bg); }

  /* ---- Status badges ---- */
  .status-badge {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    font-weight: 500;
    padding: 0.1rem 0.4rem;
    border-radius: 0.2rem;
  }
  .status-badge.running  { background: #fff3cd; color: #856404; }
  .status-badge.complete { background: #d4edda; color: #155724; }
  .status-badge.failed   { background: #f8d7da; color: #721c24; }
  .status-badge.mixed    { background: var(--color-border-subtle); color: var(--color-text-dim); }

  /* ---- Main content ---- */
  .main-content {
    flex: 1;
    min-width: 0;
    background: var(--color-surface-raised);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.6rem;
    padding: 2rem;
  }

  .detail-header { margin-bottom: 1.25rem; }
  .detail-eyebrow {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--color-text-dim);
    margin: 0 0 0.2rem;
  }
  .detail-title {
    font-size: 1.5rem;
    font-weight: 700;
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
  .model-pill.running  { background: #fff3cd; border-color: #ffc107; color: #856404; }
  .model-pill.failed   { background: #f8d7da; border-color: #f5c6cb; color: #721c24; }
  .model-pill.complete { background: #d4edda; border-color: #c3e6cb; color: #155724; }

  .pill-name { letter-spacing: 0.05em; }
  .pill-icon { font-size: 0.7rem; }
  .pill-spinner {
    width: 0.6rem; height: 0.6rem;
    border: 1.5px solid #ffc107;
    border-top-color: #856404;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ---- Form styles ---- */
  .run-form { display: flex; flex-direction: column; gap: 1.25rem; }

  fieldset {
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.4rem;
    padding: 0.75rem 1rem 1rem;
    margin: 0;
  }
  legend {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--color-text-dim);
    padding: 0 0.35rem;
  }

  .field-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    align-items: flex-end;
  }

  label {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    font-size: 0.72rem;
    font-weight: 500;
    color: var(--color-text-muted);
  }
  label.grow { flex: 1; min-width: 140px; }
  label.checkbox-label { flex-direction: row; align-items: center; gap: 0.4rem; font-size: 0.8rem; padding-bottom: 0.15rem; }

  input[type="text"], input:not([type]), input[type="number"], input[type="date"], select {
    padding: 0.35rem 0.55rem;
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.3rem;
    background: var(--color-surface);
    color: var(--color-text);
    font-family: var(--font-body);
    font-size: 0.8rem;
    outline: none;
    transition: border-color 0.12s;
  }
  input:focus, select:focus { border-color: var(--color-accent); }

  /* Model chip grid */
  .model-chip-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    padding-top: 0.25rem;
  }

  .model-chip {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.1rem;
    padding: 0.4rem 0.85rem;
    border: 1.5px solid var(--color-border-subtle);
    border-radius: 0.35rem;
    background: var(--color-surface);
    color: var(--color-text-dim);
    font-family: var(--font-body);
    cursor: pointer;
    transition: background-color 0.12s, color 0.12s, border-color 0.12s;
    text-align: left;
  }
  .model-chip:hover { border-color: var(--color-accent); color: var(--color-accent); }
  .model-chip.active {
    background: var(--color-accent-light);
    border-color: var(--color-accent);
    color: var(--color-accent);
  }
  .chip-name { font-size: 0.78rem; font-weight: 600; }
  .chip-years { font-size: 0.62rem; font-family: var(--font-mono); opacity: 0.75; }
  .model-chip.active .chip-years { opacity: 0.9; }

  .model-fieldset-header {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    margin-bottom: 0.65rem;
  }
  .model-fieldset-name {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--color-text-muted);
  }
  .model-avail-range {
    font-size: 0.65rem;
    font-family: var(--font-mono);
    color: var(--color-text-dim);
  }

  .loading-hint { font-size: 0.78rem; color: var(--color-text-dim); margin: 0.25rem 0 0; }

  .param-section {
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.4rem;
    overflow: hidden;
  }
  .param-section > summary {
    padding: 0.6rem 0.9rem;
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--color-text-muted);
    cursor: pointer;
    list-style: none;
    user-select: none;
    background: var(--color-surface);
    transition: background-color 0.12s;
  }
  .param-section > summary::-webkit-details-marker { display: none; }
  .param-section[open] > summary { border-bottom: 1px solid var(--color-border-subtle); }
  .param-section > summary:hover { background: var(--color-accent-glow); }

  .nested-fieldset {
    border: none;
    border-top: 1px solid var(--color-border-subtle);
    border-radius: 0;
    padding: 0.75rem 0.9rem;
    margin: 0;
  }
  .nested-fieldset:first-of-type { border-top: none; }
  .nested-fieldset legend {
    font-size: 0.65rem;
    color: var(--color-text-dim);
    margin-bottom: 0.5rem;
    padding: 0;
  }

  .btn-submit {
    align-self: flex-start;
    padding: 0.6rem 1.4rem;
    background: var(--color-accent);
    color: var(--color-bg);
    border: none;
    border-radius: 0.4rem;
    font-family: var(--font-body);
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    transition: background-color 0.12s, opacity 0.12s;
  }
  .btn-submit:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-submit:not(:disabled):hover { background: var(--color-accent-hover); }

  .form-error {
    font-size: 0.8rem;
    color: var(--color-danger);
    margin: 0;
  }

  /* ---- States ---- */
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

  .empty-state { padding: 2rem 0; }
  .muted { color: var(--color-text-dim); font-size: 0.9rem; margin: 0; }

  .failed-runs { display: flex; flex-direction: column; gap: 1.25rem; }
  .job-error {
    border: 1px solid #5a2020;
    border-radius: 6px;
    padding: 0.75rem 1rem;
    background: #1f1010;
  }
  .job-error-title {
    margin: 0 0 0.35rem;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: #e07070;
  }
  .job-error-msg {
    margin: 0 0 0.5rem;
    font-size: 0.78rem;
    color: #cc8888;
    white-space: pre-wrap;
    word-break: break-word;
    font-family: "JetBrains Mono", "Fira Mono", monospace;
  }
</style>
