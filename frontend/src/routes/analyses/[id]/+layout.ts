import { loadResult } from '$lib/result/load';

import type { LayoutLoad } from './$types';

// The result of the analysis for all its pages; an unknown id is a 404 «Результат не найден».
export const load: LayoutLoad = ({ params }) => ({ result: loadResult(params.id) });
