-- 0010 · Escalation state and audit run tracking (§11.12, §11.13).
SET LOCAL ROLE rm_owner;

-- Allow 'completed' for escalation_state in inspection_results
ALTER TABLE rm.inspection_results DROP CONSTRAINT IF EXISTS inspection_results_escalation_state_check;
ALTER TABLE rm.inspection_results ADD CONSTRAINT inspection_results_escalation_state_check
  CHECK (escalation_state IN ('not_triggered', 'triggered_not_run', 'completed'));

-- Add eval_run_id to audit findings
ALTER TABLE rm.audit_findings ADD COLUMN IF NOT EXISTS eval_run_id text;
CREATE INDEX IF NOT EXISTS audit_findings_eval_run ON rm.audit_findings (org_id, eval_run_id);
