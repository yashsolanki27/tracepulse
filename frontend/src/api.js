// TracePulse API client. Base URL and API key come from Vite env vars
// (frontend/.env): VITE_API_BASE_URL, VITE_API_KEY.
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8001";
const API_KEY = import.meta.env.VITE_API_KEY || "";

const headers = (extra = {}) => ({
  "Content-Type": "application/json",
  "X-API-Key": API_KEY,
  ...extra,
});

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: headers(options.headers),
    ...options,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${res.status} ${path}: ${detail}`);
  }
  return res.json();
}

export const listTickets = () => request("/tickets");
export const getTicket = (id) => request(`/tickets/${id}`);
export const assignTicket = (id, engineerId) =>
  request(`/tickets/${id}/assign`, {
    method: "PATCH",
    body: JSON.stringify({ engineer_id: engineerId }),
  });
export const updateTicketStatus = (id, status) =>
  request(`/tickets/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
export const resolveTicket = (id, resolutionText) =>
  request(`/tickets/${id}/resolve`, {
    method: "PATCH",
    body: JSON.stringify({ resolution_text: resolutionText }),
  });

export default request;