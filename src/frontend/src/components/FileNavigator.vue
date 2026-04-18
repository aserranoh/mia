<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import ContextMenu from 'primevue/contextmenu'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Menu from 'primevue/menu'
import Textarea from 'primevue/textarea'
import { useToast } from 'primevue/usetoast'
import type { MenuItem } from 'primevue/menuitem'
import {
  createFolder,
  deleteEntry,
  listDirectoryEntries,
  renameEntry,
  updateFileDescription,
  uploadFile,
} from '../services/configuration'
import type { DirectoryEntry } from '../types/configuration'

const toast = useToast()

const entries = ref<DirectoryEntry[]>([])
const currentFolder = ref('')
const isLoading = ref(true)
const isMutating = ref(false)
const deletingPath = ref('')

const showCreateDirectoryDialog = ref(false)
const showUploadFileDialog = ref(false)
const showRenameDialog = ref(false)
const showEditDescriptionDialog = ref(false)

const newDirectoryName = ref('')
const uploadDescription = ref('')
const uploadFileRef = ref<File | null>(null)
const renameName = ref('')
const editDescription = ref('')

const selectedContextEntry = ref<DirectoryEntry | null>(null)
const contextMenuSelection = ref<DirectoryEntry | null>(null)

const newMenuRef = ref<{ toggle: (event: Event) => void } | null>(null)
const rowContextMenuRef = ref<{ show: (event: Event) => void } | null>(null)

const breadcrumbs = computed(() => {
  const parts = currentFolder.value ? currentFolder.value.split('/') : []
  const items: Array<{ label: string; path: string }> = [{ label: 'root', path: '' }]

  let cursor = ''
  for (const part of parts) {
    cursor = cursor ? `${cursor}/${part}` : part
    items.push({ label: part, path: cursor })
  }

  return items
})

const newMenuItems = computed<MenuItem[]>(() => [
  {
    label: 'File',
    icon: 'pi pi-upload',
    command: () => {
      uploadFileRef.value = null
      uploadDescription.value = ''
      showUploadFileDialog.value = true
    },
  },
  {
    label: 'Directory',
    icon: 'pi pi-folder-plus',
    command: () => {
      newDirectoryName.value = ''
      showCreateDirectoryDialog.value = true
    },
  },
])

const rowMenuItems = computed<MenuItem[]>(() => [
  {
    label: 'Rename',
    icon: 'pi pi-pencil',
    command: () => {
      if (!selectedContextEntry.value) {
        return
      }
      renameName.value = getEntryName(selectedContextEntry.value)
      showRenameDialog.value = true
    },
  },
  {
    label: 'Edit Description',
    icon: 'pi pi-file-edit',
    visible: selectedContextEntry.value?.type === 'file',
    command: () => {
      if (!selectedContextEntry.value || selectedContextEntry.value.type !== 'file') {
        return
      }
      editDescription.value = selectedContextEntry.value.description ?? ''
      showEditDescriptionDialog.value = true
    },
  },
])

function getPathName(path: string): string {
  const trimmedPath = path.replace(/\/+$/, '')
  if (!trimmedPath) {
    return ''
  }

  const segments = trimmedPath.split('/')
  return segments[segments.length - 1] ?? trimmedPath
}

function getEntryName(entry: DirectoryEntry): string {
  return getPathName(entry.path)
}

function sortEntries(items: DirectoryEntry[]): DirectoryEntry[] {
  return [...items].sort((left, right) => {
    if (left.type !== right.type) {
      return left.type === 'folder' ? -1 : 1
    }
    return getEntryName(left).localeCompare(getEntryName(right))
  })
}

async function loadEntries(): Promise<void> {
  isLoading.value = true

  try {
    const data = await listDirectoryEntries(currentFolder.value)
    entries.value = sortEntries(data)
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Directory Load Error',
      detail: 'Could not load entries for the current folder.',
      life: 4000,
    })
    console.error(error)
  } finally {
    isLoading.value = false
  }
}

async function navigateTo(path: string): Promise<void> {
  currentFolder.value = path
  contextMenuSelection.value = null
  selectedContextEntry.value = null
  await loadEntries()
}

async function onOpenFolder(entry: DirectoryEntry): Promise<void> {
  if (entry.type !== 'folder') {
    return
  }

  await navigateTo(entry.path)
}

function onToggleNewMenu(event: Event): void {
  newMenuRef.value?.toggle(event)
}

function onRowContextMenu(event: { originalEvent: Event; data: DirectoryEntry }): void {
  selectedContextEntry.value = event.data
  contextMenuSelection.value = event.data
  rowContextMenuRef.value?.show(event.originalEvent)
}

function onUploadFileSelected(event: Event): void {
  const target = event.target as HTMLInputElement
  uploadFileRef.value = target.files && target.files.length > 0 ? target.files[0] : null
}

