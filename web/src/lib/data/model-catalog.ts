interface ModelInfo {
  type: string;
  forecast: string;
  resolution: string;
  period: string;
  desc: string;
}

export const MODEL_CATALOG: Record<string, ModelInfo> = {
  ifs:       { type: "NWP",  forecast: "Probabilistic · 11 members", resolution: "~32 km", period: "2004–2023",            desc: "ECMWF's operational Integrated Forecasting System — the primary physics-based NWP baseline." },
  aifsdaily: { type: "AIWP", forecast: "Deterministic",              resolution: "0.25°",  period: "2019–2024",            desc: "ECMWF's AI Weather Prediction model — daily-initialized variant. Same architecture as AIFS but initialized every day." },
  aifs:      { type: "AIWP", forecast: "Deterministic",              resolution: "0.25°",  period: "1965–2018",            desc: "ECMWF's AI Weather Prediction model. Fine-tuned on IFS analyses (2016–2022). Twice-weekly initializations (Mon/Thu)." },
  fuxi:      { type: "AIWP", forecast: "Deterministic",              resolution: "0.25°",  period: "1965–2024",            desc: "Fudan University AI model trained on ERA5 (1979–2017). Twice-weekly initializations on Mondays and Thursdays." },
  graphcast: { type: "AIWP", forecast: "Deterministic",              resolution: "0.25°",  period: "1965–2024",            desc: "Google DeepMind graph neural network model trained on ERA5 (1979–2017). Twice-weekly initializations." },
  gencast:   { type: "AIWP", forecast: "Probabilistic · 51 members", resolution: "0.25°",  period: "1965–1978, 2019–2024", desc: "Google DeepMind generative ensemble model trained on ERA5 (1979–2018). Note the gap in hindcast coverage." },
  fuxis2s:   { type: "AIWP", forecast: "Probabilistic · 51 members", resolution: "1.5°",   period: "2002–2021",            desc: "Fudan University sub-seasonal-to-seasonal model. Coarser resolution optimized for extended-range (weeks 2–4) prediction. Trained on ERA5 (1950–2016)." },
  ngcm:      { type: "AIWP", forecast: "Probabilistic · 51 members", resolution: "2.8°",   period: "1965–2024",            desc: "Google's Neural GCM — hybrid physics-ML architecture trained 2001–2018. Available April–July only. Twice-weekly initializations." },
};

export function lookupModel(id: string): ModelInfo | null {
  const normalized = id.toLowerCase().replace(/[^a-z0-9]/g, "");
  const entry =
    Object.entries(MODEL_CATALOG).find(([k]) => k === normalized) ??
    Object.entries(MODEL_CATALOG).find(([k]) => normalized.startsWith(k));
  return entry?.[1] ?? null;
}
