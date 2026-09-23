import { parseCompareParams } from '$lib/diff/anchor';

import type { PageLoad } from './$types';

// `/compare?before=<id>&after=<id>`; the page itself loads both documents, so it can show
// skeletons and wait while one is still being parsed. A missing or malformed id becomes null.
export const load: PageLoad = ({ url }) => parseCompareParams(url.searchParams);
