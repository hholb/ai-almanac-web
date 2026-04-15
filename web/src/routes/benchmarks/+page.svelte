<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { page } from "$app/stores";
  import LoginPrompt from "$lib/LoginPrompt.svelte";
  import { isAuthenticated } from "$lib/auth-store";
  import { BenchmarkStore, type MultiRunFormData } from "$lib/benchmarks.svelte";
  import ResultsViewer from "$lib/components/ResultsViewer.svelte";
  import JobLogs from "$lib/components/JobLogs.svelte";
  import { getModels, getDatasets, getRegions, type ModelConfig, type Dataset, type Region, type JobParams } from "$lib/api";

  const store = new BenchmarkStore();

  let regions = $state<Region[]>([]);
  let models = $state<ModelConfig[]>([]);
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
    if (fetchedDatasets.status === "fulfilled") {
      datasets = fetchedDatasets.value;
      const first = datasets[0];
      if (first) {
        form.datasetId = first.id;
        form.obsFilePattern = first.obs_file_pattern ?? "";
      }
    }
    dataLoaded = true;
  });

  // Reload models whenever the selected region changes.
  $effect(() => {
    if (!$isAuthenticated || !selectedRegion) return;
    getModels(selectedRegion.id).then((m) => { if (m.length > 0) models = m; });
  });

  onDestroy(() => store.stopPolling());

  // ---- Multi-model form -------------------------------------------------------

  let form = $state({
    datasetId: "",
    maxForecastDay: null as number | null,
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

  let selectedRegion = $state<Region | null>(null);
  let selectedDataset = $derived(datasets.find((d) => d.id === form.datasetId) ?? null);
  let selectedModelIds = $state<string[]>([]);
  let perModelOverrides = $state<Record<string, Record<string, string | boolean | number>>>({});
  let submitting = $state(false);
  let submitError = $state<string | null>(null);
  let selectedEventType = $state<string | null>(null);

  // ---- Event type catalog ----------------------------------------------------

  type EventTypeStatus = "active" | "coming_soon";

  const EVENT_TYPES: {
    id: string;
    name: string;
    shortName: string;
    description: string;
    regions: string[];
    status: EventTypeStatus;
    onsetDefinition: string;
  }[] = [
    {
      id: "monsoon_onset",
      name: "Monsoon Onset",
      shortName: "Monsoon",
      description: "Evaluate model skill in predicting the calendar date of seasonal monsoon onset using region-specific meteorological definitions.",
      regions: ["India", "Ethiopia"],
      status: "active",
      onsetDefinition: "India: Modified Moron–Robertson (MOK-anchored). Ethiopia: ICPAC 3-day accumulation threshold.",
    },
    {
      id: "monsoon_cessation",
      name: "Monsoon Cessation",
      shortName: "Cessation",
      description: "Evaluate model skill in predicting the end of the monsoon season using region-specific withdrawal definitions.",
      regions: ["Coming soon"],
      status: "coming_soon",
      onsetDefinition: "",
    },
    {
      id: "heatwave_onset",
      name: "Heat Wave Onset",
      shortName: "Heat Wave",
      description: "Benchmark forecasts of heat wave onset defined by sustained anomalous temperature thresholds.",
      regions: ["Coming soon"],
      status: "coming_soon",
      onsetDefinition: "",
    },
    {
      id: "custom",
      name: "Custom Event",
      shortName: "Custom",
      description: "Define your own human-centric event metric with AI assistance. Describe what matters to your community — crop planting windows, flood risk days, school closure thresholds — and we'll help you build a rigorous benchmark around it.",
      regions: ["Coming soon"],
      status: "coming_soon",
      onsetDefinition: "",
    },
  ];

  // ---- Model reference catalog -----------------------------------------------

  const MODEL_CATALOG: Record<string, {
    type: string; forecast: string; resolution: string; period: string; desc: string;
  }> = {
    ifs:       { type: "NWP",  forecast: "Probabilistic · 11 members", resolution: "~32 km", period: "2004–2023",            desc: "ECMWF's operational Integrated Forecasting System — the primary physics-based NWP baseline." },
    aifsdaily: { type: "AIWP", forecast: "Deterministic",              resolution: "0.25°",  period: "2019–2024",            desc: "ECMWF's AI Weather Prediction model — daily-initialized variant. Same architecture as AIFS but initialized every day." },
    aifs:      { type: "AIWP", forecast: "Deterministic",              resolution: "0.25°",  period: "1965–2018",            desc: "ECMWF's AI Weather Prediction model. Fine-tuned on IFS analyses (2016–2022). Twice-weekly initializations (Mon/Thu)." },
    fuxi:      { type: "AIWP", forecast: "Deterministic",              resolution: "0.25°",  period: "1965–2024",            desc: "Fudan University AI model trained on ERA5 (1979–2017). Twice-weekly initializations on Mondays and Thursdays." },
    graphcast: { type: "AIWP", forecast: "Deterministic",              resolution: "0.25°",  period: "1965–2024",            desc: "Google DeepMind graph neural network model trained on ERA5 (1979–2017). Twice-weekly initializations." },
    gencast:   { type: "AIWP", forecast: "Probabilistic · 51 members", resolution: "0.25°",  period: "1965–1978, 2019–2024", desc: "Google DeepMind generative ensemble model trained on ERA5 (1979–2018). Note the gap in hindcast coverage." },
    fuxis2s:   { type: "AIWP", forecast: "Probabilistic · 51 members", resolution: "1.5°",   period: "2002–2021",            desc: "Fudan University sub-seasonal-to-seasonal model. Coarser resolution optimized for extended-range (weeks 2–4) prediction. Trained on ERA5 (1950–2016)." },
    ngcm:      { type: "AIWP", forecast: "Probabilistic · 51 members", resolution: "2.8°",   period: "1965–2024",            desc: "Google's Neural GCM — hybrid physics-ML architecture trained 2001–2018. Available April–July only. Twice-weekly initializations." },
  };

  function lookupModel(id: string) {
    const normalized = id.toLowerCase().replace(/[^a-z0-9]/g, "");
    // Exact match first, then prefix, to avoid substring collisions (e.g. "ifs" inside "aifs").
    const entry =
      Object.entries(MODEL_CATALOG).find(([k]) => k === normalized) ??
      Object.entries(MODEL_CATALOG).find(([k]) => normalized.startsWith(k));
    return entry?.[1] ?? null;
  }

  function toggleModel(id: string) {
    if (selectedModelIds.includes(id)) {
      selectedModelIds = selectedModelIds.filter((m) => m !== id);
      return;
    }
    const cfg = models.find((m) => m.id === id);
    selectedModelIds = [...selectedModelIds, id];
    if (!cfg) return;

    // Seed per-model overrides. Dates and clim years are per-model because each
    // model covers a different hindcast period — they must not be shared.
    // Clamp to obs availability so ROMP never requests a year without obs data.
    const obsStart = selectedDataset?.obs_year_start ?? null;
    const obsEnd   = selectedDataset?.obs_year_end   ?? null;

    const clampYear = (year: number) => {
      let y = year;
      if (obsStart !== null) y = Math.max(y, obsStart);
      if (obsEnd   !== null) y = Math.min(y, obsEnd);
      return y;
    };
    const clampDate = (dateStr: string) => {
      const year = parseInt(dateStr.slice(0, 4));
      return String(clampYear(year)) + dateStr.slice(4);
    };

    perModelOverrides = {
      ...perModelOverrides,
      [id]: {
        start_date:      clampDate(cfg.start_date),
        end_date:        clampDate(cfg.end_date),
        start_year_clim: clampYear(cfg.start_year_clim),
        end_year_clim:   clampYear(cfg.end_year_clim),
        init_days:       cfg.init_days,
        parallel:        !cfg.probabilistic,
        probabilistic:   cfg.probabilistic,
        members:         cfg.members ?? "",
        model_var:       cfg.model_var !== "tp" ? cfg.model_var : "",
        file_pattern:    cfg.file_pattern !== "{}.nc" ? cfg.file_pattern : "",
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
        event_type: selectedEventType ?? "monsoon_onset",
        region: selectedRegion!.romp_region,
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

      // Per-model overrides: all date/clim/technical params are per-model since
      // each model covers a different hindcast and climatological period.
      const overrides: Record<string, Partial<JobParams>> = {};
      for (const mid of selectedModelIds) {
        const overrideMap = perModelOverrides[mid] ?? {};
        const o: Partial<JobParams> = {};
        if (overrideMap.start_date)   o.start_date   = String(overrideMap.start_date);
        if (overrideMap.end_date)     o.end_date     = String(overrideMap.end_date);
        if (overrideMap.init_days)    o.init_days    = String(overrideMap.init_days);
        if (overrideMap.parallel !== undefined) o.parallel = Boolean(overrideMap.parallel);
        if (overrideMap.model_var)    o.model_var    = String(overrideMap.model_var);
        if (overrideMap.file_pattern) o.file_pattern = String(overrideMap.file_pattern);
        if (overrideMap.members)      o.members      = String(overrideMap.members);
        if (overrideMap.probabilistic !== undefined) o.probabilistic = Boolean(overrideMap.probabilistic);
        if (overrideMap.start_year_clim != null) o.start_year_clim = Number(overrideMap.start_year_clim);
        if (overrideMap.end_year_clim   != null) o.end_year_clim   = Number(overrideMap.end_year_clim);
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
      onclick={() => { store.showForm = true; store.selectedGroupKey = null; selectedRegion = null; selectedEventType = null; }}
    >
      + New Benchmark
    </button>

    {#if store.runGroups.length > 0}
      {@const myGroups = store.runGroups.filter((g) => g.isOwner)}
      {@const sharedGroups = store.runGroups.filter((g) => !g.isOwner)}

      {#snippet groupList(groups: typeof store.runGroups)}
        <ul class="group-list">
          {#each groups as group}
            <li class="group-list-item">
              <button
                class="group-item"
                class:selected={store.selectedGroupKey === group.key && !store.showForm}
                onclick={() => selectGroup(group.key)}
              >
                <span class="group-event-type">{EVENT_TYPES.find(e => e.id === group.eventType)?.shortName ?? group.eventType}</span>
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
              {#if group.isOwner}
                <button
                  class="group-delete"
                  title="Delete run set"
                  onclick={(e) => { e.stopPropagation(); store.deleteGroup(group.key); }}
                >&times;</button>
              {/if}
            </li>
          {/each}
        </ul>
      {/snippet}

      <details class="sidebar-section" open>
        <summary class="sidebar-title">My Benchmarks <span class="sidebar-count">{myGroups.length}</span></summary>
        {#if myGroups.length > 0}
          {@render groupList(myGroups)}
        {:else}
          <p class="sidebar-empty">No benchmarks yet.</p>
        {/if}
      </details>

      {#if sharedGroups.length > 0}
        <details class="sidebar-section">
          <summary class="sidebar-title">Shared With Me <span class="sidebar-count">{sharedGroups.length}</span></summary>
          {@render groupList(sharedGroups)}
        </details>
      {/if}
    {/if}
  </aside>

  <!-- Main content -->
  <div class="main-content">

    {#if store.showForm && !selectedRegion}
      <!-- ---- Step 1: Region picker ---- -->
      <header class="detail-header">
        <p class="detail-eyebrow">New Benchmark · Step 1 of 3</p>
        <h1 class="detail-title">Choose a Region</h1>
        <p class="detail-subtitle">Select the geographic region for this benchmark. The region determines which observation datasets and onset definitions are available.</p>
      </header>
      <hr class="divider" />

      <div class="event-type-grid">
        {#each regions as r}
          <button
            type="button"
            class="event-type-card"
            class:no-data={!r.has_data}
            onclick={() => { if (r.has_data) { selectedRegion = r; selectedModelIds = []; perModelOverrides = {}; } }}
          >
            <div class="etc-top">
              <span class="etc-name">{r.display_name}</span>
              {#if r.has_data}
                <span class="etc-active-badge">Data available</span>
              {:else}
                <span class="etc-soon-badge">No data configured</span>
              {/if}
            </div>
            <p class="etc-desc">{r.description}</p>
          </button>
        {/each}
      </div>

    {:else if store.showForm && selectedRegion && !selectedEventType}
      <!-- ---- Step 2: Event type picker ---- -->
      <header class="detail-header">
        <div class="detail-header-row">
          <button class="back-btn" onclick={() => { selectedRegion = null; }} title="Back to region selection">← Back</button>
          <div>
            <p class="detail-eyebrow">New Benchmark · Step 2 of 3</p>
            <h1 class="detail-title">Choose an Event Type</h1>
            <p class="detail-subtitle">Select the type of weather event to benchmark for <strong>{selectedRegion.display_name}</strong>.</p>
          </div>
        </div>
      </header>
      <hr class="divider" />

      <div class="event-type-grid">
        {#each EVENT_TYPES as et}
          <button
            type="button"
            class="event-type-card"
            class:coming-soon={et.status === "coming_soon"}
            disabled={et.status === "coming_soon"}
            onclick={() => { selectedEventType = et.id; }}
          >
            <div class="etc-top">
              <span class="etc-name">{et.name}</span>
              {#if et.status === "coming_soon"}
                <span class="etc-soon-badge">Coming soon</span>
              {:else}
                <span class="etc-active-badge">Available</span>
              {/if}
            </div>
            <p class="etc-desc">{et.description}</p>
            {#if et.onsetDefinition}
              <p class="etc-onset"><span class="etc-onset-label">Onset</span>{et.onsetDefinition}</p>
            {/if}
            <div class="etc-regions">
              {#each et.regions as region}
                <span class="etc-region-chip">{region}</span>
              {/each}
            </div>
          </button>
        {/each}
      </div>

    {:else if store.showForm && selectedRegion && selectedEventType}
      <!-- ---- Step 3: Configure & run ---- -->
      {@const eventTypeMeta = EVENT_TYPES.find(e => e.id === selectedEventType)}
      <header class="detail-header">
        <div class="detail-header-row">
          <button class="back-btn" onclick={() => { selectedEventType = null; }} title="Back to event type selection">← Back</button>
          <div>
            <p class="detail-eyebrow">New Benchmark · Step 3 of 3 · {selectedRegion.display_name}</p>
            <h1 class="detail-title">Configure Benchmark</h1>
            <p class="detail-event-type">{eventTypeMeta?.name ?? selectedEventType}</p>
          </div>
        </div>
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
                  <option value="">{dataLoaded ? "No datasets available" : "Loading…"}</option>
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
            <p class="loading-hint">{dataLoaded ? "No models available." : "Loading models…"}</p>
          {:else}
            <div class="model-chip-grid">
              {#each models as m}
                {@const info = lookupModel(m.id)}
                <button
                  type="button"
                  class="model-chip"
                  class:active={selectedModelIds.includes(m.id)}
                  onclick={() => toggleModel(m.id)}
                  title={info?.desc}
                >
                  <span class="chip-name">{m.display_name}</span>
                  <span class="chip-meta">
                    {info?.type ?? m.model_type} · {info?.resolution ?? ""}
                    {m.probabilistic ? ` · ${m.members ?? "?"} mbr` : ""}
                  </span>
                  <span class="chip-years">{m.start_date.slice(0,4)}–{m.end_date.slice(0,4)}</span>
                </button>
              {/each}
            </div>

            <details class="model-reference">
              <summary>Model reference</summary>
              <div class="model-ref-body">
                {#each models as m}
                  {@const info = lookupModel(m.id)}
                  <div class="model-ref-row" class:ref-selected={selectedModelIds.includes(m.id)}>
                    <div class="ref-header">
                      <span class="ref-name">{m.display_name}</span>
                      <span class="ref-badge ref-badge-{(info?.type ?? m.model_type).toLowerCase()}">{info?.type ?? m.model_type}</span>
                      <span class="ref-forecast">{info?.forecast ?? (m.probabilistic ? `Probabilistic · ${m.members ?? "?"} members` : "Deterministic")}</span>
                      <span class="ref-res">{info?.resolution ?? "—"}</span>
                      <span class="ref-period">{info?.period ?? `${m.start_date.slice(0,4)}–${m.end_date.slice(0,4)}`}</span>
                    </div>
                    {#if info?.desc}
                      <p class="ref-desc">{info.desc}</p>
                    {/if}
                  </div>
                {/each}
              </div>
            </details>
          {/if}
        </fieldset>

        <fieldset>
          <legend>Options</legend>
          <div class="field-row">
            <label><span class="label-text">Max Forecast Day <span class="tip" data-tip="Cap the lead time evaluated (days). Leave blank to include all available forecast days.">ⓘ</span></span>
              <input type="number" bind:value={form.maxForecastDay} placeholder="optional" />
            </label>
          </div>
        </fieldset>

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
                  <label><span class="label-text">Start Date <span class="tip" data-tip="Start of the evaluation window for this model.">ⓘ</span></span>
                    <input
                      type="date"
                      value={getOverride(modelId, "start_date", cfg?.start_date ?? "")}
                      oninput={(e) => setOverride(modelId, "start_date", (e.target as HTMLInputElement).value)}
                      required
                    />
                  </label>
                  <label><span class="label-text">End Date <span class="tip" data-tip="End of the evaluation window for this model.">ⓘ</span></span>
                    <input
                      type="date"
                      value={getOverride(modelId, "end_date", cfg?.end_date ?? "")}
                      oninput={(e) => setOverride(modelId, "end_date", (e.target as HTMLInputElement).value)}
                      required
                    />
                  </label>
                  <label><span class="label-text">Clim Start Year <span class="tip" data-tip="First year of the climatological reference period for onset threshold computation.">ⓘ</span></span>
                    <input
                      type="number"
                      value={getOverride(modelId, "start_year_clim", cfg?.start_year_clim ?? "")}
                      oninput={(e) => setOverride(modelId, "start_year_clim", (e.target as HTMLInputElement).value)}
                    />
                  </label>
                  <label><span class="label-text">Clim End Year <span class="tip" data-tip="Last year of the climatological reference period. Must cover the evaluation years.">ⓘ</span></span>
                    <input
                      type="number"
                      value={getOverride(modelId, "end_year_clim", cfg?.end_year_clim ?? "")}
                      oninput={(e) => setOverride(modelId, "end_year_clim", (e.target as HTMLInputElement).value)}
                    />
                  </label>
                  <label><span class="label-text">Init Days <span class="tip" data-tip="Comma-separated initialization day offsets within each week. '0,3' = Mon/Thu.">ⓘ</span></span>
                    <input
                      value={getOverride(modelId, "init_days", cfg?.init_days ?? "")}
                      oninput={(e) => setOverride(modelId, "init_days", (e.target as HTMLInputElement).value)}
                    />
                  </label>
                  <label class="checkbox-label">
                    <input
                      type="checkbox"
                      checked={getOverride(modelId, "parallel", !cfg?.probabilistic)}
                      onchange={(e) => setOverride(modelId, "parallel", (e.target as HTMLInputElement).checked)}
                    />
                    <span class="label-text">Parallel <span class="tip" data-tip="Run years concurrently. On by default for deterministic models; disable for large ensemble models if jobs run out of memory.">ⓘ</span></span>
                  </label>
                  <label class="checkbox-label">
                    <input
                      type="checkbox"
                      checked={getOverride(modelId, "probabilistic", cfg?.probabilistic ?? false)}
                      onchange={(e) => setOverride(modelId, "probabilistic", (e.target as HTMLInputElement).checked)}
                    />
                    <span class="label-text">Probabilistic <span class="tip" data-tip="Compute probabilistic metrics (Brier Score, RPS, AUC) in addition to deterministic ones.">ⓘ</span></span>
                  </label>
                  {#if getOverride(modelId, "probabilistic", cfg?.probabilistic ?? false)}
                    <label><span class="label-text">Members <span class="tip" data-tip="Number of ensemble members to use. Enter a count (e.g. '11', '51') or 'All'.">ⓘ</span></span>
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
              <label><span class="label-text">Observations <span class="tip" data-tip="Override the path to the observation data directory. Leave blank to use the selected dataset's default location.">ⓘ</span></span>
                <input bind:value={form.obs} />
              </label>
              <label><span class="label-text">File Pattern <span class="tip" data-tip="Override the filename pattern used to locate observation files, e.g. 'YYYY_MM.nc'. Leave blank to use the dataset default.">ⓘ</span></span>
                <input bind:value={form.obsFilePattern} />
              </label>
              <label><span class="label-text">Variable <span class="tip" data-tip="Variable name to read from observation files (e.g. 'tp' for total precipitation). Leave blank to use the dataset default.">ⓘ</span></span>
                <input bind:value={form.obsVar} />
              </label>
            </div>
          </fieldset>
          <fieldset class="nested-fieldset">
            <legend>Wet / Dry Spell</legend>
            <div class="field-row">
              <label><span class="label-text">Wet Threshold <span class="tip" data-tip="Minimum daily rainfall (mm) to classify a day as wet. Default is 1 mm/day for both India and Ethiopia onset definitions.">ⓘ</span></span>
                <input type="number" step="any" bind:value={form.wetThreshold} />
              </label>
              <label><span class="label-text">Wet Spell <span class="tip" data-tip="Required length (days) of consecutive wet days to qualify as an onset-triggering wet spell.">ⓘ</span></span>
                <input type="number" bind:value={form.wetSpell} />
              </label>
              <label><span class="label-text">Dry Spell <span class="tip" data-tip="Maximum allowed dry spell length (days) following onset before it is invalidated. Used in the Moron–Robertson India definition.">ⓘ</span></span>
                <input type="number" bind:value={form.drySpell} />
              </label>
            </div>
          </fieldset>
          <fieldset class="nested-fieldset">
            <legend>Masks &amp; Thresholds</legend>
            <div class="field-row">
              <label class="grow"><span class="label-text">Mask File <span class="tip" data-tip="Path to a NetCDF mask file. Grid points outside the mask are excluded from all metric calculations.">ⓘ</span></span>
                <input bind:value={form.ncMask} />
              </label>
              <label class="grow"><span class="label-text">Threshold File <span class="tip" data-tip="Path to a precomputed threshold file. Overrides the climatology-derived wet-spell threshold used in onset detection.">ⓘ</span></span>
                <input bind:value={form.threshFile} />
              </label>
            </div>
          </fieldset>
        </details>

        <div class="tips-panel">
          <p class="tips-heading">Quick start tips</p>
          <ul class="tips-list">
            <li>Select multiple models to compare them side by side in the same run set.</li>
            <li>Each model's evaluation dates are pre-filled from its hindcast coverage — adjust per model if needed.</li>
            <li>Clim years define the baseline for onset threshold computation and must cover the evaluation years.</li>
            <li>Most models initialize twice weekly (Mon/Thu) — init days "0,3" reflects this.</li>
            <li>Disable Parallel for large probabilistic models (e.g. GenCast) if jobs are running out of memory.</li>
          </ul>
        </div>

        {#if submitError}
          <p class="form-error">{submitError}</p>
        {/if}

        <button class="btn-submit" type="submit" disabled={submitting || selectedModelIds.length === 0}>
          {submitting ? "Submitting…" : `Run ${selectedModelIds.length > 1 ? selectedModelIds.length + " Models" : "Benchmark"}`}
        </button>
      </form>

    {:else if store.selectedGroup}
      <!-- ---- Benchmark Results ---- -->
      {@const group = store.selectedGroup}
      <header class="detail-header">
        <div>
          <p class="detail-eyebrow">Benchmark</p>
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
      {@const failedJobs = group.jobs.filter((j) => j.status === "failed")}

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

  .sidebar-section {
    margin-top: 0.5rem;
  }
  .sidebar-section > summary {
    cursor: pointer;
    list-style: none;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.15rem 0.25rem;
    border-radius: 3px;
    user-select: none;
  }
  .sidebar-section > summary:hover { background: var(--color-surface-raised); }
  .sidebar-section > summary::before {
    content: "▶";
    font-size: 0.5rem;
    color: var(--color-text-muted);
    transition: transform 0.15s;
    flex-shrink: 0;
  }
  .sidebar-section[open] > summary::before { transform: rotate(90deg); }

  .sidebar-title {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--color-text-muted);
    margin: 0;
  }
  .sidebar-count {
    font-size: 0.6rem;
    font-weight: 500;
    color: var(--color-text-muted);
    opacity: 0.7;
  }
  .sidebar-empty {
    font-size: 0.75rem;
    color: var(--color-text-muted);
    padding: 0.4rem 0.5rem;
    opacity: 0.6;
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
  .group-dates { font-size: 0.65rem; color: var(--color-text-muted); font-family: var(--font-mono); }

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
    color: var(--color-text-muted);
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
  .status-badge.running  { background: var(--color-status-running-bg);  color: var(--color-status-running);  }
  .status-badge.complete { background: var(--color-status-complete-bg); color: var(--color-status-complete); }
  .status-badge.failed   { background: var(--color-status-failed-bg);   color: var(--color-status-failed);   }
  .status-badge.mixed    { background: var(--color-border-subtle); color: var(--color-text-muted); }

  /* ---- Main content ---- */
  .main-content {
    flex: 1;
    min-width: 0;
    background: var(--color-surface-raised);
    border: 1px solid var(--color-border);
    border-radius: 0.6rem;
    padding: 2rem;
  }

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
  .detail-event-type {
    font-size: 0.78rem;
    font-weight: 500;
    color: var(--color-text-muted);
    margin: 0.2rem 0 0;
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

  /* ---- Form styles ---- */
  .run-form { display: flex; flex-direction: column; gap: 1.25rem; }

  fieldset {
    border: 1px solid var(--color-border);
    border-radius: 0.4rem;
    padding: 0.75rem 1rem 1rem;
    margin: 0;
  }
  legend {
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--color-accent);
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
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--color-text);
  }
  label.grow { flex: 1; min-width: 140px; }
  label.checkbox-label { flex-direction: row; align-items: center; gap: 0.4rem; font-size: 0.8rem; padding-bottom: 0.15rem; }

  input[type="text"], input:not([type]), input[type="number"], input[type="date"], select {
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--color-border);
    border-radius: 0.3rem;
    background: var(--color-bg);
    color: var(--color-text);
    font-family: var(--font-body);
    font-size: 0.82rem;
    outline: none;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  input:focus, select:focus {
    border-color: var(--color-accent);
    box-shadow: 0 0 0 3px var(--color-accent-light);
  }

  /* ---- Event type picker ---- */
  .detail-subtitle {
    font-size: 0.85rem;
    color: var(--color-text-muted);
    margin: 0.35rem 0 0;
    max-width: 52ch;
    line-height: 1.5;
  }

  .detail-header-row {
    display: flex;
    align-items: flex-start;
    gap: 1rem;
  }

  .back-btn {
    padding: 0.35rem 0.7rem;
    background: none;
    border: 1px solid var(--color-border);
    border-radius: 0.3rem;
    color: var(--color-text-muted);
    font-family: var(--font-body);
    font-size: 0.78rem;
    font-weight: 500;
    cursor: pointer;
    transition: color 0.12s, border-color 0.12s;
    white-space: nowrap;
    margin-top: 0.2rem;
  }
  .back-btn:hover { color: var(--color-accent); border-color: var(--color-accent); }

  .event-type-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 1rem;
  }

  .event-type-card {
    display: flex;
    flex-direction: column;
    gap: 0.65rem;
    padding: 1.25rem 1.25rem 1rem;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: 0.5rem;
    text-align: left;
    cursor: pointer;
    transition: border-color 0.15s, background-color 0.15s, box-shadow 0.15s, transform 0.1s;
    font-family: var(--font-body);
  }
  .event-type-card:not(.coming-soon):not(.no-data):hover {
    border-color: var(--color-accent);
    background: var(--color-surface-raised);
    box-shadow: 0 0 0 3px var(--color-accent-glow), 0 4px 16px rgba(0,0,0,0.2);
    transform: translateY(-2px);
  }
  .event-type-card.coming-soon,
  .event-type-card.no-data {
    opacity: 0.45;
    cursor: default;
  }

  .etc-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .etc-name {
    font-family: var(--font-display);
    font-size: 1.1rem;
    font-weight: 400;
    color: var(--color-text);
  }
  .etc-soon-badge {
    font-size: 0.6rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    padding: 0.15rem 0.45rem;
    border-radius: 0.25rem;
    background: var(--color-border-subtle);
    color: var(--color-text-muted);
    white-space: nowrap;
    flex-shrink: 0;
  }
  .etc-active-badge {
    font-size: 0.6rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    padding: 0.15rem 0.45rem;
    border-radius: 0.25rem;
    background: var(--color-status-complete-bg);
    color: var(--color-status-complete);
    white-space: nowrap;
    flex-shrink: 0;
  }
  .etc-desc {
    margin: 0;
    font-size: 0.78rem;
    color: var(--color-text-muted);
    line-height: 1.5;
    flex: 1;
  }
  .etc-onset {
    margin: 0;
    font-size: 0.72rem;
    color: var(--color-text-muted);
    line-height: 1.4;
    padding: 0.4rem 0.6rem;
    background: var(--color-bg);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.3rem;
  }
  .etc-onset-label {
    font-weight: 700;
    color: var(--color-accent);
    margin-right: 0.4rem;
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
  }
  .etc-regions {
    display: flex;
    gap: 0.35rem;
    flex-wrap: wrap;
    margin-top: auto;
  }
  .etc-region-chip {
    font-size: 0.68rem;
    font-weight: 500;
    padding: 0.15rem 0.5rem;
    border-radius: 1rem;
    background: var(--color-accent-light);
    color: var(--color-accent);
    border: 1px solid var(--color-accent-border);
  }
  .coming-soon .etc-region-chip {
    background: var(--color-border-subtle);
    color: var(--color-text-dim);
    border-color: transparent;
  }

  /* ---- Sidebar event type label ---- */
  .group-event-type {
    font-size: 0.6rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--color-accent);
    margin-bottom: 0.05rem;
  }

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
    padding: 0.45rem 0.9rem;
    border: 1px solid var(--color-border);
    border-radius: 0.35rem;
    background: var(--color-surface);
    color: var(--color-text-muted);
    font-family: var(--font-body);
    cursor: pointer;
    transition: background-color 0.12s, color 0.12s, border-color 0.12s, box-shadow 0.12s;
    text-align: left;
  }
  .model-chip:hover { border-color: var(--color-accent); color: var(--color-accent); box-shadow: 0 0 0 3px var(--color-accent-glow); }
  .model-chip.active {
    background: var(--color-accent-light);
    border-color: var(--color-accent);
    color: var(--color-accent);
  }
  .chip-name { font-size: 0.78rem; font-weight: 600; }
  .chip-meta { font-size: 0.6rem; font-family: var(--font-mono); opacity: 0.65; }
  .chip-years { font-size: 0.62rem; font-family: var(--font-mono); opacity: 0.75; }
  .model-chip.active .chip-years { opacity: 0.9; }
  .model-chip.active .chip-meta { opacity: 0.8; }

  /* ---- Model reference ---- */
  .model-reference {
    margin-top: 0.75rem;
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.35rem;
    overflow: visible;
  }
  .model-reference > summary {
    padding: 0.45rem 0.75rem;
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--color-text-dim);
    cursor: pointer;
    list-style: none;
    user-select: none;
    background: var(--color-surface);
    border-radius: 0.35rem;
    transition: background-color 0.12s;
  }
  .model-reference > summary::-webkit-details-marker { display: none; }
  .model-reference[open] > summary {
    border-bottom: 1px solid var(--color-border-subtle);
    border-radius: 0.35rem 0.35rem 0 0;
  }
  .model-reference > summary:hover { background: var(--color-accent-glow); }

  .model-ref-body {
    display: flex;
    flex-direction: column;
    gap: 0;
  }
  .model-ref-row {
    padding: 0.6rem 0.75rem;
    border-bottom: 1px solid var(--color-border-subtle);
    transition: background-color 0.1s;
  }
  .model-ref-row:last-child { border-bottom: none; }
  .model-ref-row.ref-selected { background: var(--color-accent-light); }

  .ref-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-bottom: 0.2rem;
  }
  .ref-name {
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--color-text);
    min-width: 90px;
  }
  .ref-badge {
    font-size: 0.58rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.1rem 0.35rem;
    border-radius: 0.2rem;
  }
  .ref-badge-nwp  { background: rgba(59, 130, 246, 0.15); color: #93c5fd; }
  .ref-badge-aiwp { background: rgba(52, 211, 153, 0.15); color: var(--color-status-complete); }
  .ref-forecast {
    font-size: 0.7rem;
    color: var(--color-text-muted);
  }
  .ref-res, .ref-period {
    font-size: 0.68rem;
    font-family: var(--font-mono);
    color: var(--color-text-muted);
    padding: 0.05rem 0.35rem;
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 0.2rem;
  }
  .ref-desc {
    margin: 0;
    font-size: 0.72rem;
    color: var(--color-text-muted);
    line-height: 1.4;
  }

  /* ---- Tooltip icon ---- */
  .label-text {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
  }

  .tip {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 0.9rem;
    height: 0.9rem;
    font-size: 0.58rem;
    font-style: normal;
    font-weight: 600;
    color: var(--color-text-muted);
    border: 1px solid var(--color-border);
    border-radius: 50%;
    cursor: help;
    line-height: 1;
    transition: color 0.12s, border-color 0.12s;
    flex-shrink: 0;
    vertical-align: middle;
  }
  .tip:hover {
    color: var(--color-accent);
    border-color: var(--color-accent);
  }
  .tip::after {
    content: attr(data-tip);
    position: absolute;
    bottom: calc(100% + 6px);
    left: 50%;
    transform: translateX(-50%);
    width: 220px;
    padding: 0.45rem 0.6rem;
    background: var(--color-surface-raised);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.35rem;
    font-size: 0.72rem;
    font-weight: 400;
    color: var(--color-text-muted);
    line-height: 1.45;
    white-space: normal;
    box-shadow: 0 4px 12px rgba(0,0,0,0.18);
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s;
    z-index: 1000;
    text-align: left;
  }
  .tip:hover::after {
    opacity: 1;
  }

  /* ---- Tips panel ---- */
  .tips-panel {
    background: var(--color-accent-light);
    border: 1px solid var(--color-accent);
    border-left-width: 3px;
    border-radius: 0.4rem;
    padding: 0.75rem 1rem;
  }
  .tips-heading {
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--color-accent);
    margin: 0 0 0.4rem;
  }
  .tips-list {
    margin: 0;
    padding-left: 1.1rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .tips-list li {
    font-size: 0.78rem;
    color: var(--color-text-muted);
    line-height: 1.4;
  }

  /* ---- Empty state ---- */
  .empty-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--color-text-muted);
    margin: 0 0 0.5rem;
  }

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
    overflow: visible;
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
    border-radius: 0.4rem;
    transition: background-color 0.12s;
  }
  .param-section > summary::-webkit-details-marker { display: none; }
  .param-section[open] > summary {
    border-bottom: 1px solid var(--color-border-subtle);
    border-radius: 0.4rem 0.4rem 0 0;
  }
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
</style>
