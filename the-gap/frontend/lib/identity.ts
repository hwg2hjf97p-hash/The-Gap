export function getUserId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem("gap_user_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("gap_user_id", id);
  }
  return id;
}

export function getDisplayName(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("gap_display_name") || "";
}

export function setDisplayName(name: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem("gap_display_name", name.trim());
}

export function resetIdentity(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("gap_user_id");
  localStorage.removeItem("gap_display_name");
}
