export interface RobotConfiguration {
  whisper_model: string
  language: string
  system_prompt: string
  gemini_model: string
  gemini_key: string
  uploaded_files?: UploadedFileMetadata[]
}

export interface SelectOption {
  label: string
  value: string
}

export interface UploadedFileMetadata {
  path: string
  description: string
  content_type?: string | null
}

export interface DirectoryEntry {
  path: string
  type: 'folder' | 'file'
  description: string
}
