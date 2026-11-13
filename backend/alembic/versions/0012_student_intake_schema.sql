-- Frozen Release 0.3 schema. Runtime models do not define migration history.
CREATE TABLE onboarding_schemas (
	id UUID NOT NULL,
	institution_id UUID NOT NULL,
	org_unit_id UUID NOT NULL,
	version INTEGER NOT NULL,
	definition JSONB NOT NULL,
	author_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (org_unit_id, version),
	FOREIGN KEY(institution_id) REFERENCES institutions (id),
	FOREIGN KEY(org_unit_id) REFERENCES org_units (id),
	FOREIGN KEY(author_id) REFERENCES users (id)
);

CREATE TABLE onboarding_configs (
	id UUID NOT NULL,
	version INTEGER NOT NULL,
	active_schema_id UUID,
	PRIMARY KEY (id),
	FOREIGN KEY(id) REFERENCES org_units (id)
);

CREATE TABLE academic_profiles (
	id UUID NOT NULL,
	version INTEGER NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(id) REFERENCES student_memberships (id)
);

CREATE TABLE profile_versions (
	id UUID NOT NULL,
	student_membership_id UUID NOT NULL,
	institution_id UUID NOT NULL,
	org_unit_id UUID NOT NULL,
	version INTEGER NOT NULL,
	schema_id UUID NOT NULL,
	status VARCHAR NOT NULL,
	facts JSONB NOT NULL,
	reviews JSONB NOT NULL,
	author_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (student_membership_id, version),
	FOREIGN KEY(student_membership_id) REFERENCES student_memberships (id),
	FOREIGN KEY(institution_id) REFERENCES institutions (id),
	FOREIGN KEY(org_unit_id) REFERENCES org_units (id),
	FOREIGN KEY(schema_id) REFERENCES onboarding_schemas (id),
	FOREIGN KEY(author_id) REFERENCES users (id)
);

CREATE TABLE sources (
	id UUID NOT NULL,
	institution_id UUID NOT NULL,
	org_unit_id UUID,
	student_membership_id UUID,
	owner_id UUID NOT NULL,
	visibility VARCHAR NOT NULL,
	version INTEGER NOT NULL,
	archived BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(institution_id) REFERENCES institutions (id),
	FOREIGN KEY(org_unit_id) REFERENCES org_units (id),
	FOREIGN KEY(student_membership_id) REFERENCES student_memberships (id),
	FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE TABLE source_versions (
	id UUID NOT NULL,
	source_id UUID NOT NULL,
	version INTEGER NOT NULL,
	filename VARCHAR NOT NULL,
	media_type VARCHAR NOT NULL,
	content_hash VARCHAR NOT NULL,
	object_key VARCHAR NOT NULL,
	metadata_fields JSONB NOT NULL,
	author_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (source_id, version),
	FOREIGN KEY(source_id) REFERENCES sources (id),
	FOREIGN KEY(author_id) REFERENCES users (id)
);

CREATE TABLE ingestion_jobs (
	id UUID NOT NULL,
	source_version_id UUID NOT NULL,
	actor_id UUID NOT NULL,
	grant_epoch INTEGER NOT NULL,
	relationship_epoch INTEGER,
	purpose VARCHAR NOT NULL,
	attempt INTEGER NOT NULL,
	state VARCHAR NOT NULL,
	error_code VARCHAR,
	lease_token UUID,
	lease_until TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (source_version_id, attempt),
	FOREIGN KEY(source_version_id) REFERENCES source_versions (id),
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE TABLE extraction_artifacts (
	id UUID NOT NULL,
	source_version_id UUID NOT NULL,
	job_id UUID NOT NULL,
	object_key VARCHAR NOT NULL,
	extractor_version VARCHAR NOT NULL,
	ocr BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (source_version_id),
	FOREIGN KEY(source_version_id) REFERENCES source_versions (id),
	FOREIGN KEY(job_id) REFERENCES ingestion_jobs (id)
);
