export const environment = {
  production: true,
  // Use relative path because nginx proxies /api to backend:8080 inside the Docker network
  apiBase: '/api/v1'
};
