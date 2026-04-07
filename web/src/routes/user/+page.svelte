<script lang="ts">
  import { onMount } from "svelte";
  import { getManager } from "$lib/auth";
  import { isAuthenticated } from "$lib/auth-store";

  onMount(() => {
    const manager = getManager();
    if (!manager?.authenticated) {
      sessionStorage.setItem("auth_return_to", "/user");
      manager?.login();
    }
  });

  function logout() {
    getManager()?.revoke();
  }

  let user = $derived(getManager()?.user ?? null);
</script>

{#if $isAuthenticated}
  <div class="flex justify-center px-6 pt-12 min-h-[calc(100vh-3.5rem)]">
    <div class="w-full max-w-[400px] h-fit bg-[var(--color-surface-raised)] border border-[var(--color-border-subtle)] rounded-[0.6rem] p-8 flex flex-col gap-1.5">
      <p class="eyebrow">Account</p>
      <h1 class="name">{user?.name ?? user?.preferred_username ?? "User"}</h1>
      {#if user?.email}
        <p class="text-[0.875rem] text-[var(--color-text-muted)] m-0">{user.email}</p>
      {/if}
      <hr class="border-none border-t border-[var(--color-border-subtle)] my-3" />
      <button class="btn-danger" onclick={logout}>Sign out</button>
    </div>
  </div>
{:else}
  <div class="flex items-center justify-center min-h-[calc(100vh-3.5rem)] text-[var(--color-text-muted)] text-[0.95rem]">
    <p>Redirecting to sign in…</p>
  </div>
{/if}

<style>
  .eyebrow {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--color-accent);
    margin: 0;
    opacity: 0.8;
  }

  .name {
    font-family: var(--font-display);
    font-size: 1.75rem;
    font-weight: 400;
    font-style: italic;
    letter-spacing: -0.01em;
    color: var(--color-text);
    margin: 0;
  }

  .btn-danger {
    align-self: flex-start;
    padding: 0.5rem 1.1rem;
    background: transparent;
    color: var(--color-danger);
    border: 1px solid var(--color-danger-border);
    border-radius: 0.4rem;
    font-family: var(--font-body);
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.12s, border-color 0.12s;
  }

  .btn-danger:hover {
    background-color: var(--color-danger-bg);
    border-color: var(--color-danger);
  }
</style>
