-- Extend clip_exports with quality and resolution options
ALTER TABLE clip_exports ADD COLUMN quality_preset TEXT NOT NULL DEFAULT 'original';
ALTER TABLE clip_exports ADD COLUMN resolution TEXT NOT NULL DEFAULT 'original';
