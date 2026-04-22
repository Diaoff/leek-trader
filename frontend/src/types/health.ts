export interface HealthResponse {
  status: string
  app: string
  environment: string
  tenant: string
  services: {
    api: string
    database: string
    redis: string
  }
}
