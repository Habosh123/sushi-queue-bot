ALTER TABLE queue_entries
DROP CONSTRAINT IF EXISTS uq_active_user_location_queue;

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_queue_entry
ON queue_entries (user_id, location_id)
WHERE is_active = true;
