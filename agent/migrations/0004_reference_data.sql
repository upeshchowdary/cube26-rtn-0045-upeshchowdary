-- 0004 · Reference data tables (§7.2). Runs as the migrator role; SET LOCAL ROLE rm_owner.
SET LOCAL ROLE rm_owner;

CREATE TABLE rm.products (
  org_id        text NOT NULL CHECK (org_id <> '') REFERENCES rm.organizations (org_id),
  sku           text NOT NULL CHECK (sku <> ''),
  card_version  text NOT NULL CHECK (card_version <> ''),
  asin          text,
  fnsku         text,
  gtin          text,
  title         text NOT NULL,
  brand         text NOT NULL,
  category_key  text NOT NULL,
  card_sha256   text NOT NULL CHECK (card_sha256 ~ '^[0-9a-f]{64}$'),
  card          jsonb NOT NULL,
  active        boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, sku, card_version)
);

CREATE TABLE rm.product_components (
  org_id               text NOT NULL CHECK (org_id <> '') REFERENCES rm.organizations (org_id),
  sku                  text NOT NULL,
  card_version         text NOT NULL,
  component_id         text NOT NULL CHECK (component_id ~ '^[a-z0-9_]+$'),
  name                 text NOT NULL,
  quantity             integer NOT NULL CHECK (quantity >= 1),
  essential            boolean,
  replaceable          boolean,
  verifiable_by_photo  boolean NOT NULL DEFAULT true,
  visual_cues          text NOT NULL,
  source               jsonb NOT NULL,
  PRIMARY KEY (org_id, sku, card_version, component_id),
  FOREIGN KEY (org_id, sku, card_version) REFERENCES rm.products (org_id, sku, card_version)
);

CREATE TABLE rm.reference_images (
  org_id                   text NOT NULL CHECK (org_id <> '') REFERENCES rm.organizations (org_id),
  sku                      text NOT NULL,
  card_version             text NOT NULL,
  ref_image_id             text NOT NULL CHECK (ref_image_id ~ '^ref_[a-z0-9_]+$'),
  view                     text NOT NULL,
  storage_key              text NOT NULL,
  sha256                   text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  width                    integer,
  height                   integer,
  gemini_file_uri          text,
  gemini_file_uploaded_at  timestamptz,
  PRIMARY KEY (org_id, ref_image_id),
  FOREIGN KEY (org_id, sku, card_version) REFERENCES rm.products (org_id, sku, card_version)
);

-- Global reference tables: no tenant data, rm_app gets read/write for loader.
CREATE TABLE rm.rubric_snapshots (
  snapshot_id             text PRIMARY KEY,
  source_marketplace      text NOT NULL,
  applies_to_marketplace  text NOT NULL,
  category_key            text NOT NULL,
  verification_status     text NOT NULL CHECK (verification_status IN ('verified', 'unverified_substitute')),
  source_id               text NOT NULL,
  content_sha256          text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  content                 jsonb NOT NULL,
  loaded_at               timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rm.category_policies (
  policy_id               text NOT NULL,
  version                 text NOT NULL,
  source_marketplace      text NOT NULL,
  category_key            text NOT NULL,
  content_sha256          text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  content                 jsonb NOT NULL,
  loaded_at               timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (policy_id, version)
);

CREATE TABLE rm.org_policy_overrides (
  org_id       text NOT NULL CHECK (org_id <> '') REFERENCES rm.organizations (org_id),
  key          text NOT NULL CHECK (key <> ''),
  value        jsonb NOT NULL,
  source_type  text NOT NULL CHECK (source_type IN ('business_policy', 'assumption')),
  updated_by   text NOT NULL CHECK (updated_by <> ''),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, key)
);

CREATE TABLE rm.orders (
  org_id            text NOT NULL CHECK (org_id <> '') REFERENCES rm.organizations (org_id),
  order_id          text NOT NULL CHECK (order_id <> ''),
  unit_id           text NOT NULL CHECK (unit_id <> ''),
  ordered_sku       text NOT NULL,
  ordered_asin      text,
  quantity          integer NOT NULL CHECK (quantity >= 1),
  fulfilment_route  text NOT NULL CHECK (fulfilment_route IN ('fba', 'mfn', 'unknown')),
  ordered_at        timestamptz NOT NULL,
  PRIMARY KEY (org_id, order_id, unit_id)
);

-- ── Row-level security ─────────────────────────────────────────────────────
ALTER TABLE rm.products ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.products FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.products
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

ALTER TABLE rm.product_components ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.product_components FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.product_components
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

ALTER TABLE rm.reference_images ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.reference_images FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.reference_images
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

ALTER TABLE rm.org_policy_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.org_policy_overrides FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.org_policy_overrides
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

ALTER TABLE rm.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.orders FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.orders
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

-- ── Privileges (no DELETE anywhere) ────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE ON rm.products, rm.product_components, rm.reference_images,
  rm.org_policy_overrides, rm.orders TO rm_app;
GRANT SELECT, INSERT, UPDATE ON rm.rubric_snapshots, rm.category_policies TO rm_app;
