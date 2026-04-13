<script lang="ts">
  import { fetchResultBlob } from "$lib/benchmarks.svelte";
  import type { ParsedFigure } from "$lib/result-parser";

  type Props = {
    figures: ParsedFigure[];
    index: number;
    onclose: () => void;
  };

  let { figures, index = $bindable(), onclose }: Props = $props();

  function prev() { if (index > 0) index--; }
  function next() { if (index < figures.length - 1) index++; }

  function onkeydown(e: KeyboardEvent) {
    if (e.key === "Escape") onclose();
    if (e.key === "ArrowLeft") prev();
    if (e.key === "ArrowRight") next();
  }

  $effect(() => {
    document.addEventListener("keydown", onkeydown);
    return () => document.removeEventListener("keydown", onkeydown);
  });
</script>

<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div class="overlay" onclick={onclose}>
  <div class="box" onclick={(e) => e.stopPropagation()}>
    <button class="close" onclick={onclose} aria-label="Close">&times;</button>

    {#if figures[index]}
      {@const fig = figures[index]}
      <div class="img-wrap">
        {#await fetchResultBlob(fig.raw.url)}
          <div class="loading">Loading…</div>
        {:then src}
          <img {src} alt={fig.label} />
        {:catch}
          <div class="loading">Failed to load image.</div>
        {/await}
      </div>
      <p class="caption">{fig.label}</p>
    {/if}

    <div class="nav">
      <button onclick={prev} disabled={index === 0}>&#8592; Prev</button>
      <span>{index + 1} / {figures.length}</span>
      <button onclick={next} disabled={index === figures.length - 1}>Next &#8594;</button>
    </div>
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    inset: 0;
    z-index: 1000;
    background: rgba(0, 0, 0, 0.85);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.5rem;
  }

  .box {
    position: relative;
    max-width: min(90vw, 1200px);
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    background: var(--color-surface-raised);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.6rem;
    padding: 1.25rem;
    overflow: hidden;
  }

  .close {
    position: absolute;
    top: 0.5rem;
    right: 0.75rem;
    background: none;
    border: none;
    font-size: 1.5rem;
    line-height: 1;
    cursor: pointer;
    color: var(--color-text-dim);
    padding: 0.15rem 0.4rem;
    border-radius: 0.3rem;
    transition: color 0.12s, background-color 0.12s;
  }

  .close:hover { color: var(--color-text); background: var(--color-border-subtle); }

  .img-wrap {
    overflow: auto;
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 1;
    min-height: 0;
  }

  .img-wrap img {
    max-width: 100%;
    max-height: calc(90vh - 9rem);
    display: block;
    border-radius: 0.3rem;
  }

  .loading {
    padding: 3rem;
    color: var(--color-text-dim);
    font-size: 0.9rem;
  }

  .caption {
    font-size: 0.8rem;
    color: var(--color-text-muted);
    margin: 0;
    text-align: center;
  }

  .nav {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1.5rem;
    font-size: 0.8rem;
    color: var(--color-text-muted);
  }

  .nav button {
    background: none;
    border: 1px solid var(--color-border-subtle);
    color: var(--color-text-muted);
    border-radius: 0.3rem;
    padding: 0.25rem 0.7rem;
    cursor: pointer;
    font-size: 0.8rem;
    transition: background-color 0.12s, color 0.12s;
  }

  .nav button:hover:not(:disabled) {
    background: var(--color-accent-light);
    color: var(--color-accent);
  }

  .nav button:disabled { opacity: 0.35; cursor: not-allowed; }
</style>
