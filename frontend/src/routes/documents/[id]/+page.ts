import { parseDocumentId } from '$lib/document/view.svelte';

import type { PageLoad } from './$types';

// Data is loaded by the page itself, so it can show skeletons and poll while parsing runs.
// An id that cannot exist (null) is shown as «Документ не найден», like a deleted document.
export const load: PageLoad = ({ params }) => ({ id: parseDocumentId(params.id) });
