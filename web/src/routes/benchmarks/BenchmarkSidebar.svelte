<script lang="ts">
  import { EVENT_TYPES } from "$lib/data/event-types";
  import type { BenchmarkStore } from "$lib/benchmarks.svelte";

  interface Props {
    store: BenchmarkStore;
    onNewBenchmark: () => void;
    onSelectGroup: (key: string) => void;
  }

  const { store, onNewBenchmark, onSelectGroup }: Props = $props();
</script>

<aside class="sidebar">
  <button
    class="new-run-btn"
    class:active={store.showForm}
    onclick={onNewBenchmark}
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
              onclick={() => onSelectGroup(group.key)}
            >
              <span class="group-event-type">{EVENT_TYPES.find((e) => e.id === group.eventType)?.shortName ?? group.eventType}</span>
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

<style>
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

  .sidebar-section { margin-top: 0.5rem; }
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

  .group-event-type {
    font-size: 0.6rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--color-accent);
    margin-bottom: 0.05rem;
  }
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
</style>
