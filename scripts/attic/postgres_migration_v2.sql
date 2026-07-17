-- OpenEtruscan Migration v2: SOTA Provenance Alignment
-- This script modernizes the inscriptions table with Digital Humanities standards.

BEGIN;

-- 1. Add SOTA Provenance Columns
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS source_code TEXT DEFAULT 'unknown';
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS source_detail TEXT;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS original_script_entry TEXT;

-- 2. Create index on source_code for dataset segmentation
CREATE INDEX IF NOT EXISTS ix_inscriptions_source_code ON inscriptions (source_code);

-- 3. Tag existing records as 'LARTH'
-- Assumption: All records currently in the DB without a source_code are from the legacy Larth dataset.
UPDATE inscriptions 
SET 
    source_code = 'LARTH',
    source_detail = 'Larth dataset (Legacy Migration 2024-2025)'
WHERE source_code = 'unknown';

-- 4. Constraint (Optional: enforcing source_code in future)
-- ALTER TABLE inscriptions ALTER COLUMN source_code SET NOT NULL;

COMMIT;
