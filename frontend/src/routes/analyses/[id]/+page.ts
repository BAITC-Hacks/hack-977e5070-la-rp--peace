import { redirect } from '@sveltejs/kit';

import { resolve } from '$app/paths';

import type { PageLoad } from './$types';

// The results open on «Изменения» (tz_site.md §6.2).
export const load: PageLoad = ({ params }) => {
	redirect(307, resolve('/analyses/[id]/changes', { id: params.id }));
};
