<script lang="ts">
  import { getManager } from "./auth";

  interface Props {
    message?: string;
  }

  let { message = "Sign in to continue." }: Props = $props();

  function login() {
    sessionStorage.setItem("auth_return_to", window.location.pathname);
    getManager()?.login();
  }
</script>

<div class="flex flex-col items-center justify-center min-h-[calc(100vh-3.5rem)] gap-5">
  <p class="prompt-message">{message}</p>
  <button class="btn-primary" onclick={login}>Sign in with Globus</button>
</div>

<style>
  .prompt-message {
    color: var(--color-text-muted);
    font-family: var(--font-display);
    font-size: 1.2rem;
    font-weight: 400;
    font-style: italic;
    margin: 0;
  }

  .btn-primary {
    padding: 0.65rem 1.6rem;
    background-color: var(--color-accent);
    color: var(--color-bg);
    font-family: var(--font-body);
    font-size: 0.9rem;
    font-weight: 600;
    border-radius: 0.4rem;
    border: none;
    cursor: pointer;
    letter-spacing: 0.03em;
    transition: background-color 0.15s, transform 0.1s;
  }

  .btn-primary:hover {
    background-color: var(--color-accent-hover);
    transform: translateY(-1px);
  }
</style>
