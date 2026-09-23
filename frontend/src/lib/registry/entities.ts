import type { Entity } from '$lib/api/registries';

export function entityLabel(id: number, entities: readonly Entity[]): string {
	return `${entities.find((item) => item.id === id)?.name ?? 'Объект не найден'} · #${id}`;
}

/** Only confirmed organisational edges form a path; unknown does not mean a root. */
export function entityPath(entity: Entity, entities: readonly Entity[]): string {
	const byId = new Map(entities.map((item) => [item.id, item]));
	const seen = new Set<number>();
	const parts: string[] = [];
	let current: Entity | undefined = entity;
	while (current) {
		if (seen.has(current.id)) {
			parts.unshift('Цикл в связях');
			break;
		}
		seen.add(current.id);
		parts.unshift(`${current.name} · #${current.id}`);
		if (current.parent_status === 'root') break;
		if (current.parent_status !== 'resolved' || current.parent_id === null) {
			parts.unshift(
				current.parent_status === 'ambiguous'
					? 'Принадлежность неоднозначна'
					: 'Принадлежность не установлена'
			);
			break;
		}
		const parentId: number = current.parent_id;
		current = byId.get(parentId);
		if (!current) parts.unshift(`Родитель #${parentId} не найден`);
	}
	return parts.join(' → ');
}
