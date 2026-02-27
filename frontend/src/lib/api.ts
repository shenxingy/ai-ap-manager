import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:8002/api/v1",
});

// Request interceptor — attach Bearer token
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    let raw = localStorage.getItem("auth-storage");
    if (!raw) {
      raw = sessionStorage.getItem("auth-storage");
    }
    if (raw) {
      try {
        const parsed = JSON.parse(raw);
        const token = parsed?.state?.token;
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
      } catch {
        // ignore parse errors
      }
    }
  }
  return config;
});

// Response interceptor — 401 → clear auth + redirect to /login; 4xx/5xx → dispatch error event
api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (typeof window !== "undefined") {
      const status = error.response?.status;

      if (status === 401) {
        localStorage.removeItem("auth-storage");
        sessionStorage.removeItem("auth-storage");
        window.location.href = "/login";
      } else if (status && status >= 400) {
        // Dispatch custom error event for toast handling
        const message = error.response?.data?.detail || error.response?.data?.message || `Error (${status})`;
        window.dispatchEvent(
          new CustomEvent("api-error", {
            detail: { status, message },
          })
        );
      }
    }
    return Promise.reject(error);
  }
);

export default api;
