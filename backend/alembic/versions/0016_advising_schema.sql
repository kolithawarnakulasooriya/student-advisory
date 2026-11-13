-- Frozen Release 0.4 schema.
CREATE TABLE embedding_configs (
	id UUID NOT NULL,
	fingerprint VARCHAR NOT NULL,
	definition JSONB NOT NULL,
	dimension INTEGER NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (fingerprint)
);

CREATE TABLE knowledge_states (
	id UUID NOT NULL,
	version INTEGER NOT NULL,
	config_id UUID,
	PRIMARY KEY (id),
	FOREIGN KEY(id) REFERENCES institutions (id),
	FOREIGN KEY(config_id) REFERENCES embedding_configs (id)
);

CREATE TABLE index_builds (
	id UUID NOT NULL,
	source_version_id UUID NOT NULL,
	config_id UUID NOT NULL,
	state VARCHAR NOT NULL,
	error_code VARCHAR,
	reviewed_by UUID NOT NULL,
	review_reason VARCHAR NOT NULL,
	chunk_count INTEGER NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (source_version_id, config_id),
	FOREIGN KEY(source_version_id) REFERENCES source_versions (id),
	FOREIGN KEY(config_id) REFERENCES embedding_configs (id),
	FOREIGN KEY(reviewed_by) REFERENCES users (id)
);

CREATE TABLE evidence_chunks (
	id UUID NOT NULL,
	build_id UUID NOT NULL,
	ordinal INTEGER NOT NULL,
	source_version_id UUID NOT NULL,
	text VARCHAR NOT NULL,
	locator JSONB NOT NULL,
	content_hash VARCHAR NOT NULL,
	token_count INTEGER NOT NULL,
	embedding VECTOR(768) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (build_id, ordinal),
	FOREIGN KEY(build_id) REFERENCES index_builds (id),
	FOREIGN KEY(source_version_id) REFERENCES source_versions (id)
);

CREATE TABLE source_publications (
	id UUID NOT NULL,
	build_id UUID NOT NULL,
	version INTEGER NOT NULL,
	status VARCHAR NOT NULL,
	publisher_id UUID NOT NULL,
	reason VARCHAR NOT NULL,
	published_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(id) REFERENCES sources (id),
	FOREIGN KEY(build_id) REFERENCES index_builds (id),
	FOREIGN KEY(publisher_id) REFERENCES users (id)
);

