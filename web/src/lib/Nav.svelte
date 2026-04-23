<script lang="ts">
	import { page } from '$app/stores';
</script>

<nav
	class="sticky top-0 z-50 border-b border-[var(--color-border-subtle)] bg-[var(--color-bg-glass)] backdrop-blur-[16px]"
	style="backdrop-filter: blur(16px) saturate(1.2); -webkit-backdrop-filter: blur(16px) saturate(1.2);"
>
	<div class="mx-auto flex h-14 max-w-[1160px] items-center justify-between px-7">
		<a
			href="/"
			class="nav-brand flex items-center gap-2.5 no-underline transition-opacity duration-150 hover:opacity-85"
		>
			<span class="text-[0.75rem] text-[var(--color-accent)] opacity-60">&#x25C8;</span>
			<span class="brand-text">AI Almanac</span>
		</a>
		<div class="flex gap-1">
			<a href="/" class:active={$page.url.pathname === '/'}>Home</a>
			<a href="/benchmarks" class:active={$page.url.pathname === '/benchmarks'}>Benchmarks</a>
			<a href="/user" class:active={$page.url.pathname === '/user'}>Account</a>
		</div>
	</div>
</nav>

<style>
	.brand-text {
		font-family: var(--font-display);
		font-size: 1.2rem;
		font-weight: 400;
		font-style: italic;
		color: var(--color-accent);
		letter-spacing: 0.01em;
	}

	/* Nav links — repeated pattern with active pseudo-element */
	div a {
		position: relative;
		padding: 0.4rem 0.85rem;
		border-radius: 0.3rem;
		font-size: 0.8rem;
		font-weight: 500;
		color: var(--color-text-dim);
		text-decoration: none;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		transition:
			color 0.15s,
			background-color 0.15s;
	}

	div a:hover {
		color: var(--color-text-muted);
		background-color: rgba(255, 255, 255, 0.03);
	}

	div a.active {
		color: var(--color-accent);
	}

	div a.active::after {
		content: '';
		position: absolute;
		bottom: -1px;
		left: 50%;
		transform: translateX(-50%);
		width: 16px;
		height: 1px;
		background: var(--color-accent);
		opacity: 0.7;
	}
</style>
