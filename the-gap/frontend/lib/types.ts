export type DataSource = "apple_health" | "whoop";
export type ConfidenceLevel = "strong" | "moderate" | "weak";
export type MetricDirection = "positive" | "negative";

export interface Insight {
  hypothesis_id: string;
  title: string;
  headline: string;
  body: string;
  metric_delta: string;         // e.g. "+4.2"
  metric_unit: string;          // e.g. "ms HRV"
  metric_direction: MetricDirection;
  treatment_label: string;
  outcome_label: string;
  confidence: ConfidenceLevel;
  confidence_label: string;
  confidence_description: string;
  ate: number;
  ci_low: number;
  ci_high: number;
  n_observations: number;
  p_value?: number | null;
  actionable_tip: string;
  share_text: string;
}

export interface DataSummary {
  days: number;
  source: DataSource;
}

export interface AnalysisResponse {
  session_id: string;
  share_url: string;
  data_summary: DataSummary;
  insights: Insight[];
}

export interface ApiError {
  error_code: string;
  message: string;
}

// Upload states used by the upload page
export type UploadState =
  | "idle"
  | "selected"
  | "uploading"
  | "processing"
  | "done"
  | "error";