CREATE TABLE publication_events (
	id UUID NOT NULL,
	source_id UUID NOT NULL,
	build_id UUID NOT NULL,
	version INTEGER NOT NULL,
	action VARCHAR NOT NULL,
	actor_id UUID NOT NULL,
	reason VARCHAR NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(source_id) REFERENCES sources (id),
	FOREIGN KEY(build_id) REFERENCES index_builds (id),
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE TABLE index_releases (
	id UUID NOT NULL,
	institution_id UUID NOT NULL,
	config_id UUID NOT NULL,
	version INTEGER NOT NULL,
	manifest JSONB NOT NULL,
	actor_id UUID NOT NULL,
	reason VARCHAR NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(institution_id) REFERENCES institutions (id),
	FOREIGN KEY(config_id) REFERENCES embedding_configs (id),
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE TABLE governance_versions (
	id UUID NOT NULL,
	institution_id UUID NOT NULL,
	org_unit_id UUID,
	kind VARCHAR NOT NULL,
	definition JSONB NOT NULL,
	actor_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(institution_id) REFERENCES institutions (id),
	FOREIGN KEY(org_unit_id) REFERENCES org_units (id),
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE TABLE governance_activations (
	id UUID NOT NULL,
	governance_id UUID NOT NULL,
	institution_id UUID NOT NULL,
	org_unit_id UUID,
	kind VARCHAR NOT NULL,
	version INTEGER NOT NULL,
	actor_id UUID NOT NULL,
	reason VARCHAR NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(governance_id) REFERENCES governance_versions (id),
	FOREIGN KEY(institution_id) REFERENCES institutions (id),
	FOREIGN KEY(org_unit_id) REFERENCES org_units (id),
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE TABLE governance_evaluations (
	id UUID NOT NULL,
	governance_id UUID NOT NULL,
	fingerprint VARCHAR NOT NULL,
	dataset_hash VARCHAR NOT NULL,
	passed BOOLEAN NOT NULL,
	results JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(governance_id) REFERENCES governance_versions (id)
);

CREATE TABLE conversations (
	id UUID NOT NULL,
	student_membership_id UUID NOT NULL,
	institution_id UUID NOT NULL,
	org_unit_id UUID NOT NULL,
	version INTEGER NOT NULL,
	guidance_epoch INTEGER NOT NULL,
	title VARCHAR NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(student_membership_id) REFERENCES student_memberships (id),
	FOREIGN KEY(institution_id) REFERENCES institutions (id),
	FOREIGN KEY(org_unit_id) REFERENCES org_units (id)
);

CREATE TABLE student_messages (
	id UUID NOT NULL,
	conversation_id UUID NOT NULL,
	author_id UUID NOT NULL,
	text VARCHAR NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(conversation_id) REFERENCES conversations (id),
	FOREIGN KEY(author_id) REFERENCES users (id)
);

CREATE TABLE advisor_guidance (
	id UUID NOT NULL,
	conversation_id UUID NOT NULL,
	author_id UUID NOT NULL,
	text VARCHAR NOT NULL,
	effective_from TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	effective_until TIMESTAMP WITH TIME ZONE,
	supersedes_id UUID,
	preferences JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(conversation_id) REFERENCES conversations (id),
	FOREIGN KEY(author_id) REFERENCES users (id),
	FOREIGN KEY(supersedes_id) REFERENCES advisor_guidance (id)
);

CREATE TABLE staff_notes (
	id UUID NOT NULL,
	conversation_id UUID NOT NULL,
	author_id UUID NOT NULL,
	text VARCHAR NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(conversation_id) REFERENCES conversations (id),
	FOREIGN KEY(author_id) REFERENCES users (id)
);

CREATE TABLE advising_jobs (
	id UUID NOT NULL,
	kind VARCHAR NOT NULL,
	target_id UUID NOT NULL,
	student_membership_id UUID,
	conversation_id UUID,
	message_id UUID,
	actor_id UUID NOT NULL,
	grant_epoch INTEGER NOT NULL,
	purpose VARCHAR NOT NULL,
	version INTEGER NOT NULL,
	attempt INTEGER NOT NULL,
	state VARCHAR NOT NULL,
	context_snapshot JSONB NOT NULL,
	error_code VARCHAR,
	lease_token UUID,
	lease_until TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (message_id, attempt, kind),
	FOREIGN KEY(student_membership_id) REFERENCES student_memberships (id),
	FOREIGN KEY(conversation_id) REFERENCES conversations (id),
	FOREIGN KEY(message_id) REFERENCES student_messages (id),
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE TABLE validated_answers (
	id UUID NOT NULL,
	job_id UUID NOT NULL,
	conversation_id UUID NOT NULL,
	message_id UUID NOT NULL,
	disposition VARCHAR NOT NULL,
	payload JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (job_id),
	FOREIGN KEY(job_id) REFERENCES advising_jobs (id),
	FOREIGN KEY(conversation_id) REFERENCES conversations (id),
	FOREIGN KEY(message_id) REFERENCES student_messages (id)
);

CREATE TABLE advisor_drafts (
	id UUID NOT NULL,
	job_id UUID NOT NULL,
	conversation_id UUID NOT NULL,
	actor_id UUID NOT NULL,
	payload JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (job_id),
	FOREIGN KEY(job_id) REFERENCES advising_jobs (id),
	FOREIGN KEY(conversation_id) REFERENCES conversations (id),
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE TABLE retrieval_traces (
	id UUID NOT NULL,
	job_id UUID NOT NULL,
	evidence_ids JSONB NOT NULL,
	context_snapshot JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (job_id),
	FOREIGN KEY(job_id) REFERENCES advising_jobs (id)
);

CREATE TABLE advising_cases (
	id UUID NOT NULL,
	student_membership_id UUID NOT NULL,
	conversation_id UUID,
	institution_id UUID NOT NULL,
	org_unit_id UUID NOT NULL,
	status VARCHAR NOT NULL,
	version INTEGER NOT NULL,
	reason VARCHAR NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(student_membership_id) REFERENCES student_memberships (id),
	FOREIGN KEY(conversation_id) REFERENCES conversations (id),
	FOREIGN KEY(institution_id) REFERENCES institutions (id),
	FOREIGN KEY(org_unit_id) REFERENCES org_units (id)
);

CREATE TABLE case_events (
	id UUID NOT NULL,
	case_id UUID NOT NULL,
	actor_id UUID NOT NULL,
	status VARCHAR NOT NULL,
	text VARCHAR NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(case_id) REFERENCES advising_cases (id),
	FOREIGN KEY(actor_id) REFERENCES users (id)
);
