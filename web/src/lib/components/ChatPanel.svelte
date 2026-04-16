<script lang="ts">
  import { onMount, tick } from "svelte";
  import { marked } from "marked";
  import DOMPurify from "dompurify";
  import {
    createChatSession,
    getChatSession,
    sendChatMessage,
    type ChatMessage,
    type ChatEvent,
  } from "$lib/api";
  import type { Job } from "$lib/api";

  function renderMarkdown(text: string): string {
    return DOMPurify.sanitize(marked.parse(text) as string);
  }

  interface Props {
    jobs: Job[];
  }

  let { jobs }: Props = $props();

  // Session state
  let sessionId = $state<string | null>(null);
  let messages = $state<ChatMessage[]>([]);
  let input = $state("");
  let sending = $state(false);
  let error = $state<string | null>(null);

  // Streaming assistant turn
  let streamingContent = $state("");
  let activeToolCalls = $state<{ name: string; done: boolean }[]>([]);

  let messagesEl = $state<HTMLElement | null>(null);

  // Create a session scoped to the current jobs when the panel first loads.
  onMount(async () => {
    try {
      const jobIds = jobs.map((j) => j.id);
      const title = jobs.map((j) => j.model_name.toUpperCase()).join(", ");
      const session = await createChatSession(jobIds, title);
      sessionId = session.id;
    } catch (e) {
      error = "Failed to start chat session.";
    }
  });

  // Scroll to bottom whenever messages update.
  $effect(() => {
    messages; streamingContent;
    tick().then(() => {
      if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
    });
  });

  async function submit() {
    if (!input.trim() || sending || !sessionId) return;
    const text = input.trim();
    input = "";
    sending = true;
    error = null;
    streamingContent = "";
    activeToolCalls = [];

    messages = [...messages, { role: "user", content: text }];

    try {
      for await (const event of sendChatMessage(sessionId, text)) {
        if (event.type === "text") {
          streamingContent += event.content;
        } else if (event.type === "tool_call") {
          activeToolCalls = [...activeToolCalls, { name: event.name, done: false }];
        } else if (event.type === "tool_result") {
          activeToolCalls = activeToolCalls.map((tc) =>
            tc.name === event.name && !tc.done ? { ...tc, done: true } : tc
          );
        } else if (event.type === "done") {
          messages = [...messages, { role: "assistant", content: streamingContent }];
          streamingContent = "";
          activeToolCalls = [];
        }
      }
    } catch (e: any) {
      error = e.message ?? "An error occurred.";
    } finally {
      sending = false;
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  const TOOL_LABELS: Record<string, string> = {
    list_jobs: "listing jobs",
    get_job_info: "fetching job info",
    get_job_metrics: "loading metrics",
    get_spatial_summary: "loading spatial summary",
    run_code_sandbox: "running sandbox computation",
    run_code: "running custom analysis",
  };

  function formatToolName(name: string): string {
    return TOOL_LABELS[name] ?? name.replace(/_/g, " ");
  }
</script>

<div class="chat-panel">
  <div class="chat-header">
    <span class="chat-title">AI Analysis</span>
    <span class="chat-subtitle">Ask about these benchmark results</span>
  </div>

  <div class="messages" bind:this={messagesEl}>
    {#if messages.length === 0 && !sending}
      <div class="empty-chat">
        <p>Ask a question about the benchmark results above.</p>
        <div class="suggestions">
          <button class="suggestion" onclick={() => { input = "How do the models compare on false alarm rate?"; submit(); }}>
            How do the models compare on false alarm rate?
          </button>
          <button class="suggestion" onclick={() => { input = "Which model has the best MAE at longer lead times?"; submit(); }}>
            Which model has the best MAE at longer lead times?
          </button>
          <button class="suggestion" onclick={() => { input = "Summarise the key findings from these runs."; submit(); }}>
            Summarise the key findings from these runs.
          </button>
        </div>
      </div>
    {/if}

    {#each messages as msg}
      <div class="message {msg.role}">
        {#if msg.role === "assistant"}
          <div class="message-content prose">{@html renderMarkdown(msg.content)}</div>
        {:else}
          <div class="message-content">{msg.content}</div>
        {/if}
      </div>
    {/each}

    {#if sending}
      {#each activeToolCalls as tc}
        <div class="tool-indicator {tc.done ? 'done' : 'active'}">
          <span class="tool-icon">{tc.done ? "✓" : "⟳"}</span>
          <span>{formatToolName(tc.name)}</span>
        </div>
      {/each}

      {#if streamingContent}
        <div class="message assistant">
          <div class="message-content prose streaming">{@html renderMarkdown(streamingContent)}<span class="cursor">▋</span></div>
        </div>
      {:else if activeToolCalls.length === 0}
        <div class="thinking">
          <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </div>
      {/if}
    {/if}
  </div>

  {#if error}
    <div class="chat-error">{error}</div>
  {/if}

  <div class="input-row">
    <textarea
      bind:value={input}
      onkeydown={handleKeydown}
      placeholder="Ask about the results… (Enter to send, Shift+Enter for newline)"
      rows={2}
      disabled={sending || !sessionId}
    ></textarea>
    <button class="send-btn" onclick={submit} disabled={sending || !input.trim() || !sessionId}>
      {sending ? "…" : "Send"}
    </button>
  </div>
</div>

<style>
  .chat-panel {
    display: flex;
    flex-direction: column;
    border: 1px solid var(--color-border);
    border-radius: 8px;
    overflow: hidden;
    background: var(--color-surface-raised);
    height: calc(100vh - 12rem);
    min-height: 480px;
  }

  .chat-header {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--color-border);
    background: var(--color-surface);
    flex-shrink: 0;
  }

  .chat-title {
    font-weight: 600;
    font-size: 0.875rem;
    color: var(--color-accent);
  }

  .chat-subtitle {
    font-size: 0.8rem;
    color: var(--color-text-muted);
  }

  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .empty-chat {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    color: var(--color-text-muted);
    font-size: 0.875rem;
  }

  .suggestions {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .suggestion {
    text-align: left;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: 6px;
    padding: 0.4rem 0.75rem;
    font-size: 0.8rem;
    cursor: pointer;
    color: var(--color-text);
    transition: background 0.15s;
  }

  .suggestion:hover {
    background: var(--color-border);
  }

  .message {
    max-width: 92%;
    font-size: 0.875rem;
    line-height: 1.6;
  }

  .message.user {
    align-self: flex-end;
  }

  .message.assistant {
    align-self: flex-start;
    width: 100%;
    max-width: 100%;
  }

  .message-content {
    padding: 0.6rem 0.875rem;
    border-radius: 8px;
    word-break: break-word;
  }

  .message.user .message-content {
    background: var(--color-accent);
    color: var(--color-bg);
    border-bottom-right-radius: 2px;
    white-space: pre-wrap;
  }

  .message.assistant .message-content {
    background: var(--color-surface);
    color: var(--color-text);
    border-bottom-left-radius: 2px;
  }

  /* Markdown prose styles for assistant messages */
  .prose :global(p) { margin: 0 0 0.6em; }
  .prose :global(p:last-child) { margin-bottom: 0; }
  .prose :global(strong) { font-weight: 600; }
  .prose :global(em) { font-style: italic; }
  .prose :global(ul), .prose :global(ol) {
    margin: 0.4em 0 0.6em 1.25em;
    padding: 0;
  }
  .prose :global(li) { margin-bottom: 0.2em; }
  .prose :global(h1), .prose :global(h2), .prose :global(h3) {
    font-weight: 600;
    margin: 0.75em 0 0.3em;
    line-height: 1.3;
  }
  .prose :global(h1) { font-size: 1.1em; }
  .prose :global(h2) { font-size: 1em; }
  .prose :global(h3) { font-size: 0.95em; }
  .prose :global(code) {
    font-family: var(--font-mono, monospace);
    font-size: 0.85em;
    background: var(--color-surface-raised);
    padding: 0.15em 0.35em;
    border-radius: 3px;
  }
  .prose :global(pre) {
    background: var(--color-surface-raised);
    border: 1px solid var(--color-border);
    border-radius: 6px;
    padding: 0.75em 1em;
    overflow-x: auto;
    margin: 0.5em 0;
  }
  .prose :global(pre code) {
    background: none;
    padding: 0;
    font-size: 0.82em;
  }
  .prose :global(blockquote) {
    border-left: 3px solid var(--color-accent);
    margin: 0.5em 0;
    padding-left: 0.75em;
    color: var(--color-text-muted);
  }
  .prose :global(table) {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85em;
    margin: 0.5em 0;
  }
  .prose :global(th), .prose :global(td) {
    padding: 0.3em 0.6em;
    border: 1px solid var(--color-border);
    text-align: left;
  }
  .prose :global(th) { font-weight: 600; background: var(--color-surface-raised); }

  .cursor {
    animation: blink 1s step-end infinite;
  }

  @keyframes blink {
    50% { opacity: 0; }
  }

  .tool-indicator {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.75rem;
    color: var(--muted, #64748b);
    padding: 0.2rem 0;
  }

  .tool-indicator.done {
    opacity: 0.5;
  }

  .tool-icon {
    font-size: 0.7rem;
  }

  .thinking {
    display: flex;
    gap: 4px;
    padding: 0.4rem 0;
  }

  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--muted, #94a3b8);
    animation: bounce 1.2s infinite;
  }

  .dot:nth-child(2) { animation-delay: 0.2s; }
  .dot:nth-child(3) { animation-delay: 0.4s; }

  @keyframes bounce {
    0%, 80%, 100% { transform: translateY(0); }
    40% { transform: translateY(-5px); }
  }

  .chat-error {
    padding: 0.5rem 1rem;
    background: #fef2f2;
    color: #b91c1c;
    font-size: 0.8rem;
    border-top: 1px solid #fecaca;
  }

  .input-row {
    display: flex;
    gap: 0.5rem;
    padding: 0.75rem;
    border-top: 1px solid var(--color-border);
    flex-shrink: 0;
  }

  textarea {
    flex: 1;
    resize: none;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--color-border);
    border-radius: 6px;
    font-size: 0.875rem;
    font-family: inherit;
    background: var(--color-surface);
    color: var(--color-text);
    line-height: 1.4;
  }

  textarea:focus {
    outline: none;
    border-color: var(--color-accent);
  }

  textarea:disabled {
    opacity: 0.6;
  }

  .send-btn {
    padding: 0 1rem;
    background: var(--color-accent);
    color: var(--color-bg);
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: opacity 0.15s;
    align-self: flex-end;
    height: 2.25rem;
  }

  .send-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .send-btn:not(:disabled):hover {
    opacity: 0.85;
  }
</style>
