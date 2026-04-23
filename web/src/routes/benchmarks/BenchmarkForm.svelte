<script lang="ts">
	import { isAuthenticated } from '$lib/auth-store';
	import { type BenchmarkStore, type MultiRunFormData } from '$lib/benchmarks.svelte';
	import { getModels, type ModelConfig, type Dataset, type Region, type JobParams } from '$lib/api';
	import { EVENT_TYPES } from '$lib/data/event-types';
	import RegionPicker from './RegionPicker.svelte';
	import EventTypePicker from './EventTypePicker.svelte';
	import ModelSelector from './ModelSelector.svelte';
	import PerModelConfig from './PerModelConfig.svelte';

	let {
		store,
		regions,
		datasets,
		dataLoaded,
		onSubmitted
	}: {
		store: BenchmarkStore;
		regions: Region[];
		datasets: Dataset[];
		dataLoaded: boolean;
		onSubmitted: (groupKey: string) => void;
	} = $props();

	let models = $state<ModelConfig[]>([]);

	let form = $state({
		datasetId: '',
		maxForecastDay: null as number | null,
		parallel: true,
		obs: '',
		obsFilePattern: '',
		obsVar: '',
		wetThreshold: null as number | null,
		wetSpell: null as number | null,
		drySpell: null as number | null,
		ncMask: '',
		threshFile: ''
	});

	let selectedRegion = $state<Region | null>(null);
	let selectedDataset = $derived(datasets.find((d) => d.id === form.datasetId) ?? null);
	let selectedModelIds = $state<string[]>([]);
	let perModelOverrides = $state<Record<string, Record<string, string | boolean | number>>>({});
	let submitting = $state(false);
	let submitError = $state<string | null>(null);
	let selectedEventType = $state<string | null>(null);

	$effect(() => {
		if (!$isAuthenticated || !selectedRegion) return;
		const regionId = selectedRegion.id;
		getModels(regionId).then((m) => {
			if (m.length > 0) models = m;
			const firstRegionDataset = datasets.find(
				(d) =>
					d.is_demo &&
					(!selectedRegion ||
						d.name.toLowerCase().includes(selectedRegion!.display_name.toLowerCase()))
			);
			if (firstRegionDataset) {
				form.datasetId = firstRegionDataset.id;
				form.obsFilePattern = firstRegionDataset.obs_file_pattern ?? '';
			}
		});
	});

	function toggleModel(id: string) {
		if (selectedModelIds.includes(id)) {
			selectedModelIds = selectedModelIds.filter((m) => m !== id);
			return;
		}
		const cfg = models.find((m) => m.id === id);
		selectedModelIds = [...selectedModelIds, id];
		if (!cfg) return;

		const obsStart = selectedDataset?.obs_year_start ?? null;
		const obsEnd = selectedDataset?.obs_year_end ?? null;
		const clampYear = (year: number) => {
			let y = year;
			if (obsStart !== null) y = Math.max(y, obsStart);
			if (obsEnd !== null) y = Math.min(y, obsEnd);
			return y;
		};
		const clampDate = (dateStr: string) =>
			String(clampYear(parseInt(dateStr.slice(0, 4)))) + dateStr.slice(4);

		perModelOverrides = {
			...perModelOverrides,
			[id]: {
				start_date: clampDate(cfg.start_date),
				end_date: clampDate(cfg.end_date),
				start_year_clim: clampYear(cfg.start_year_clim),
				end_year_clim: clampYear(cfg.end_year_clim),
				init_days: cfg.init_days,
				parallel: true,
				probabilistic: cfg.probabilistic,
				members: cfg.members ?? '',
				model_var: cfg.model_var !== 'tp' ? cfg.model_var : '',
				file_pattern: cfg.file_pattern !== '{}.nc' ? cfg.file_pattern : ''
			}
		};
	}

	function setOverride(modelId: string, key: string, value: string | boolean | number) {
		perModelOverrides = {
			...perModelOverrides,
			[modelId]: { ...(perModelOverrides[modelId] ?? {}), [key]: value }
		};
	}

	function getOverride<T>(modelId: string, key: string, fallback: T): T {
		const v = perModelOverrides[modelId]?.[key];
		return v !== undefined ? (v as T) : fallback;
	}

	async function handleSubmit() {
		if (selectedModelIds.length === 0) {
			submitError = 'Select at least one model.';
			return;
		}
		submitting = true;
		submitError = null;
		try {
			const sharedParams: JobParams = {
				event_type: selectedEventType ?? 'monsoon_onset',
				region: selectedRegion!.romp_region,
				...(form.maxForecastDay != null && { max_forecast_day: form.maxForecastDay }),
				...(form.obs && { obs: form.obs }),
				...(form.obsFilePattern && { obs_file_pattern: form.obsFilePattern }),
				...(form.obsVar && { obs_var: form.obsVar }),
				...(form.wetThreshold != null && { wet_threshold: form.wetThreshold }),
				...(form.wetSpell != null && { wet_spell: form.wetSpell }),
				...(form.drySpell != null && { dry_spell: form.drySpell }),
				...(form.ncMask && { nc_mask: form.ncMask }),
				...(form.threshFile && { thresh_file: form.threshFile })
			};

			const overrides: Record<string, Partial<JobParams>> = {};
			for (const mid of selectedModelIds) {
				const overrideMap = perModelOverrides[mid] ?? {};
				const o: Partial<JobParams> = {};
				if (overrideMap.start_date) o.start_date = String(overrideMap.start_date);
				if (overrideMap.end_date) o.end_date = String(overrideMap.end_date);
				if (overrideMap.init_days) o.init_days = String(overrideMap.init_days);
				const isProbabilistic = Boolean(overrideMap.probabilistic);
				o.parallel = isProbabilistic ? false : Boolean(overrideMap.parallel ?? true);
				if (overrideMap.model_var) o.model_var = String(overrideMap.model_var);
				if (overrideMap.file_pattern) o.file_pattern = String(overrideMap.file_pattern);
				if (overrideMap.members) o.members = String(overrideMap.members);
				if (overrideMap.probabilistic !== undefined)
					o.probabilistic = Boolean(overrideMap.probabilistic);
				if (overrideMap.start_year_clim != null)
					o.start_year_clim = Number(overrideMap.start_year_clim);
				if (overrideMap.end_year_clim != null) o.end_year_clim = Number(overrideMap.end_year_clim);
				overrides[mid] = o;
			}

			await store.submitRuns({
				datasetId: form.datasetId,
				modelNames: selectedModelIds,
				sharedParams,
				perModelOverrides: overrides
			} satisfies MultiRunFormData);

			const g = store.selectedGroupKey;
			if (g) onSubmitted(g);
		} catch (e) {
			submitError = e instanceof Error ? e.message : 'Submission failed.';
		} finally {
			submitting = false;
		}
	}
