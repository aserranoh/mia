import { http } from './http'
import type {
  DirectoryEntry,
  RobotConfiguration,
  SelectOption,
  UploadedFileMetadata,
} from '../types/configuration'

function normalizeOptions(data: string[] | SelectOption[]): SelectOption[] {
  if (data.length === 0) {
    return []
  }

  if (typeof data[0] === 'string') {
    return (data as string[]).map((value) => ({ label: value, value }))
  }

  return data as SelectOption[]
}

export async function fetchConfiguration(): Promise<RobotConfiguration> {
  const { data } = await http.get<RobotConfiguration>('/configuration')
  return data
}

export async function saveConfiguration(
  configuration: Partial<RobotConfiguration>,
): Promise<RobotConfiguration> {
  const { data } = await http.patch<RobotConfiguration>('/configuration', configuration)
  return data
}

export async function fetchWhisperModelOptions(): Promise<SelectOption[]> {
  const { data } = await http.get<string[] | SelectOption[]>('/configuration/options/whisper-models/')
  return normalizeOptions(data)
}

export async function fetchLanguageOptions(): Promise<SelectOption[]> {
  const { data } = await http.get<string[] | SelectOption[]>('/configuration/options/languages/')
  return normalizeOptions(data)
}

export async function fetchGeminiModelOptions(): Promise<SelectOption[]> {
  const { data } = await http.get<string[] | SelectOption[]>('/configuration/options/gemini-models/')
  return normalizeOptions(data)
}

export async function listFolders(): Promise<string[]> {
  const { data } = await http.get<string[]>('/files/folders')
  return data
}

export async function createFolder(path: string, name: string): Promise<string[]> {
  const { data } = await http.post<string[]>('/files/folders/', { path, name })
  return data
}

export async function renameFolder(path: string, newName: string): Promise<string[]> {
  const { data } = await http.patch<string[]>('/files/folders/rename', { path, new_name: newName })
  return data
}

export async function deleteFolder(path: string): Promise<string[]> {
  const { data } = await http.delete<string[]>('/files/folders', { params: { path } })
  return data
}

export async function listUploadedFiles(): Promise<UploadedFileMetadata[]> {
  const { data } = await http.get<UploadedFileMetadata[]>('/files/metadata')
  return data
}

export async function listDirectoryEntries(path: string): Promise<DirectoryEntry[]> {
  const { data } = await http.get<DirectoryEntry[]>('/files/', {
    params: { path },
  })
  return data
}

export async function renameEntry(path: string, newName: string): Promise<DirectoryEntry[]> {
  const { data } = await http.patch<DirectoryEntry[]>('/files/rename', {
    path,
    new_name: newName,
  })
  return data
}

export async function updateFileDescription(
  path: string,
  description: string,
): Promise<DirectoryEntry[]> {
  const { data } = await http.patch<DirectoryEntry[]>('/files/description', {
    path,
    description,
  })
  return data
}

export async function deleteEntry(path: string): Promise<DirectoryEntry[]> {
  const { data } = await http.delete<DirectoryEntry[]>('/files/', {
    params: { path },
  })
  return data
}

export async function uploadFile(
  file: File,
  directory: string,
  description: string,
): Promise<UploadedFileMetadata> {
  const normalizedDirectory = directory === '.' ? '' : directory

  const formData = new FormData()
  formData.append('file', file)
  formData.append('path', normalizedDirectory)
  formData.append('description', description)

  const { data } = await http.post<UploadedFileMetadata>('/files/', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return data
}
