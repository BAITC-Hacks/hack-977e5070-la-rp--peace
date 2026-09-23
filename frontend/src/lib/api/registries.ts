import { request } from './client';

// Read-only mirrors of api/entities.py and api/activities.py. IDs belong to one document.
export type ExtractionStatus = 'not_started' | 'running' | 'done' | 'needs_review' | 'failed';
export type ReviewStatus = 'pending' | 'checked' | 'needs_review';
export type ParentStatus = 'resolved' | 'root' | 'unknown' | 'ambiguous';
export type ActivityType =
	'goal' | 'task' | 'function' | 'duty' | 'right' | 'prohibition' | 'other';
export type Participation = 'individual' | 'each' | 'joint' | 'alternative' | 'unclear';

export interface RegistrySource {
	node_id: number;
	path: string;
	location: Record<string, unknown>;
	quote: string;
	start: number;
	end: number;
	supports: string[];
}

export interface Entity {
	id: number;
	parent_id: number | null;
	parent_status: ParentStatus;
	parent_candidates: number[];
	name: string;
	aliases: string[];
	entity_type: string;
	category: string;
	position_type: string | null;
	level: string | null;
	roles: { role: string; scope: string | null }[];
	review_status: ReviewStatus;
	sources: RegistrySource[];
}

export interface EntityRelation {
	id: number;
	from_entity_id: number;
	to_entity_id: number;
	relation_type: string;
	conditions: string | null;
	sources: RegistrySource[];
}

export interface Activity {
	id: number;
	block_node_id: number;
	entity_id: number | null;
	entity_name: string | null;
	designation: string;
	record_type: ActivityType;
	formulation: string;
	specificity: 'specific' | 'generalized' | 'needs_clarification';
	participation: Participation;
	participant_designation: string;
	other_participants: { entity_id: number; entity_name: string | null }[];
	condition: string | null;
	deadline: string | null;
	periodicity: string | null;
	note: string | null;
	review_status: ReviewStatus;
	sources: RegistrySource[];
}

export interface ExtractionBlock {
	node_id: number;
	path: string;
	status: 'found' | 'none' | 'needs_clarification' | 'failed';
	message: string | null;
	attempts: number;
}

export interface ExtractionIssue {
	id: number;
	issue_type: string;
	message: string;
	is_blocking: boolean;
	resolved_at: string | null;
	created_at: string;
	entity_id?: number | null;
	relation_id?: number | null;
	record_id?: number | null;
}

export interface ExtractionReport {
	document_id: number;
	blocks: ExtractionBlock[];
	issues: ExtractionIssue[];
}

export interface EntityReport extends ExtractionReport {
	entities_status: ExtractionStatus;
}

export interface ActivityReport extends ExtractionReport {
	activities_status: ExtractionStatus;
	record_count: number;
}

export interface RegistryResult<T> {
	items: T[];
	status: ExtractionStatus;
	report: ExtractionReport;
}

export interface EntityResult extends RegistryResult<Entity> {
	relations: EntityRelation[];
}

export interface RegistriesApi {
	entities(id: number): Promise<EntityResult>;
	activities(id: number): Promise<RegistryResult<Activity>>;
}

async function read<T>(id: number, resource: string): Promise<T> {
	return (await request(`/api/documents/${id}/${resource}`)).json();
}

export const registriesApi: RegistriesApi = {
	async entities(id) {
		const [items, relations, report] = await Promise.all([
			read<Entity[]>(id, 'entities'),
			read<EntityRelation[]>(id, 'entity-relations'),
			read<EntityReport>(id, 'entity-report')
		]);
		return { items, relations, report, status: report.entities_status };
	},
	async activities(id) {
		const [items, report] = await Promise.all([
			read<Activity[]>(id, 'activities'),
			read<ActivityReport>(id, 'activity-report')
		]);
		return { items, report, status: report.activities_status };
	}
};
