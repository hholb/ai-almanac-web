<script lang="ts">
  import type { Region } from "$lib/api";

  interface Props {
    regions: Region[];
    onSelect: (region: Region) => void;
  }

  const { regions, onSelect }: Props = $props();
</script>

<header class="detail-header">
  <p class="detail-eyebrow">New Benchmark · Step 1 of 3</p>
  <h1 class="detail-title">Choose a Region</h1>
  <p class="detail-subtitle">Select the geographic region for this benchmark. The region determines which observation datasets and onset definitions are available.</p>
</header>
<hr class="divider" />

<div class="card-grid">
  {#each regions as r}
    <button
      type="button"
      class="picker-card"
      class:no-data={!r.has_data}
      onclick={() => { if (r.has_data) onSelect(r); }}
    >
      <div class="card-top">
        <span class="card-name">{r.display_name}</span>
        {#if r.has_data}
          <span class="badge-available">Data available</span>
        {:else}
          <span class="badge-soon">No data configured</span>
        {/if}
      </div>
      <p class="card-desc">{r.description}</p>
    </button>
  {/each}
</div>

<style>
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
  .detail-subtitle {
    font-size: 0.85rem;
    color: var(--color-text-muted);
    margin: 0.35rem 0 0;
    max-width: 52ch;
    line-height: 1.5;
  }
  .divider {
    border: none;
    border-top: 1px solid var(--color-border-subtle);
    margin: 0 0 1.5rem;
  }

  .card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 1rem;
  }

  .picker-card {
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
  .picker-card:not(.no-data):hover {
    border-color: var(--color-accent);
    background: var(--color-surface-raised);
    box-shadow: 0 0 0 3px var(--color-accent-glow), 0 4px 16px rgba(0,0,0,0.2);
    transform: translateY(-2px);
  }
  .picker-card.no-data { opacity: 0.45; cursor: default; }

  .card-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .card-name {
    font-family: var(--font-display);
    font-size: 1.1rem;
    font-weight: 400;
    color: var(--color-text);
  }
  .card-desc {
    margin: 0;
    font-size: 0.78rem;
    color: var(--color-text-muted);
    line-height: 1.5;
    flex: 1;
  }

  .badge-available, .badge-soon {
    font-size: 0.6rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    padding: 0.15rem 0.45rem;
    border-radius: 0.25rem;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .badge-available {
    background: var(--color-status-complete-bg);
    color: var(--color-status-complete);
  }
  .badge-soon {
    background: var(--color-border-subtle);
    color: var(--color-text-muted);
  }
</style>
