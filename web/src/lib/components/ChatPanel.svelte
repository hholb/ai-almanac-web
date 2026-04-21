<script lang="ts">
  import { onMount, tick } from "svelte";
  import { marked } from "marked";
  import DOMPurify from "dompurify";
  import {
    createChatSession,
    getChatSessions,
    getChatSession,
    deleteChatSession,
    sendChatMessage,
    type ChatSession,
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

  // Session list
  let sessions = $state<ChatSession[]>([]);
  let sessionId = $state<string | null>(null);
  let messages = $state<ChatMessage[]>([]);
  let input = $state("");
  let sending = $state(false);
  let error = $state<string | null>(null);
  let loadingSession = $state(false);
  let showSessionList = $state(false);

  // Streaming assistant turn
  let streamingContent = $state("");
  let activeToolCalls = $state<{ name: string; done: boolean; code?: string }[]>([]);
  let shownCode = $state<Set<string>>(new Set());

  function toggleCode(key: string) {
    const next = new Set(shownCode);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    shownCode = next;
  }

  // Code snippets collected this turn — appended to messages on done so they persist.
  let pendingSnippets = $state<{ name: string; code: string }[]>([]);

  const CODE_TOOLS = new Set(["run_code_sandbox", "run_code"]);

  async function copyCode(code: string) {
    await navigator.clipboard.writeText(code);
  }

  function extractCodeFromMessage(msg: ChatMessage): { name: string; code: string }[] {
    if (!msg.tool_calls) return [];
    return msg.tool_calls
      .filter((tc) => CODE_TOOLS.has(tc.function.name))
      .map((tc) => {
        try {
          const args = JSON.parse(tc.function.arguments);
          return { name: tc.function.name, code: args.code ?? "" };
        } catch {
          return null;
        }
      })
      .filter((x): x is { name: string; code: string } => x !== null && x.code !== "");
  }

  let messagesEl = $state<HTMLElement | null>(null);

  function handleOutsideClick(e: MouseEvent) {
    if (showSessionList && !(e.target as Element).closest(".session-selector")) {
      showSessionList = false;
    }
  }

  onMount(() => {
    document.addEventListener("click", handleOutsideClick, true);

    (async () => {
      try {
        const all = await getChatSessions();
        sessions = all;
        if (all.length > 0) {
          await loadSession(all[0].id);
        } else {
          await createNewSession();
        }
      } catch (e) {
        error = "Failed to load chat sessions.";
      }
    })();

    return () => document.removeEventListener("click", handleOutsideClick, true);
  });

  async function loadSession(id: string) {
    loadingSession = true;
    error = null;
    try {
      const detail = await getChatSession(id);
      sessionId = id;
      // Keep user messages, assistant text, and assistant tool-call messages that
      // contain code (so sandbox runs are visible in history).
      messages = detail.messages.filter(
        (m) => m.role === "user" ||
          (m.role === "assistant" && (m.content || extractCodeFromMessage(m).length > 0))
      );
    } catch (e) {
      error = "Failed to load session.";
    } finally {
      loadingSession = false;
      showSessionList = false;
    }
  }

  async function createNewSession() {
    error = null;
    try {
      const jobIds = jobs.map((j) => j.id);
      const title = jobs.map((j) => j.model_name.toUpperCase()).join(", ");
      const session = await createChatSession(jobIds, title);
      sessions = [session, ...sessions];
      sessionId = session.id;
      messages = [];
    } catch (e) {
      error = "Failed to create session.";
    }
    showSessionList = false;
  }

  async function handleDeleteSession(id: string, e: MouseEvent) {
    e.stopPropagation();
    try {
      await deleteChatSession(id);
      sessions = sessions.filter((s) => s.id !== id);
      if (sessionId === id) {
        if (sessions.length > 0) {
          await loadSession(sessions[0].id);
        } else {
          await createNewSession();
        }
      }
    } catch {
      error = "Failed to delete session.";
    }
  }

  function currentSession(): ChatSession | undefined {
    return sessions.find((s) => s.id === sessionId);
  }

  function sessionLabel(s: ChatSession): string {
    if (s.title) return s.title;
    return `Chat ${new Date(s.created_at).toLocaleDateString()}`;
  }

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
    pendingSnippets = [];

    messages = [...messages, { role: "user", content: text }];

    try {
      for await (const event of sendChatMessage(sessionId, text)) {
        if (event.type === "text") {
          streamingContent += event.content;
        } else if (event.type === "tool_call") {
          const code = CODE_TOOLS.has(event.name) ? (event.input as any).code as string | undefined : undefined;
          activeToolCalls = [...activeToolCalls, { name: event.name, done: false, code }];
          if (code) pendingSnippets = [...pendingSnippets, { name: event.name, code }];
        } else if (event.type === "tool_result") {
          activeToolCalls = activeToolCalls.map((tc) =>
            tc.name === event.name && !tc.done ? { ...tc, done: true } : tc
          );
        } else if (event.type === "done") {
          // Extract code snippets from the authoritative done.messages payload.
          // This is more reliable than pendingSnippets which depends on tool_call
          // events having correctly-parsed input.
          const doneSnippets: { name: string; code: string }[] = [];
          if (event.messages) {
            for (const m of event.messages) {
              if (m.role === "assistant" && m.tool_calls) {
                for (const tc of m.tool_calls) {
                  if (CODE_TOOLS.has(tc.function.name)) {
                    try {
                      const args = JSON.parse(tc.function.arguments);
                      if (args.code) doneSnippets.push({ name: tc.function.name, code: args.code });
                    } catch { /* skip malformed */ }
                  }
                }
              }
            }
          } else {
            // Fallback: use pendingSnippets if done.messages not available
            doneSnippets.push(...pendingSnippets);
          }
          if (doneSnippets.length > 0) {
            messages = [...messages, { role: "assistant", content: "", tool_calls: doneSnippets.map((s, i) => ({
              id: `local-${i}`, type: "function",
              function: { name: s.name, arguments: JSON.stringify({ code: s.code }) }
            })) }];
          }
          if (streamingContent) {
            messages = [...messages, { role: "assistant", content: streamingContent }];
          }
          streamingContent = "";
          activeToolCalls = [];
          pendingSnippets = [];
          // Update session's message_count in the list
          sessions = sessions.map((s) =>
            s.id === sessionId ? { ...s, message_count: s.message_count + 2, updated_at: new Date().toISOString() } : s
          );
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

  let copyState = $state<"idle" | "copied">("idle");

  async function copyChat() {
    if (messages.length === 0) return;
    const text = messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => `${m.role === "user" ? "You" : "AI"}: ${m.content}`)
      .join("\n\n");
    await navigator.clipboard.writeText(text);
    copyState = "copied";
    setTimeout(() => (copyState = "idle"), 1500);
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
  <!-- Header with session picker -->
  <div class="chat-header">
    <span class="ai-badge">✦ AI</span>
    <div class="session-selector">
      <button
        class="session-current"
        onclick={() => { showSessionList = !showSessionList; }}
        title="Switch session"
      >
        <span class="session-label">
          {#if currentSession()}
            {sessionLabel(currentSession()!)}
          {:else}
            AI Analysis
          {/if}
        </span>
        <span class="session-chevron" class:open={showSessionList}>▾</span>
      </button>

      {#if showSessionList}
        <div class="session-dropdown">
          <button class="session-new-btn" onclick={createNewSession}>
            + New Chat
          </button>
          {#if sessions.length > 0}
            <div class="session-divider"></div>
            {#each sessions as s}
              <div class="session-item" class:active={s.id === sessionId}>
                <button class="session-item-btn" onclick={() => loadSession(s.id)}>
                  <span class="session-item-title">{sessionLabel(s)}</span>
                  <span class="session-item-meta">{s.message_count} msg · {new Date(s.updated_at).toLocaleDateString()}</span>
                </button>
                <button
                  class="session-item-delete"
                  title="Delete"
                  onclick={(e) => handleDeleteSession(s.id, e)}
                >&times;</button>
              </div>
            {/each}
          {/if}
        </div>
      {/if}
    </div>

    <div class="header-actions">
      <button
        class="copy-btn"
        onclick={copyChat}
        disabled={messages.length === 0}
        title="Copy chat to clipboard"
      >
        {copyState === "copied" ? "✓ Copied" : "Copy"}
      </button>
    </div>
  </div>

  <div class="messages" bind:this={messagesEl}>
    {#if loadingSession}
      <div class="loading-msgs">
        <div class="spinner-sm"></div>
        <span>Loading…</span>
      </div>
    {:else if messages.length === 0 && !sending}
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

    {#each messages as msg, i}
      {#if msg.role === "assistant"}
        {@const snippets = extractCodeFromMessage(msg)}
        {#each snippets as snippet, si}
          {@const key = `hist-${i}-${si}`}
          <div class="code-snippet">
            <div class="code-snippet-header">
              <span class="code-snippet-label">{formatToolName(snippet.name)}</span>
              <div class="code-snippet-actions">
                <button class="code-action-btn" onclick={() => copyCode(snippet.code)}>Copy</button>
                <button class="code-action-btn" onclick={() => toggleCode(key)}>
                  {shownCode.has(key) ? "Hide code" : "Show code"}
                </button>
              </div>
            </div>
            {#if shownCode.has(key)}
              <pre class="code-block"><code>{snippet.code}</code></pre>
            {/if}
          </div>
        {/each}
        {#if msg.content}
          <div class="message assistant">
            <div class="message-content prose">{@html renderMarkdown(msg.content)}</div>
          </div>
        {/if}
      {:else}
        <div class="message user">
          <div class="message-content">{msg.content}</div>
        </div>
      {/if}
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
      disabled={sending || !sessionId || loadingSession}
    ></textarea>
    <button class="send-btn" onclick={submit} disabled={sending || !input.trim() || !sessionId || loadingSession}>
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
    flex: 1;
    min-height: 0;
    box-shadow: -4px 0 24px rgba(0,0,0,0.12);
  }

  .chat-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.55rem 0.85rem;
    border-bottom: 1px solid var(--color-border);
    background: linear-gradient(90deg, rgba(212,147,63,0.06) 0%, var(--color-surface) 40%);
    flex-shrink: 0;
    position: relative;
  }

  .ai-badge {
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--color-accent);
    background: var(--color-accent-light);
    border: 1px solid var(--color-accent-border);
    border-radius: 3px;
    padding: 0.15rem 0.4rem;
    flex-shrink: 0;
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
  }

  .copy-btn {
    padding: 0.25rem 0.6rem;
    background: none;
    border: 1px solid var(--color-border);
    border-radius: 4px;
    font-family: inherit;
    font-size: 0.72rem;
    font-weight: 500;
    color: var(--color-text-muted);
    cursor: pointer;
    transition: color 0.12s, border-color 0.12s, background-color 0.12s;
    white-space: nowrap;
  }
  .copy-btn:not(:disabled):hover {
    color: var(--color-accent);
    border-color: var(--color-accent);
    background: var(--color-accent-light);
  }
  .copy-btn:disabled { opacity: 0.35; cursor: default; }

  /* Session selector */
  .session-selector {
    position: relative;
    flex: 1;
    min-width: 0;
  }

  .session-current {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    background: none;
    border: 1px solid var(--color-border);
    border-radius: 5px;
    padding: 0.3rem 0.6rem;
    cursor: pointer;
    color: var(--color-text);
    font-family: inherit;
    font-size: 0.82rem;
    font-weight: 600;
    max-width: 100%;
    transition: border-color 0.15s, background-color 0.15s;
  }
  .session-current:hover {
    border-color: var(--color-accent);
    background: var(--color-accent-light);
  }

  .session-label {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-align: left;
    color: var(--color-accent);
  }

  .session-chevron {
    font-size: 0.7rem;
    color: var(--color-text-muted);
    transition: transform 0.15s;
    flex-shrink: 0;
  }
  .session-chevron.open { transform: rotate(180deg); }

  .session-dropdown {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    min-width: 240px;
    max-width: 340px;
    background: var(--color-surface-raised);
    border: 1px solid var(--color-border);
    border-radius: 7px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.25);
    z-index: 100;
    overflow: hidden;
    padding: 0.4rem;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
  }

  .session-new-btn {
    width: 100%;
    text-align: left;
    padding: 0.45rem 0.65rem;
    background: var(--color-accent);
    color: var(--color-bg);
    border: none;
    border-radius: 5px;
    font-family: inherit;
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.12s;
  }
  .session-new-btn:hover { opacity: 0.85; }

  .session-divider {
    height: 1px;
    background: var(--color-border-subtle);
    margin: 0.25rem 0;
  }

  .session-item {
    display: flex;
    align-items: stretch;
    border-radius: 5px;
    overflow: hidden;
    transition: background-color 0.1s;
  }
  .session-item:hover { background: var(--color-accent-glow); }
  .session-item.active { background: var(--color-accent-light); }

  .session-item-btn {
    flex: 1;
    text-align: left;
    padding: 0.4rem 0.6rem;
    background: none;
    border: none;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    min-width: 0;
  }

  .session-item-title {
    font-size: 0.78rem;
    font-weight: 500;
    color: var(--color-text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .session-item.active .session-item-title { color: var(--color-accent); }

  .session-item-meta {
    font-size: 0.65rem;
    color: var(--color-text-muted);
    font-family: var(--font-mono);
  }

  .session-item-delete {
    padding: 0 0.5rem;
    background: none;
    border: none;
    color: var(--color-text-dim);
    font-size: 0.85rem;
    cursor: pointer;
    border-radius: 0 5px 5px 0;
    transition: color 0.12s, background-color 0.12s;
    flex-shrink: 0;
  }
  .session-item-delete:hover { color: var(--color-danger); background: var(--color-danger-bg); }

  /* Messages */
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .loading-msgs {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--color-text-muted);
    font-size: 0.8rem;
    padding: 0.5rem 0;
  }

  .spinner-sm {
    width: 0.85rem;
    height: 0.85rem;
    border: 1.5px solid var(--color-border-subtle);
    border-top-color: var(--color-accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    flex-shrink: 0;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .empty-chat {
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
    color: var(--color-text-muted);
    font-size: 0.875rem;
    padding: 0.5rem 0;
  }

  .suggestions {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .suggestion {
    text-align: left;
    background: transparent;
    border: 1px solid var(--color-border-subtle);
    border-left: 2px solid var(--color-accent-border);
    border-radius: 5px;
    padding: 0.5rem 0.75rem;
    font-size: 0.8rem;
    cursor: pointer;
    color: var(--color-text-muted);
    transition: border-color 0.15s, color 0.15s, background 0.15s;
    line-height: 1.4;
  }
  .suggestion:hover {
    background: var(--color-accent-glow);
    border-color: var(--color-accent-border);
    border-left-color: var(--color-accent);
    color: var(--color-text);
  }

  .message {
    max-width: 92%;
    font-size: 0.875rem;
    line-height: 1.6;
  }

  .message.user { align-self: flex-end; }
  .message.assistant { align-self: flex-start; width: 100%; max-width: 100%; }

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

  /* Markdown prose styles */
  .prose :global(p) { margin: 0 0 0.6em; }
  .prose :global(p:last-child) { margin-bottom: 0; }
  .prose :global(strong) { font-weight: 600; }
  .prose :global(em) { font-style: italic; }
  .prose :global(ul), .prose :global(ol) { margin: 0.4em 0 0.6em 1.25em; padding: 0; }
  .prose :global(li) { margin-bottom: 0.2em; }
  .prose :global(h1), .prose :global(h2), .prose :global(h3) {
    font-weight: 600; margin: 0.75em 0 0.3em; line-height: 1.3;
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
  .prose :global(pre code) { background: none; padding: 0; font-size: 0.82em; }
  .prose :global(blockquote) {
    border-left: 3px solid var(--color-accent);
    margin: 0.5em 0;
    padding-left: 0.75em;
    color: var(--color-text-muted);
  }
  .prose :global(table) { width: 100%; border-collapse: collapse; font-size: 0.85em; margin: 0.5em 0; }
  .prose :global(th), .prose :global(td) { padding: 0.3em 0.6em; border: 1px solid var(--color-border); text-align: left; }
  .prose :global(th) { font-weight: 600; background: var(--color-surface-raised); }

  .cursor { animation: blink 1s step-end infinite; }
  @keyframes blink { 50% { opacity: 0; } }

  .code-snippet {
    border: 1px solid var(--color-border);
    border-radius: 6px;
    font-size: 0.78rem;
  }

  .code-snippet-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.35rem 0.65rem;
    background: var(--color-surface);
    border-radius: 6px;
    gap: 0.5rem;
  }

  .code-snippet-label {
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--color-accent);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .code-snippet-actions {
    display: flex;
    gap: 0.35rem;
  }

  .code-action-btn {
    padding: 0.15rem 0.5rem;
    background: none;
    border: 1px solid var(--color-border);
    border-radius: 3px;
    font-family: inherit;
    font-size: 0.68rem;
    color: var(--color-text-muted);
    cursor: pointer;
    transition: color 0.12s, border-color 0.12s;
  }
  .code-action-btn:hover { color: var(--color-accent); border-color: var(--color-accent); }

  .code-block {
    margin: 0;
    padding: 0.75rem 1rem;
    background: var(--color-bg);
    border-top: 1px solid var(--color-border);
    overflow-x: auto;
    font-family: var(--font-mono, monospace);
    font-size: 0.78rem;
    line-height: 1.5;
    color: var(--color-text);
    white-space: pre;
  }

  .tool-indicator {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.75rem;
    color: var(--color-text-muted);
    padding: 0.2rem 0;
  }
  .tool-indicator.done { opacity: 0.5; }
  .tool-icon { font-size: 0.7rem; }

  .thinking { display: flex; gap: 4px; padding: 0.4rem 0; }
  .dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--color-text-muted);
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
  textarea:focus { outline: none; border-color: var(--color-accent); }
  textarea:disabled { opacity: 0.6; }

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
  .send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .send-btn:not(:disabled):hover { opacity: 0.85; }
</style>
