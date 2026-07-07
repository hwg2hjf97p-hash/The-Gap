import type { AnalysisResponse, ApiError, DataSource } from "./types";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "https://the-gap-backend.onrender.com";

export class AnalysisError extends Error {
  constructor(
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "AnalysisError";
  }
}

/**
 * Upload a health data file to the backend for causal analysis.
 * Reports upload progress via the onProgress callback (0–100).
 */
export async function analyseFile(
  file: File,
  dataSource: DataSource,
  calendarFile?: File,
  onProgress?: (pct: number) => void,
): Promise<AnalysisResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("data_source", dataSource);
  if (calendarFile) {
    formData.append("calendar_file", calendarFile);
  }

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener("load", () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data as AnalysisResponse);
        } else {
          const err = data as { detail?: ApiError | string };
          const detail = err.detail;
          if (typeof detail === "object" && detail !== null) {
            reject(new AnalysisError(detail.error_code, detail.message));
          } else {
            reject(
              new AnalysisError(
                "SERVER_ERROR",
                typeof detail === "string"
                  ? detail
                  : "Analysis failed. Please try again.",
              ),
            );
          }
        }
      } catch {
        reject(new AnalysisError("PARSE_ERROR", "Unexpected server response."));
      }
    });

    xhr.addEventListener("error", () =>
      reject(
        new AnalysisError(
          "NETWORK_ERROR",
          "Could not reach the server. Check your connection.",
        ),
      ),
    );

    xhr.addEventListener("abort", () =>
      reject(new AnalysisError("ABORTED", "Upload cancelled.")),
    );

    xhr.open("POST", `${API_URL}/analyse`);
    xhr.send(formData);
  });
}

/**
 * Retrieve previously saved results by session_id.
 */
export async function getResults(sessionId: string): Promise<AnalysisResponse> {
  const res = await fetch(`${API_URL}/results/${sessionId}`);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = data?.detail ?? {};
    throw new AnalysisError(
      detail.error_code ?? "NOT_FOUND",
      detail.message ?? "Results not found.",
    );
  }
  return res.json();
}
