const API_BASE = "/api";

export function apiUrl(path = "") {
  const value = String(path || "");
  if (value === "/api" || value.startsWith("/api/")) return value;
  return `${API_BASE}${value.startsWith("/") ? value : `/${value}`}`;
}

export function appUrl(path = "/") {
  return new URL(path, window.location.origin).href;
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json().catch(() => ({}));
  }
  return response.text();
}

export async function apiFetch(path, options = {}) {
  let response;
  try {
    response = await fetch(apiUrl(path), {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      },
    });
  } catch (error) {
    throw new Error("Aplikasi tidak dapat terhubung ke backend.", { cause: error });
  }

  const data = await parseResponse(response);
  if (!response.ok) {
    const detail = typeof data === "object" ? data.detail : data;
    throw new Error(detail || `Permintaan gagal (${response.status}).`);
  }
  return data;
}

export function postJson(path, payload = {}) {
  return apiFetch(path, { method: "POST", body: JSON.stringify(payload) });
}

export function getJson(path) {
  return apiFetch(path);
}

function reportAccessToken() {
  try {
    return sessionStorage.getItem("netraware-report-token") || localStorage.getItem("netraware-report-token") || "";
  } catch (error) {
    return "";
  }
}

export function setReportAccessToken(token, remember = false) {
  try {
    const cleanToken = String(token || "").trim();
    sessionStorage.removeItem("netraware-report-token");
    localStorage.removeItem("netraware-report-token");
    if (!cleanToken) return;
    (remember ? localStorage : sessionStorage).setItem("netraware-report-token", cleanToken);
  } catch (error) {
    // Storage tidak wajib; token tetap bisa dikirim melalui query/header manual.
  }
}

export async function downloadFromApi(path, fallbackFilename) {
  const token = reportAccessToken();
  const response = await fetch(apiUrl(path), {
    headers: token ? { "X-Report-Token": token } : {},
  });
  if (!response.ok) {
    const data = await parseResponse(response);
    const detail = typeof data === "object" ? data.detail : data;
    throw new Error(detail || `Unduhan gagal (${response.status}).`);
  }

  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") || "";
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
  const filename = decodeURIComponent(utf8Match?.[1] || plainMatch?.[1] || fallbackFilename);
  const objectUrl = URL.createObjectURL(blob);
  const anchor = Object.assign(document.createElement("a"), { href: objectUrl, download: filename });
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}
