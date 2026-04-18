<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Card from 'primevue/card'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'
import FileNavigator from '../components/FileNavigator.vue'
import {
  fetchConfiguration,
  fetchGeminiModelOptions,
  fetchLanguageOptions,
  fetchWhisperModelOptions,
  saveConfiguration,
} from '../services/configuration'
import type { RobotConfiguration, SelectOption } from '../types/configuration'

const toast = useToast()

const configuration = ref<RobotConfiguration>({
  whisper_model: '',
  language: '',
  system_prompt: '',
  gemini_model: '',
  gemini_key: '',
})
const originalConfiguration = ref<RobotConfiguration | null>(null)
const whisperModelOptions = ref<SelectOption[]>([])
const languageOptions = ref<SelectOption[]>([])
const geminiModelOptions = ref<SelectOption[]>([])
const isLoading = ref(true)
const isSaving = ref(false)

const isDirty = computed(() => {
  if (!originalConfiguration.value) {
    return false
  }

  return JSON.stringify(configuration.value) !== JSON.stringify(originalConfiguration.value)
})

const canSave = computed(() => isDirty.value && !isLoading.value && !isSaving.value)

const cloneConfiguration = (source: RobotConfiguration): RobotConfiguration => ({
  whisper_model: source.whisper_model,
  language: source.language,
  system_prompt: source.system_prompt,
  gemini_model: source.gemini_model,
  gemini_key: source.gemini_key,
})

async function loadData(): Promise<void> {
  isLoading.value = true

  try {
    const [currentConfigResult, whisperModelsResult, languagesResult, geminiModelsResult] = await Promise.allSettled([
      fetchConfiguration(),
      fetchWhisperModelOptions(),
      fetchLanguageOptions(),
      fetchGeminiModelOptions(),
    ])

    if (currentConfigResult.status === 'fulfilled') {
      configuration.value = cloneConfiguration(currentConfigResult.value)
      originalConfiguration.value = cloneConfiguration(currentConfigResult.value)
    } else {
      originalConfiguration.value = cloneConfiguration(configuration.value)
      toast.add({
        severity: 'warn',
        summary: 'Configuration Unavailable',
        detail: 'Current configuration could not be loaded, but option lists were requested.',
        life: 4000,
      })
      console.error(currentConfigResult.reason)
    }

    if (whisperModelsResult.status === 'fulfilled') {
      whisperModelOptions.value = whisperModelsResult.value
    }

    if (languagesResult.status === 'fulfilled') {
      languageOptions.value = languagesResult.value
    }

    if (geminiModelsResult.status === 'fulfilled') {
      geminiModelOptions.value = geminiModelsResult.value
    }

    if (
      whisperModelsResult.status === 'rejected' ||
      languagesResult.status === 'rejected' ||
      geminiModelsResult.status === 'rejected'
    ) {
      toast.add({
        severity: 'error',
        summary: 'Options Load Error',
        detail: 'One or more selector option lists could not be loaded from the API.',
        life: 4000,
      })
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Configuration Load Error',
      detail: 'Could not load configuration or selector options from the API.',
      life: 4000,
    })
    console.error(error)
  } finally {
    isLoading.value = false
  }
}

async function onSave(): Promise<void> {
  if (!canSave.value) {
    return
  }

  isSaving.value = true

  try {
    const updated = await saveConfiguration(configuration.value)
    configuration.value = cloneConfiguration(updated)
    originalConfiguration.value = cloneConfiguration(updated)

    toast.add({
      severity: 'success',
      summary: 'Configuration Saved',
      detail: 'Robot configuration has been updated successfully.',
      life: 2500,
    })
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Save Failed',
      detail: 'Unable to save configuration. Please check API availability and try again.',
      life: 4000,
    })
    console.error(error)
  } finally {
    isSaving.value = false
  }
}

onMounted(() => {
  void loadData()
})
</script>

<template>
  <Toast />

  <main class="mx-auto min-h-screen w-full max-w-5xl px-4 py-8 md:px-8 md:py-12">
    <section
      class="mb-8 rounded-3xl border border-amber-200/50 bg-white/80 p-6 shadow-[0_18px_55px_-30px_rgba(62,44,7,0.48)] backdrop-blur md:p-10"
    >
      <p class="mb-2 text-xs font-semibold uppercase tracking-[0.22em] text-amber-700">
        Maia Robot Control Center
      </p>
      <h1 class="m-0 text-3xl font-black tracking-tight text-neutral-900 md:text-5xl">
        Robot Configuration
      </h1>
      <p class="mt-4 max-w-3xl text-sm text-neutral-600 md:text-base">
        Manage core AI behavior, language selection and Gemini credentials. The Save button is only
        enabled when there are unsaved changes.
      </p>
    </section>

    <Card class="rounded-3xl border border-emerald-200/60 bg-white/85 backdrop-blur">
      <template #content>
        <form class="grid grid-cols-1 gap-6 md:grid-cols-2" @submit.prevent="onSave">
          <div class="flex flex-col gap-2">
            <label class="text-sm font-semibold text-neutral-700" for="whisper-model">
              Whisper Model
            </label>
            <Select
              id="whisper-model"
              v-model="configuration.whisper_model"
              :options="whisperModelOptions"
              option-label="label"
              option-value="value"
              placeholder="Select whisper model"
              :disabled="isLoading"
              class="w-full"
            />
          </div>

          <div class="flex flex-col gap-2">
            <label class="text-sm font-semibold text-neutral-700" for="language">
              Language
            </label>
            <Select
              id="language"
              v-model="configuration.language"
              :options="languageOptions"
              option-label="label"
              option-value="value"
              placeholder="Select language"
              :disabled="isLoading"
              class="w-full"
            />
          </div>

          <div class="flex flex-col gap-2 md:col-span-2">
            <label class="text-sm font-semibold text-neutral-700" for="system-prompt">
              System Prompt
            </label>
            <Textarea
              id="system-prompt"
              v-model="configuration.system_prompt"
              auto-resize
              rows="6"
              placeholder="Type the system prompt for the robot behavior"
              :disabled="isLoading"
              class="w-full"
            />
          </div>

          <div class="flex flex-col gap-2">
            <label class="text-sm font-semibold text-neutral-700" for="gemini-model">
              Gemini Model
            </label>
            <Select
              id="gemini-model"
              v-model="configuration.gemini_model"
              :options="geminiModelOptions"
              option-label="label"
              option-value="value"
              placeholder="Select Gemini model"
              :disabled="isLoading"
              class="w-full"
            />
          </div>

          <div class="flex flex-col gap-2">
            <label class="text-sm font-semibold text-neutral-700" for="gemini-key">
              Gemini Key
            </label>
            <InputText
              id="gemini-key"
              v-model="configuration.gemini_key"
              type="text"
              placeholder="Enter Gemini API key"
              :disabled="isLoading"
              class="w-full"
            />
          </div>

          <div class="md:col-span-2 flex items-center justify-between pt-2">
            <p class="text-sm text-neutral-500">
              <span v-if="isSaving">Saving changes...</span>
              <span v-else-if="isDirty">You have unsaved changes.</span>
              <span v-else>No pending changes.</span>
            </p>
            <Button
              type="submit"
              label="Save"
              icon="pi pi-save"
              :loading="isSaving"
              :disabled="!canSave"
            />
          </div>
        </form>
      </template>
    </Card>

    <FileNavigator />
  </main>
</template>
