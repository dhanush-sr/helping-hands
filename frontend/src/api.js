// Base URL for the backend. Empty in development (Vite proxies /api to FastAPI);
// set VITE_API_BASE_URL at build time when the API lives on another host.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export async function getHealth() {
  const response = await fetch(`${API_BASE_URL}/api/v1/health`)
  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`)
  }
  return response.json()
}
