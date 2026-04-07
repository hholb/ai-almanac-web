<script>
</script>

<main class="relative min-h-[calc(100vh-3.5rem)] flex items-center justify-center px-7 pt-20 pb-12 overflow-hidden">

  <!-- Atmospheric glows -->
  <div class="glow glow-1" aria-hidden="true"></div>
  <div class="glow glow-2" aria-hidden="true"></div>
  <div class="glow glow-3" aria-hidden="true"></div>

  <div class="relative max-w-[740px] text-center flex flex-col items-center gap-5">
    <h1 class="hero-title">
      AI<br/><em>Almanac</em>
    </h1>

    <div class="ornament flex items-center gap-3">
      <span class="block w-12 h-px bg-gradient-to-r from-transparent via-[var(--color-accent)] to-transparent opacity-40"></span>
      <span class="text-[0.55rem] text-[var(--color-accent)] opacity-50">&#x25C7;</span>
      <span class="block w-12 h-px bg-gradient-to-r from-transparent via-[var(--color-accent)] to-transparent opacity-40"></span>
    </div>

    <p class="subtitle">Human-Centric Regional Climate &amp; Weather Forecasts</p>

    <p class="text-[1rem] text-[var(--color-text-dim)] leading-[1.8] max-w-[460px] mt-2 description-anim">
      Powered by the latest AI weather prediction models to deliver accurate,
      region-specific climate insights with scientific rigour.
    </p>

    <div class="flex gap-3.5 flex-wrap justify-center mt-3 cta-anim">
      <a href="/benchmarks" class="btn-primary">
        View Benchmarks
        <span class="btn-arrow">&rarr;</span>
      </a>
      <a href="/user" class="btn-secondary">Get Started</a>
    </div>
  </div>

  <div class="scroll-hint absolute bottom-8 left-1/2 -translate-x-1/2">
    <span class="scroll-line block w-px h-8 bg-gradient-to-b from-[var(--color-accent)] to-transparent opacity-30"></span>
  </div>
</main>

<style>
  /* Display font — can't be expressed cleanly in Tailwind arbitrary values */
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
    from { opacity: 0; transform: translateY(30px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  /* Buttons — could be reused elsewhere, keep as CSS */
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
    transition: background-color 0.2s, transform 0.15s, box-shadow 0.2s;
  }

  .btn-primary:hover {
    background-color: var(--color-accent-hover);
    transform: translateY(-2px);
    box-shadow: 0 8px 30px -8px rgba(212, 147, 63, 0.35);
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
    transition: border-color 0.2s, color 0.2s, background-color 0.2s;
  }

  .btn-secondary:hover {
    border-color: var(--color-accent-border);
    color: var(--color-accent);
    background-color: var(--color-accent-glow);
  }

  /* Glows — complex positioning and animations */
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
    from { opacity: 0.6; }
    to   { opacity: 1; }
  }

  /* Scroll indicator animation */
  .scroll-hint {
    animation: fadeUp 1s 0.8s cubic-bezier(0.16, 1, 0.3, 1) both;
  }

  .scroll-line {
    animation: scrollPulse 2s ease-in-out infinite;
  }

  @keyframes scrollPulse {
    0%, 100% { opacity: 0.15; transform: scaleY(0.7); }
    50%      { opacity: 0.4;  transform: scaleY(1); }
  }
</style>
