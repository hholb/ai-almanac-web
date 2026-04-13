import type { JobResult } from "./api";

export type FigureKind = "spatial_metrics" | "portrait" | "climatology" | "unknown";
export type FigureMetric = "far" | "mr" | "mae" | "multi" | null;
export type FigureWindow = "1-15" | "16-30" | null;

export type ParsedFigure = {
  raw: JobResult;
  kind: FigureKind;
  metric: FigureMetric;
  model: string | null;
  window: FigureWindow;
  label: string;
};

const METRIC_LABELS: Record<string, string> = {
  false_alarm_rate: "FAR",
  far: "FAR",
  miss_rate: "MR",
  mr: "MR",
  mae: "MAE",
  mean_mae: "MAE",
  multi: "All Metrics",
};

const WINDOW_LABELS: Record<string, string> = {
  "1-15": "Days 1–15",
  "16-30": "Days 16–30",
};

// spatial_metrics_{model}_{window}.png  e.g. spatial_metrics_aifs_1-15.png
const SPATIAL_RE = /^spatial_metrics_(.+?)_(1-15|16-30)\.png$/;

// panel_portrait_mae_far_mr_{model}_{maxDay}day.png
const PORTRAIT_RE = /^panel_portrait_mae_far_mr_(.+?)_(\d+)day\.png$/;

// climatology_onset_{years}.png  e.g. climatology_onset_2013-2018.png
const CLIM_RE = /^climatology_onset_(.+?)\.png$/;

export function parseResult(r: JobResult): ParsedFigure {
  const name = r.name;

  let m: RegExpMatchArray | null;

  m = name.match(SPATIAL_RE);
  if (m) {
    const model = m[1];
    const window = m[2] as FigureWindow;
    return {
      raw: r,
      kind: "spatial_metrics",
      metric: "multi", // spatial metrics figures show FAR, MR, MAE together
      model,
      window,
      label: `Spatial Metrics — ${WINDOW_LABELS[window ?? ""] ?? window}`,
    };
  }

  m = name.match(PORTRAIT_RE);
  if (m) {
    const model = m[1];
    const maxDay = m[2];
    return {
      raw: r,
      kind: "portrait",
      metric: "multi",
      model,
      window: null,
      label: `Portrait Heatmap — ${maxDay}-day`,
    };
  }

  m = name.match(CLIM_RE);
  if (m) {
    const years = m[1];
    return {
      raw: r,
      kind: "climatology",
      metric: null,
      model: null,
      window: null,
      label: `Climatological Onset — ${years}`,
    };
  }

  return {
    raw: r,
    kind: "unknown",
    metric: null,
    model: null,
    window: null,
    label: name,
  };
}

export { METRIC_LABELS, WINDOW_LABELS };