</script>

{#if !selectedRegion}
	<!-- Step 1: Region picker -->
	<RegionPicker
		{regions}
		onSelect={(r) => {
			selectedRegion = r;
			selectedModelIds = [];
			perModelOverrides = {};
		}}
	/>
{:else if !selectedEventType}
	<!-- Step 2: Event type picker -->
	<EventTypePicker
		region={selectedRegion}
		onSelect={(id) => {
			selectedEventType = id;
		}}
		onBack={() => {
			selectedRegion = null;
		}}
	/>
{:else}
	<!-- Step 3: Configure & run -->
	{@const eventTypeMeta = EVENT_TYPES.find((e) => e.id === selectedEventType)}
	<header class="detail-header">
		<div class="detail-header-row">
			<button
				class="back-btn"
				onclick={() => {
					selectedEventType = null;
				}}
				title="Back to event type selection">← Back</button
			>
			<div>
				<p class="detail-eyebrow">New Benchmark · Step 3 of 3 · {selectedRegion.display_name}</p>
				<h1 class="detail-title">Configure Benchmark</h1>
				<p class="detail-event-type">{eventTypeMeta?.name ?? selectedEventType}</p>
			</div>
		</div>
	</header>
	<hr class="divider" />

	<form
		class="run-form"
		onsubmit={(e) => {
			e.preventDefault();
			handleSubmit();
		}}
	>
		<fieldset>
			<legend>Dataset</legend>
			<div class="field-row">
				<label class="grow"
					>Observations
					<select
						bind:value={form.datasetId}
						required
						onchange={(e) => {
							const ds = datasets.find((d) => d.id === (e.target as HTMLSelectElement).value);
							form.obsFilePattern = ds?.obs_file_pattern ?? '';
						}}
					>
						{#if datasets.length === 0}
							<option value="">{dataLoaded ? 'No datasets available' : 'Loading…'}</option>
						{:else}
							{@const demoDatasets = datasets.filter(
								(d) =>
									d.is_demo &&
									(!selectedRegion ||
										d.name.toLowerCase().includes(selectedRegion.display_name.toLowerCase()))
							)}
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
			<ModelSelector {models} selectedIds={selectedModelIds} {dataLoaded} onToggle={toggleModel} />
		</fieldset>

		<fieldset>
			<legend>Options</legend>
			<div class="field-row">
				<label
					><span class="label-text"
						>Max Forecast Day <span
							class="tip"
							data-tip="Cap the lead time evaluated (days). Leave blank to include all available forecast days."
							>ⓘ</span
						></span
					>
					<input type="number" bind:value={form.maxForecastDay} placeholder="optional" />
				</label>
			</div>
		</fieldset>

		{#if selectedModelIds.length > 0}
			<details class="param-section" open>
				<summary>Per-model Configuration</summary>
				{#each selectedModelIds as modelId}
					<PerModelConfig
						{modelId}
						cfg={models.find((m) => m.id === modelId)}
						{getOverride}
						{setOverride}
					/>
				{/each}
			</details>
		{/if}

		<details class="param-section">
			<summary>Advanced Options</summary>
			<fieldset class="nested-fieldset">
				<legend>Observation Overrides</legend>
				<div class="field-row">
					<label
						><span class="label-text"
							>Observations <span
								class="tip"
								data-tip="Override the path to the observation data directory. Leave blank to use the selected dataset's default location."
								>ⓘ</span
							></span
						>
						<input bind:value={form.obs} />
					</label>
					<label
						><span class="label-text"
							>File Pattern <span
								class="tip"
								data-tip="Override the filename pattern used to locate observation files, e.g. 'YYYY_MM.nc'. Leave blank to use the dataset default."
								>ⓘ</span
							></span
						>
						<input bind:value={form.obsFilePattern} />
					</label>
					<label
						><span class="label-text"
							>Variable <span
								class="tip"
								data-tip="Variable name to read from observation files (e.g. 'tp' for total precipitation). Leave blank to use the dataset default."
								>ⓘ</span
							></span
						>
						<input bind:value={form.obsVar} />
					</label>
				</div>
			</fieldset>
			<fieldset class="nested-fieldset">
				<legend>Wet / Dry Spell</legend>
				<div class="field-row">
					<label
						><span class="label-text"
							>Wet Threshold <span
								class="tip"
								data-tip="Minimum daily rainfall (mm) to classify a day as wet. Default is 1 mm/day for both India and Ethiopia onset definitions."
								>ⓘ</span
							></span
						>
						<input type="number" step="any" bind:value={form.wetThreshold} />
					</label>
					<label
						><span class="label-text"
							>Wet Spell <span
								class="tip"
								data-tip="Required length (days) of consecutive wet days to qualify as an onset-triggering wet spell."
								>ⓘ</span
							></span
						>
						<input type="number" bind:value={form.wetSpell} />
					</label>
					<label
						><span class="label-text"
							>Dry Spell <span
								class="tip"
								data-tip="Maximum allowed dry spell length (days) following onset before it is invalidated. Used in the Moron–Robertson India definition."
								>ⓘ</span
							></span
						>
						<input type="number" bind:value={form.drySpell} />
					</label>
				</div>
			</fieldset>
			<fieldset class="nested-fieldset">
				<legend>Masks &amp; Thresholds</legend>
				<div class="field-row">
					<label class="grow"
						><span class="label-text"
							>Mask File <span
								class="tip"
								data-tip="Path to a NetCDF mask file. Grid points outside the mask are excluded from all metric calculations."
								>ⓘ</span
							></span
						>
						<input bind:value={form.ncMask} />
					</label>
					<label class="grow"
						><span class="label-text"
							>Threshold File <span
								class="tip"
								data-tip="Path to a precomputed threshold file. Overrides the climatology-derived wet-spell threshold used in onset detection."
								>ⓘ</span
							></span
						>
						<input bind:value={form.threshFile} />
					</label>
				</div>
			</fieldset>
		</details>

		<div class="tips-panel">
			<p class="tips-heading">Quick start tips</p>
			<ul class="tips-list">
				<li>Select multiple models to compare them side by side in the same run set.</li>
				<li>
					Each model's evaluation dates are pre-filled from its hindcast coverage — adjust per model
					if needed.
				</li>
				<li>
					Clim years define the baseline for onset threshold computation and must cover the
					evaluation years.
				</li>
				<li>Most models initialize twice weekly (Mon/Thu) — init days "0,3" reflects this.</li>
				<li>
					Disable Parallel for large probabilistic models (e.g. GenCast) if jobs are running out of
					memory.
				</li>
			</ul>
		</div>

		{#if submitError}
			<p class="form-error">{submitError}</p>
		{/if}

		<button class="btn-submit" type="submit" disabled={submitting || selectedModelIds.length === 0}>
			{submitting
				? 'Submitting…'
				: `Run ${selectedModelIds.length > 1 ? selectedModelIds.length + ' Models' : 'Benchmark'}`}
		</button>
	</form>
{/if}

<style>
	.detail-header {
		margin-bottom: 1.25rem;
	}
	.detail-header-row {
		display: flex;
		align-items: flex-start;
		gap: 1rem;
	}
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
		transition:
			color 0.12s,
			border-color 0.12s;
		white-space: nowrap;
		margin-top: 0.2rem;
	}
	.back-btn:hover {
		color: var(--color-accent);
		border-color: var(--color-accent);
	}
	.divider {
		border: none;
		border-top: 1px solid var(--color-border-subtle);
		margin: 0 0 1.5rem;
	}

	.run-form {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
	}

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
	label.grow {
		flex: 1;
		min-width: 140px;
	}

	input:not([type]),
	input[type='number'],
	select {
		padding: 0.4rem 0.6rem;
		border: 1px solid var(--color-border);
		border-radius: 0.3rem;
		background: var(--color-bg);
		color: var(--color-text);
		font-family: var(--font-body);
		font-size: 0.82rem;
		outline: none;
		transition:
			border-color 0.15s,
			box-shadow 0.15s;
	}
	input:focus,
	select:focus {
		border-color: var(--color-accent);
		box-shadow: 0 0 0 3px var(--color-accent-light);
	}

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
		transition:
			color 0.12s,
			border-color 0.12s;
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
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.18);
		pointer-events: none;
		opacity: 0;
		transition: opacity 0.15s;
		z-index: 1000;
		text-align: left;
	}
	.tip:hover::after {
		opacity: 1;
	}

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
	.param-section > summary::-webkit-details-marker {
		display: none;
	}
	.param-section[open] > summary {
		border-bottom: 1px solid var(--color-border-subtle);
		border-radius: 0.4rem 0.4rem 0 0;
	}
	.param-section > summary:hover {
		background: var(--color-accent-glow);
	}

	.nested-fieldset {
		border: none;
		border-top: 1px solid var(--color-border-subtle);
		border-radius: 0;
		padding: 0.75rem 0.9rem;
		margin: 0;
	}
	.nested-fieldset:first-of-type {
		border-top: none;
	}
	.nested-fieldset legend {
		font-size: 0.65rem;
		color: var(--color-text-dim);
		margin-bottom: 0.5rem;
		padding: 0;
	}

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
		transition:
			background-color 0.12s,
			opacity 0.12s;
	}
	.btn-submit:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.btn-submit:not(:disabled):hover {
		background: var(--color-accent-hover);
	}

	.form-error {
		font-size: 0.8rem;
		color: var(--color-danger);
		margin: 0;
	}
</style>
