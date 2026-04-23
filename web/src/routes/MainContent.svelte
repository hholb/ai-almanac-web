<script>
</script>

<main
	class="relative flex min-h-[calc(100vh-3.5rem)] items-center justify-center overflow-hidden px-7 pt-20 pb-12"
>
	<!-- Atmospheric glows -->
	<div class="glow glow-1" aria-hidden="true"></div>
	<div class="glow glow-2" aria-hidden="true"></div>
	<div class="glow glow-3" aria-hidden="true"></div>

	<!-- Pressure system: large, left-center (High) -->
	<svg
		class="isobar-svg iso-a"
		aria-hidden="true"
		viewBox="0 0 900 900"
		fill="none"
		xmlns="http://www.w3.org/2000/svg"
	>
		<g transform="rotate(-12 450 450)" stroke="rgba(212,147,63,0.22)" stroke-width="1" fill="none">
			<ellipse cx="450" cy="450" rx="70" ry="50" />
			<ellipse cx="450" cy="450" rx="145" ry="102" />
			<ellipse cx="450" cy="450" rx="225" ry="158" />
			<ellipse cx="450" cy="450" rx="310" ry="218" />
			<ellipse cx="450" cy="450" rx="400" ry="282" />
			<ellipse cx="450" cy="450" rx="440" ry="330" />
		</g>
		<text
			x="450"
			y="455"
			text-anchor="middle"
			font-family="'JetBrains Mono', monospace"
			font-size="14"
			fill="rgba(212,147,63,0.4)"
			letter-spacing="0.12em">H</text
		>
		<path
			d="M 130 560 Q 260 370 460 400 Q 640 428 700 270"
			stroke="rgba(130,168,200,0.15)"
			stroke-width="1.5"
			stroke-dasharray="5 9"
			fill="none"
		/>
		<g stroke="rgba(212,147,63,0.28)" stroke-width="1">
			{#each Array(24) as _, i}
				{@const a = (i / 24) * Math.PI * 2}
				<line
					x1={450 + 440 * Math.cos(a)}
					y1={450 + 330 * Math.sin(a)}
					x2={450 + 455 * Math.cos(a)}
					y2={450 + 342 * Math.sin(a)}
				/>
			{/each}
		</g>
	</svg>

	<!-- Pressure system: smaller, upper-right (Low) -->
	<svg
		class="isobar-svg iso-b"
		aria-hidden="true"
		viewBox="0 0 600 600"
		fill="none"
		xmlns="http://www.w3.org/2000/svg"
	>
		<g transform="rotate(8 300 300)" stroke="rgba(130,168,200,0.2)" stroke-width="1" fill="none">
			<ellipse cx="300" cy="300" rx="55" ry="42" />
			<ellipse cx="300" cy="300" rx="115" ry="88" />
			<ellipse cx="300" cy="300" rx="180" ry="138" />
			<ellipse cx="300" cy="300" rx="248" ry="190" />
			<ellipse cx="300" cy="300" rx="290" ry="232" />
		</g>
		<text
			x="300"
			y="305"
			text-anchor="middle"
			font-family="'JetBrains Mono', monospace"
			font-size="11"
			fill="rgba(130,168,200,0.35)"
			letter-spacing="0.12em">L</text
		>
		<path
			d="M 60 400 Q 160 220 310 260 Q 440 295 490 160"
			stroke="rgba(130,168,200,0.14)"
			stroke-width="1.5"
			stroke-dasharray="4 8"
			fill="none"
		/>
	</svg>

	<!-- Pressure system: medium, lower-right (High) -->
	<svg
		class="isobar-svg iso-c"
		aria-hidden="true"
		viewBox="0 0 700 700"
		fill="none"
		xmlns="http://www.w3.org/2000/svg"
	>
		<g transform="rotate(-20 350 350)" stroke="rgba(212,147,63,0.16)" stroke-width="1" fill="none">
			<ellipse cx="350" cy="350" rx="60" ry="48" />
			<ellipse cx="350" cy="350" rx="125" ry="95" />
			<ellipse cx="350" cy="350" rx="200" ry="152" />
			<ellipse cx="350" cy="350" rx="280" ry="210" />
			<ellipse cx="350" cy="350" rx="340" ry="268" />
		</g>
		<text
			x="350"
			y="355"
			text-anchor="middle"
			font-family="'JetBrains Mono', monospace"
			font-size="12"
			fill="rgba(212,147,63,0.28)"
			letter-spacing="0.12em">H</text
		>
	</svg>

	<!-- Content -->
	<div class="relative flex max-w-[740px] flex-col items-center gap-5 text-center">
		<h1 class="hero-title">
			AI<br /><em>Almanac</em>
		</h1>

		<div class="ornament flex items-center gap-3">
			<span
				class="block h-px w-12 bg-gradient-to-r from-transparent via-[var(--color-accent)] to-transparent opacity-40"
			></span>
			<span class="text-[0.55rem] text-[var(--color-accent)] opacity-50">&#x25C7;</span>
			<span
				class="block h-px w-12 bg-gradient-to-r from-transparent via-[var(--color-accent)] to-transparent opacity-40"
			></span>
		</div>

		<p class="subtitle">Human-Centric Regional Climate &amp; Weather Forecasts</p>

		<p
			class="description-anim mt-2 max-w-[460px] text-[1rem] leading-[1.8] text-[var(--color-text-dim)]"
		>
			Powered by the latest AI weather prediction models to deliver accurate, region-specific
			climate insights with scientific rigour.
		</p>

		<div class="cta-anim mt-3 flex flex-wrap justify-center gap-3.5">
			<a href="/benchmarks" class="btn-primary">
				View Benchmarks
				<span class="btn-arrow">&rarr;</span>
			</a>
			<a href="/user" class="btn-secondary">Get Started</a>
		</div>
	</div>

	<!-- Model marquee -->
	<div class="marquee-wrap" aria-hidden="true">
		<div class="marquee-track">
			{#each Array(4) as _}
				<span class="marquee-item">AIFS</span>
				<span class="marquee-sep">·</span>
				<span class="marquee-item">GraphCast</span>
				<span class="marquee-sep">·</span>
				<span class="marquee-item">FuXi</span>
				<span class="marquee-sep">·</span>
				<span class="marquee-item">FuXi-S2S</span>
				<span class="marquee-sep">·</span>
				<span class="marquee-item">GenCast</span>
				<span class="marquee-sep">·</span>
				<span class="marquee-item">IFS-S2S</span>
				<span class="marquee-sep">·</span>
				<span class="marquee-item">NeuralGCM</span>
				<span class="marquee-sep">·</span>
			{/each}
		</div>
	</div>

	<!-- Scroll hint -->
	<div class="scroll-hint absolute bottom-8 left-1/2 -translate-x-1/2">
		<span
			class="scroll-line block h-8 w-px bg-gradient-to-b from-[var(--color-accent)] to-transparent opacity-30"
		></span>
	</div>
</main>

<style>
	/* ── Hero title ─────────────────────────────────── */
	.hero-title {
		font-family: var(--font-display);
		font-size: clamp(4.5rem, 13vw, 8.5rem);
		font-weight: 400;
		line-height: 0.85;
		letter-spacing: -0.02em;
		color: var(--color-text);
		margin: 0;
		animation: fadeUp 1s cubic-bezier(0.16, 1, 0.3, 1) both;
	}

	.hero-title em {
		font-style: italic;
		color: var(--color-accent);
	}

	/* ── Ornament / subtitle ────────────────────────── */
	.ornament {
		animation: fadeUp 1s 0.15s cubic-bezier(0.16, 1, 0.3, 1) both;
	}

	.subtitle {
		font-size: clamp(0.85rem, 1.8vw, 1rem);
		font-weight: 500;
		color: var(--color-text-muted);
		letter-spacing: 0.12em;
		text-transform: uppercase;
		margin: 0;
		animation: fadeUp 1s 0.2s cubic-bezier(0.16, 1, 0.3, 1) both;
	}

	.description-anim {
		animation: fadeUp 1s 0.3s cubic-bezier(0.16, 1, 0.3, 1) both;
	}

	.cta-anim {
		animation: fadeUp 1s 0.4s cubic-bezier(0.16, 1, 0.3, 1) both;
	}

	@keyframes fadeUp {
		from {
			opacity: 0;
			transform: translateY(30px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	/* ── Buttons ────────────────────────────────────── */
	.btn-primary {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem 1.75rem;
		background-color: var(--color-accent);
		color: var(--color-bg);
		font-size: 0.875rem;
		font-weight: 700;
		border-radius: 0.4rem;
		text-decoration: none;
		letter-spacing: 0.03em;
		transition:
			background-color 0.2s,
			transform 0.15s,
			box-shadow 0.2s;
	}

	.btn-primary:hover {
		background-color: var(--color-accent-hover);
		transform: translateY(-2px);
		box-shadow: 0 8px 30px -8px rgba(212, 147, 63, 0.45);
	}

	.btn-arrow {
		font-size: 1.05rem;
		transition: transform 0.2s;
	}

	.btn-primary:hover .btn-arrow {
		transform: translateX(4px);
	}

	.btn-secondary {
		padding: 0.75rem 1.75rem;
		background-color: transparent;
		color: var(--color-text-muted);
		font-size: 0.875rem;
		font-weight: 600;
		border-radius: 0.4rem;
		border: 1px solid var(--color-border);
		text-decoration: none;
		letter-spacing: 0.03em;
		transition:
			border-color 0.2s,
			color 0.2s,
			background-color 0.2s;
	}

	.btn-secondary:hover {
		border-color: var(--color-accent-border);
		color: var(--color-accent);
		background-color: var(--color-accent-glow);
	}

	/* ── Atmospheric glows ──────────────────────────── */
	.glow {
		position: absolute;
		border-radius: 50%;
		pointer-events: none;
	}

	.glow-1 {
		width: 700px;
		height: 500px;
		top: -150px;
		left: 50%;
		transform: translateX(-50%);
		background: radial-gradient(ellipse, rgba(212, 147, 63, 0.07) 0%, transparent 65%);
		filter: blur(100px);
		animation: glowPulse 8s ease-in-out infinite alternate;
	}

	.glow-2 {
		width: 900px;
		height: 350px;
		bottom: 5%;
		left: 50%;
		transform: translateX(-60%);
		background: radial-gradient(ellipse, rgba(25, 70, 140, 0.1) 0%, transparent 65%);
		filter: blur(100px);
		animation: glowPulse 10s 2s ease-in-out infinite alternate;
	}

	.glow-3 {
		width: 400px;
		height: 400px;
		top: 30%;
		right: -100px;
		background: radial-gradient(ellipse, rgba(212, 147, 63, 0.04) 0%, transparent 70%);
		filter: blur(80px);
		animation: glowPulse 12s 4s ease-in-out infinite alternate;
	}

	@keyframes glowPulse {
		from {
			opacity: 0.6;
		}
		to {
			opacity: 1;
		}
	}

	/* ── Isobar SVGs ────────────────────────────────── */
	.isobar-svg {
		position: absolute;
		pointer-events: none;
	}

	/* Large High — left-center, slow clockwise */
	.iso-a {
		width: 860px;
		height: 860px;
		top: 50%;
		left: -18%;
		transform: translateY(-50%);
		animation: isoRotateCW 150s linear infinite;
	}

	/* Small Low — upper-right, slow counter-clockwise */
	.iso-b {
		width: 520px;
		height: 520px;
		top: -8%;
		right: -6%;
		animation: isoRotateCCW 110s linear infinite;
	}

	/* Medium High — lower-right, very slow clockwise */
	.iso-c {
		width: 600px;
		height: 600px;
		bottom: -15%;
		right: 5%;
		animation: isoRotateCW 180s linear infinite;
	}

	@keyframes isoRotateCW {
		from {
			transform: rotate(0deg);
		}
		to {
			transform: rotate(360deg);
		}
	}

	@keyframes isoRotateCCW {
		from {
			transform: rotate(0deg);
		}
		to {
			transform: rotate(-360deg);
		}
	}

	/* iso-a needs to keep translateY(-50%) during rotation */
	.iso-a {
		animation: isoRotateCW-a 150s linear infinite;
	}

	@keyframes isoRotateCW-a {
		from {
			transform: translateY(-50%) rotate(0deg);
		}
		to {
			transform: translateY(-50%) rotate(360deg);
		}
	}

	/* ── Model marquee ──────────────────────────────── */
	.marquee-wrap {
		position: absolute;
		bottom: 3.5rem;
		left: 0;
		right: 0;
		overflow: hidden;
		/* fade edges */
		mask-image: linear-gradient(to right, transparent 0%, black 12%, black 88%, transparent 100%);
		-webkit-mask-image: linear-gradient(
			to right,
			transparent 0%,
			black 12%,
			black 88%,
			transparent 100%
		);
		animation: fadeUp 1s 0.6s cubic-bezier(0.16, 1, 0.3, 1) both;
	}

	.marquee-track {
		display: flex;
		width: max-content;
		animation: marqueeScroll 30s linear infinite;
		gap: 0;
	}

	.marquee-item {
		font-family: var(--font-mono);
		font-size: 0.7rem;
		font-weight: 500;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--color-text-dim);
		padding: 0 1.4rem;
		white-space: nowrap;
	}

	.marquee-sep {
		font-family: var(--font-mono);
		font-size: 0.7rem;
		color: var(--color-accent);
		opacity: 0.35;
		align-self: center;
	}

	@keyframes marqueeScroll {
		from {
			transform: translateX(0);
		}
		to {
			transform: translateX(-25%);
		}
	}

	/* ── Scroll hint ────────────────────────────────── */
	.scroll-hint {
		animation: fadeUp 1s 0.8s cubic-bezier(0.16, 1, 0.3, 1) both;
	}

	.scroll-line {
		animation: scrollPulse 2s ease-in-out infinite;
	}

	@keyframes scrollPulse {
		0%,
		100% {
			opacity: 0.15;
			transform: scaleY(0.7);
		}
		50% {
			opacity: 0.4;
			transform: scaleY(1);
		}
	}
</style>
