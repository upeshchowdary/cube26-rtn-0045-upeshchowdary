-- 0006 · Reference-image key fix (§7.2).
-- 0004 keyed rm.reference_images by (org_id, ref_image_id), but image ids are only unique within one product
-- card (every card has `ref_front`), so loading several cards of one org overwrote each other's rows: after
-- `reference load` each org kept a single image row. The key now includes the card the image belongs to.
SET LOCAL ROLE rm_owner;

ALTER TABLE rm.reference_images DROP CONSTRAINT reference_images_pkey;
ALTER TABLE rm.reference_images ADD PRIMARY KEY (org_id, sku, card_version, ref_image_id);
