import { apiClient } from './client'
import type {
  RLModelArtifact,
  RLModelCompareItem,
  RLModelStatus,
  RLTrainingJob,
  RLTrainingRequest,
  RLTrainingResolveRequest,
  RLTrainingResolveResponse,
  RLTrainingScopeOption,
} from '../types/rlTraining'

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

export async function fetchLatestRLTrainingJob(): Promise<RLTrainingJob | null> {
  try {
    const { data } = await apiClient.get('/market/rl/training/jobs/latest')
    return data
  } catch (error: unknown) {
    if (typeof error === 'object' && error !== null && 'response' in error) {
      const response = (error as { response?: { status?: number } }).response
      if (response?.status === 404) {
        return null
      }
    }
    throw error
  }
}

export async function fetchRLModels(): Promise<{ models: RLModelArtifact[] }> {
  const { data } = await apiClient.get('/market/rl/models')
  return data
}

export async function fetchRLModelCompare(): Promise<{ models: RLModelCompareItem[] }> {
  const { data } = await apiClient.get('/market/rl/models/compare')
  return data
}

export async function updateRLModelStatus(modelId: string, status: RLModelStatus): Promise<RLModelArtifact> {
  const { data } = await apiClient.patch(`/market/rl/models/${modelId}/status`, { status })
  return data
}

export async function deleteRLModel(modelId: string): Promise<{ status: string; model_id: string }> {
  const { data } = await apiClient.delete(`/market/rl/models/${modelId}`)
  return data
}
