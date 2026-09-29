// Landing-page copy. Every claim here traces to ui/FACTS.md (section numbers in comments).
import type { FaqItem, NavItem } from '../design/components'

export const anchors: NavItem[] = [
  { label: 'How it works', href: '#journey' },
  { label: 'Evidence', href: '#evidence' },
  { label: 'Decisions', href: '#decision' },
  { label: 'Audit trail', href: '#audit' },
  { label: 'FAQ', href: '#faq' },
]

// Real app screens (FACTS §1).
export const appLinks: NavItem[] = [
  { label: 'Dashboard', to: '/dashboard' },
  { label: 'Returns', to: '/returns' },
  { label: 'Review queue', to: '/reviews' },
]

export const footerLinks: NavItem[] = [
  { label: 'How it works', href: '#journey' },
  { label: 'FAQ', href: '#faq' },
  { label: 'Dashboard', to: '/dashboard' },
  { label: 'New inspection', to: '/returns/new' },
  { label: 'Evidence & audit', to: '/evidence' },
]

export const faq: FaqItem[] = [
  {
    // FACTS §12 mission, §2
    q: 'What is Return Manager?',
    a: (
      <p>
        A return inspection workflow. From two or three photos of a returned item, plus your catalogue, the order, the
        parts list and Amazon's published condition guidelines, it records an evidence-backed verdict on identity,
        completeness and condition. A rules engine then computes one of four dispositions (restock, refurbish, liquidate
        or dispose) for your team to confirm.
      </p>
    ),
  },
  {
    // FACTS §9b checks, §3
    q: 'What does it check on a returned item?',
    a: (
      <p>
        Whether the product is actually in the photos, whether it is the product that was sold, whether the sold and
        returned records agree, whether every part on the parts list is there, and its condition against the category's
        rubric. It also checks photo quality and flags reused photos. A functional test is not performed.
      </p>
    ),
  },
  {
    // FACTS §9b identity, fusion.py
    q: 'How does it tell whether the right product came back?',
    a: (
      <>
        <p>
          Two separate checks, shown separately. <b>Product identity</b>: the model reports whether the distinguishing
          features on the product body match the reference, and deterministic rules fuse that with any decoded barcode
          into Yes, No or Uncertain. A barcode alone never produces a Yes.
        </p>
        <p>
          <b>Sold vs returned records</b> compares the order ID, SKU and ASIN of the sale and the return. Paperwork that
          matches doesn't prove what's inside the box, which is why it never stands in for product identity.
        </p>
      </>
    ),
  },
  {
    // FACTS §9b parts, §5 essential_component_uncertain, engine R05
    q: "What happens when a part isn't visible in the photos?",
    a: (
      <p>
        It is recorded as <i>not visible in the provided photos</i>, not as missing. A part is marked missing only when
        it is clearly absent in view. If an essential part can't be seen, the engine routes as if it were missing, marks
        the recommendation provisional and sends the return to review.
      </p>
    ),
  },
  {
    // FACTS §3, §4
    q: 'How is condition graded?',
    a: (
      <p>
        The model reports the observed state (for example <i>Signs of use</i>) and any defects with their severity and
        location. Code maps that to one of Amazon's five grades, from New to Used - Acceptable, graded against Amazon's
        published condition guidelines (unverified substitute snapshot: the UK guidelines, applied to amazon.in). If the
        photos can't settle it, condition is recorded as uncertain.
      </p>
    ),
  },
  {
    // FACTS §12 "no disposition field", §2
    q: 'Does the AI decide what happens to the item?',
    a: (
      <p>
        No. The model has no disposition field in its output; it only reports what it observes in the photos.
        Deterministic rules turn those observations into verdicts, the rules engine computes the recommended disposition
        and the rule that produced it, and a person confirms or overrides it.
      </p>
    ),
  },
  {
    // FACTS §2.4, §5, §9
    q: 'When does a return need a person to review or sign off?',
    a: (
      <>
        <p>
          Review, whenever the engine can't make a recommendation (identity or condition uncertain, inspection
          incomplete) or a flag is raised (an essential part not visible, a possible reused photo, instruction-like text in
          a photo, a re-inspection that disagreed).
        </p>
        <p>
          Sign-off by a second person, for every dispose and for any route other than restock at or above the high-value
          threshold (₹5,000 list price). Whoever submitted the return can't sign it off. In batch uploads, a row is
          auto-approved only if it needs neither, its records match, every check passes and the lowest check confidence
          clears a threshold that is a placeholder, not yet calibrated.
        </p>
      </>
    ),
  },
  {
    // FACTS §6, 0.5, 0.9
    q: 'Is every decision recorded?',
    a: (
      <>
        <p>
          In the inspection pipeline, every step (photos received, inspection completed, identity fused, disposition
          computed, the operator's decision, any override, the sign-off, the finalised record) is an event in a per-unit
          hash chain: tamper-evident within the database (hash-chained), not immutable. An override records the original
          value, the new value, the reason and who made it.
        </p>
        <p>
          Batch uploads append each decision to the job's decision log (the new disposition, the reason, who and when).
          Batch rows are not hash-chained.
        </p>
      </>
    ),
  },
]