async function onCreateDirectory(): Promise<void> {
  const name = newDirectoryName.value.trim()
  if (!name) {
    return
  }

  isMutating.value = true
  try {
    await createFolder(currentFolder.value, name)
    showCreateDirectoryDialog.value = false
    newDirectoryName.value = ''
    await loadEntries()
    toast.add({
      severity: 'success',
      summary: 'Directory Created',
      detail: 'New directory created successfully.',
      life: 2500,
    })
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Create Directory Failed',
      detail: 'Could not create directory. Please check the name and try again.',
      life: 4000,
    })
    console.error(error)
  } finally {
    isMutating.value = false
  }
}

async function onUploadFile(): Promise<void> {
  if (!uploadFileRef.value) {
    toast.add({
      severity: 'warn',
      summary: 'No File Selected',
      detail: 'Select a file before uploading.',
      life: 3000,
    })
    return
  }

  isMutating.value = true
  try {
    await uploadFile(uploadFileRef.value, currentFolder.value, uploadDescription.value)
    showUploadFileDialog.value = false
    uploadDescription.value = ''
    uploadFileRef.value = null
    await loadEntries()
    toast.add({
      severity: 'success',
      summary: 'File Uploaded',
      detail: 'File uploaded successfully.',
      life: 2500,
    })
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Upload Failed',
      detail: 'Could not upload file. Please try again.',
      life: 4000,
    })
    console.error(error)
  } finally {
    isMutating.value = false
  }
}

async function onRenameSelected(): Promise<void> {
  const selected = selectedContextEntry.value
  const newName = renameName.value.trim()

  if (!selected || !newName) {
    return
  }

  isMutating.value = true
  try {
    await renameEntry(selected.path, newName)
    showRenameDialog.value = false
    renameName.value = ''
    selectedContextEntry.value = null
    contextMenuSelection.value = null
    await loadEntries()
    toast.add({
      severity: 'success',
      summary: 'Entry Renamed',
      detail: `${selected.type === 'folder' ? 'Directory' : 'File'} renamed successfully.`,
      life: 2500,
    })
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Rename Failed',
      detail: 'Could not rename entry. Please check the name and try again.',
      life: 4000,
    })
    console.error(error)
  } finally {
    isMutating.value = false
  }
}

async function onDeleteEntry(entry: DirectoryEntry): Promise<void> {
  deletingPath.value = entry.path
  try {
    await deleteEntry(entry.path)
    if (selectedContextEntry.value?.path === entry.path) {
      selectedContextEntry.value = null
      contextMenuSelection.value = null
    }
    await loadEntries()
    toast.add({
      severity: 'success',
      summary: 'Entry Deleted',
      detail: `${entry.type === 'folder' ? 'Directory' : 'File'} deleted successfully.`,
      life: 2500,
    })
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Delete Failed',
      detail: 'Could not delete entry. Please try again.',
      life: 4000,
    })
    console.error(error)
  } finally {
    deletingPath.value = ''
  }
}

async function onSaveDescription(): Promise<void> {
  const selected = selectedContextEntry.value
  if (!selected || selected.type !== 'file') {
    return
  }

  isMutating.value = true
  try {
    await updateFileDescription(selected.path, editDescription.value)
    showEditDescriptionDialog.value = false
    selectedContextEntry.value = null
    contextMenuSelection.value = null
    await loadEntries()
    toast.add({
      severity: 'success',
      summary: 'Description Updated',
      detail: 'File description updated successfully.',
      life: 2500,
    })
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Update Failed',
      detail: 'Could not update file description. Please try again.',
      life: 4000,
    })
    console.error(error)
  } finally {
    isMutating.value = false
  }
}

onMounted(() => {
  void loadEntries()
})
</script>

