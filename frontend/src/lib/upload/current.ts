import { API_URL, documentsApi } from '$lib/api/client';

import { UPLOAD_SESSION_KEY } from './persistence';
import { UploadSession } from './session.svelte';

/**
 * The files of the analysis being prepared. One session for the whole app, so that the status
 * screen follows the same files after «Начать анализ» and going back to the upload screen keeps
 * them (frontend/HANDOFF.md: preserve the user's selected files).
 */
export const uploadSession = new UploadSession(
	documentsApi,
	() => window.sessionStorage,
	`${UPLOAD_SESSION_KEY}:${API_URL}`
);
