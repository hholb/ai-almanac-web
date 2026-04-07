<script lang="ts">
  import { onMount } from "svelte";
  import { getManager } from "$lib/auth";

  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      console.log("callback: starting handleCodeRedirect");
      const manager = getManager();
      console.log("callback: manager", manager);
      const result = await manager?.handleCodeRedirect();
      console.log("callback: handleCodeRedirect result", result);
      console.log("callback: manager.authenticated", manager?.authenticated);
      console.log("callback: localStorage keys", Object.keys(localStorage));
      const returnTo = sessionStorage.getItem("auth_return_to") ?? "/";
      sessionStorage.removeItem("auth_return_to");
      window.location.replace(returnTo);
    } catch (e) {
      console.error("callback error:", e);
      error = e instanceof Error ? e.message : "Authentication failed.";
    }
  });
</script>

{#if error}
  <div class="error-page">
    <p class="error-title">Authentication Error</p>
    <p class="error-message">{error}</p>
    <a href="/">Return home</a>
  </div>
{:else}
  <div class="loading-page">
    <p>Completing sign in…</p>
  </div>
{/if}

<style>
  .loading-page, .error-page {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: calc(100vh - 3.5rem);
    gap: 0.75rem;
    color: var(--color-text-muted);
    font-size: 0.95rem;
  }

  .error-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--color-text);
  }

  .error-message {
    color: var(--color-danger);
    font-size: 0.875rem;
  }

  a {
    color: var(--color-accent);
    font-weight: 500;
  }
</style>