<template>
  <section class="mt-8 rounded-3xl border border-sky-200/60 bg-white/85 p-6 backdrop-blur md:p-8">
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="m-0 text-2xl font-bold tracking-tight text-neutral-900">File Navigator</h2>
        <p class="mt-2 text-sm text-neutral-600">
          Click a directory to open it. Right-click any entry to rename it.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Button
          label="Root"
          icon="pi pi-home"
          text
          size="small"
          :disabled="currentFolder === '' || isLoading"
          @click="navigateTo('')"
        />
        <Button
          label="Refresh"
          icon="pi pi-refresh"
          severity="secondary"
          outlined
          :loading="isLoading"
          @click="loadEntries"
        />
        <Button label="New" icon="pi pi-plus" @click="onToggleNewMenu" />
        <Menu ref="newMenuRef" :model="newMenuItems" popup />
      </div>
    </div>

    <div class="mb-4 flex flex-wrap items-center gap-2 text-sm text-neutral-700">
      <span class="font-semibold">Current directory:</span>
      <div class="flex flex-wrap items-center gap-1">
        <Button
          v-for="crumb in breadcrumbs"
          :key="crumb.path || 'root-crumb'"
          :label="crumb.label"
          text
          size="small"
          @click="navigateTo(crumb.path)"
        />
      </div>
    </div>

    <ContextMenu ref="rowContextMenuRef" :model="rowMenuItems" />

    <DataTable
      v-model:contextMenuSelection="contextMenuSelection"
      :value="entries"
      :loading="isLoading"
      contextMenu
      data-key="path"
      stripedRows
      class="overflow-hidden rounded-2xl border border-neutral-200"
      @row-contextmenu="onRowContextMenu"
    >
      <Column header="Name">
        <template #body="{ data }">
          <button
            v-if="data.type === 'folder'"
            type="button"
            class="inline-flex items-center gap-2 rounded-lg px-2 py-1 text-left text-amber-700 hover:bg-amber-50"
            @click="onOpenFolder(data)"
          >
            <i class="pi pi-folder" />
            <span class="font-medium">{{ getEntryName(data) }}</span>
          </button>
          <span v-else class="inline-flex items-center gap-2 px-2 py-1 text-neutral-700">
            <i class="pi pi-file text-sky-600" />
            <span>{{ getEntryName(data) }}</span>
          </span>
        </template>
      </Column>

      <Column field="description" header="Description">
        <template #body="{ data }">
          <span class="text-sm text-neutral-600">{{ data.description || '-' }}</span>
        </template>
      </Column>

      <Column header="Actions" style="width: 7rem">
        <template #body="{ data }">
          <Button
            icon="pi pi-trash"
            severity="danger"
            text
            rounded
            :loading="deletingPath === data.path"
            :disabled="isMutating"
            @click="onDeleteEntry(data)"
          />
        </template>
      </Column>

      <template #empty>
        <span class="text-sm text-neutral-500">This directory is empty.</span>
      </template>
    </DataTable>

    <Dialog
      v-model:visible="showCreateDirectoryDialog"
      modal
      header="Create Directory"
      :style="{ width: '24rem' }"
    >
      <div class="flex flex-col gap-3">
        <label class="text-sm font-semibold text-neutral-700" for="new-directory-name">Name</label>
        <InputText
          id="new-directory-name"
          v-model="newDirectoryName"
          placeholder="new-directory"
          :disabled="isMutating"
          @keyup.enter="onCreateDirectory"
        />
      </div>
      <template #footer>
        <Button
          label="Cancel"
          severity="secondary"
          text
          :disabled="isMutating"
          @click="showCreateDirectoryDialog = false"
        />
        <Button
          label="Create"
          icon="pi pi-check"
          :loading="isMutating"
          :disabled="!newDirectoryName.trim()"
          @click="onCreateDirectory"
        />
      </template>
    </Dialog>

    <Dialog v-model:visible="showUploadFileDialog" modal header="Upload File" :style="{ width: '30rem' }">
      <div class="flex flex-col gap-4">
        <div class="flex flex-col gap-2">
          <label class="text-sm font-semibold text-neutral-700" for="upload-file-input">File</label>
          <input
            id="upload-file-input"
            type="file"
            class="rounded-xl border border-neutral-300 bg-white px-3 py-2 text-sm"
            :disabled="isMutating"
            @change="onUploadFileSelected"
          />
        </div>

        <div class="flex flex-col gap-2">
          <label class="text-sm font-semibold text-neutral-700" for="upload-description">Description</label>
          <Textarea
            id="upload-description"
            v-model="uploadDescription"
            rows="3"
            auto-resize
            placeholder="Optional description"
            :disabled="isMutating"
          />
        </div>
      </div>

      <template #footer>
        <Button
          label="Cancel"
          severity="secondary"
          text
          :disabled="isMutating"
          @click="showUploadFileDialog = false"
        />
        <Button
          label="Upload"
          icon="pi pi-upload"
          :loading="isMutating"
          :disabled="!uploadFileRef"
          @click="onUploadFile"
        />
      </template>
    </Dialog>

    <Dialog v-model:visible="showRenameDialog" modal header="Rename Entry" :style="{ width: '24rem' }">
      <div class="flex flex-col gap-3">
        <label class="text-sm font-semibold text-neutral-700" for="rename-entry-name">New name</label>
        <InputText
          id="rename-entry-name"
          v-model="renameName"
          :disabled="isMutating"
          @keyup.enter="onRenameSelected"
        />
      </div>

      <template #footer>
        <Button
          label="Cancel"
          severity="secondary"
          text
          :disabled="isMutating"
          @click="showRenameDialog = false"
        />
        <Button
          label="Rename"
          icon="pi pi-check"
          :loading="isMutating"
          :disabled="!renameName.trim()"
          @click="onRenameSelected"
        />
      </template>
    </Dialog>

    <Dialog
      v-model:visible="showEditDescriptionDialog"
      modal
      header="Edit File Description"
      :style="{ width: '30rem' }"
    >
      <div class="flex flex-col gap-3">
        <label class="text-sm font-semibold text-neutral-700" for="edit-file-description">
          Description
        </label>
        <Textarea
          id="edit-file-description"
          v-model="editDescription"
          rows="4"
          auto-resize
          :disabled="isMutating"
        />
      </div>

      <template #footer>
        <Button
          label="Cancel"
          severity="secondary"
          text
          :disabled="isMutating"
          @click="showEditDescriptionDialog = false"
        />
        <Button
          label="Save"
          icon="pi pi-check"
          :loading="isMutating"
          @click="onSaveDescription"
        />
      </template>
    </Dialog>
  </section>
</template>
