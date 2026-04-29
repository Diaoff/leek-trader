import { apiClient } from './client'
import type { MarketOverview } from '../types/market'
import type {
  RLModelArtifact,
  RLModelStatus,
  RLTrainingJob,
  RLTrainingRequest,
  RLTrainingResolveRequest,
  RLTrainingResolveResponse,
  RLTrainingScopeOption,
} from '../types/rlTraining'

export async function fetchMarketOverview(): Promise<MarketOverview> {
  const { data } = await apiClient.get('/market/overview')
  return data
}

export async function fetchRLTrainingScopes(): Promise<{ scopes: RLTrainingScopeOption[] }> {
  const { data } = await apiClient.get('/market/rl/training/scopes')
  return data
}

export async function resolveRLTrainingSymbols(payload: RLTrainingResolveRequest): Promise<RLTrainingResolveResponse> {
  const { data } = await apiClient.post('/market/rl/training/resolve', payload)
  return data
}

export async function trainRLModel(payload: RLTrainingRequest): Promise<RLModelArtifact> {
  const { data } = await apiClient.post('/market/rl/training/train', payload)
  return data
}

export async function submitRLTrainingJob(payload: RLTrainingRequest): Promise<RLTrainingJob> {
  const { data } = await apiClient.post('/market/rl/training/jobs', payload)
  return data
}

export async function fetchRLTrainingJob(jobId: string): Promise<RLTrainingJob> {
  const { data } = await apiClient.get(`/market/rl/training/jobs/${jobId}`)
  return data
}

export async function fetchRLModels(): Promise<{ models: RLModelArtifact[] }> {
  const { data } = await apiClient.get('/market/rl/models')
  return data
}

export async function updateRLModelStatus(modelId: string, status: RLModelStatus): Promise<RLModelArtifact> {
  const { data } = await apiClient.patch(`/market/rl/models/${modelId}/status`, { status })
  return data
}
