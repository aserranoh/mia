# Robot Maia Frontend

Frontend project for robot configuration using:

- Vue 3 + Vite + TypeScript
- PrimeVue (component library)
- Tailwind CSS (styling)
- Axios (HTTP client)

## Setup

1. Install dependencies:

	 ```bash
	 npm install
	 ```

2. Configure API URL:

	 ```bash
	 cp .env.example .env
	 ```

	 Then edit `.env` if needed:

	 ```env
	 VITE_API_BASE_URL=http://localhost:8000
	 ```

3. Run dev server:

	 ```bash
	 npm run dev
	 ```

4. Build for production:

	 ```bash
	 npm run build
	 ```

## Implemented View

The main screen is the robot configuration view in `src/views/RobotConfigurationView.vue` with:

- Selectors:
	- `whisper_model`
	- `language`
	- `gemini_model`
- Text area:
	- `system_prompt`
- Text input:
	- `gemini_key`
- Save button with dirty-state tracking:
	- Enabled only when there are unsaved changes
	- Disabled when there are no changes or while loading/saving

## API Integration

Axios instance:

- `src/services/http.ts`

Configuration service:

- `src/services/configuration.ts`

Expected endpoints:

- `GET /configuration`
- `PATCH /configuration`
- `GET /configuration/options/whisper-models`
- `GET /configuration/options/languages`
- `GET /configuration/options/gemini-models`
