-- 0012 · Keep the unit event / org ledger tables append-only for rm_app.
-- The application can read and insert new chain entries, but must never mutate the stored
-- historical record or ledger payloads directly. The app role only updates the per-unit head
-- rows and evidence record versions via the explicit service layer.
SET LOCAL ROLE rm_owner;

REVOKE UPDATE ON TABLE rm.unit_events FROM rm_app;
REVOKE UPDATE ON TABLE rm.unit_events FROM rm_app_login;
REVOKE UPDATE ON TABLE rm.org_ledger FROM rm_app;
REVOKE UPDATE ON TABLE rm.org_ledger FROM rm_app_login;

-- Defensive cleanup for any older or manually-mutated grant state.
REVOKE ALL ON TABLE rm.unit_events FROM PUBLIC;
REVOKE ALL ON TABLE rm.org_ledger FROM PUBLIC;

-- Keep the intended app permissions explicit and narrow.
GRANT SELECT, INSERT ON TABLE rm.unit_events TO rm_app;
GRANT SELECT, INSERT ON TABLE rm.org_ledger TO rm_app;
