# Sydon Returns — Demo Video Voiceover Narration Script
**Project:** Sydon Returns (Cube Buildathon 2026 / `cube26-rtn-0045-upeshchowdary`)  
**Video File:** [`Sydon_Returns_Demo_Voiceover.mp4`](Sydon_Returns_Demo_Voiceover.mp4)  
**Total Duration:** 07:03.50 (423.50 seconds)  
**Voice Profile:** Neural Male Narrator (`en-US-ChristopherNeural`)  
**Delivery Style:** Professional, authoritative, engaging, and technically precise  

---

## Synchronized Scene-by-Scene Timeline

### 1. `00:00 – 00:30` | System Introduction & Value Proposition
- **Visual:** Landing Page Hero Section (`http://localhost:5173/` or Render deployment).
- **On Screen:** "Turn every return into a clear decision." Subtitle, action buttons, and sample preview card `RTN-SAMPLE-0142`.
- **Narration:**
  > *"Welcome to Sydon Returns, an enterprise reverse logistics platform built for the Cube Buildathon 2026. In modern e-commerce, returns represent one of the most complex, fraud-prone, and expensive operational challenges. Sydon transforms subjective warehouse inspections into automated, mathematically optimized, and auditable decisions using state-of-the-art multimodal vision intelligence."*

---

### 2. `00:30 – 01:15` | The 9-Stage Return Journey & Core Philosophy
- **Visual:** Landing Page scroll-through: "The Return Journey", 9 pipeline stages, "Evidence first. Decision second.", and "Exceptions & Fail-Open".
- **On Screen:** Step markers (Intake, Identity, Parts, Condition, Evidence, Recommendation, Human review, Disposition, Audit trail).
- **Narration:**
  > *"Here on the landing page, we outline our foundational architecture: The Return Journey. Every return progresses through nine rigorous stages—from intake photo storage, product identity extraction, and component checks, to condition grading, evidence verification, and deterministic rule routing. Our core philosophy is simple: Evidence first, decision second. The multimodal vision model never makes arbitrary business choices; it reports objective visual facts with spatial coordinates. A deterministic rules engine then computes the disposition. Crucially, our system implements a fail-open architecture: when photos are missing or ambiguous, it never guesses—it flags uncertain and safely escalates to human operators."*

---

### 3. `01:15 – 01:35` | Bulk Operations & Intake Upload
- **Visual:** Clicks "Open sydon returns", navigates to Workspace Intake (`/returns/new`).
- **On Screen:** File picker opens, selecting `returns_input_30.csv`, and clicks "Process batch".
- **Narration:**
  > *"Let us step into the live workspace. In the Operations Intake screen, warehouse teams ingest returns in bulk. Here, an operator selects a unified intake CSV manifest, linking pre-sale catalog baselines with returned unit intake photos, and initiates batch processing."*

---

### 4. `01:35 – 02:18` | Asynchronous Batch Engine & Spend Guards
- **Visual:** "Processing your upload: returns_input_30.csv - job 01M3VYH3KE".
- **On Screen:** Real-time progress bar, live metrics (Total: 8, Processed, Uncertain/Fail-open, Live model requests), and navigation to Returns ledger.
- **Narration:**
  > *"The batch inspection engine springs into action. Each return unit is processed asynchronously through a dedicated judgment session. The engine orchestrates calls to Google Gemini vision models using strict JSON schema contracts. Built-in spend guards and dynamic concurrency controls protect API token limits while live progress streams in real time. Notice how the UI actively tracks processed units, fail-open escalations, and live model requests. By decoupling intake ingestion from asynchronous worker execution, the architecture guarantees linear scalability even under peak return volumes. Let us drill down into the streaming Returns ledger."*

---

### 5. `02:18 – 02:58` | Returns Ledger & Triage Routing
- **Visual:** Returns Ledger Table (`/returns`).
- **On Screen:** Filter tabs (All returns: 80, Awaiting review: 33, Finalized: 34, Auto approved, Auto disapproved: 13), paginating through records.
- **Narration:**
  > *"This is the Returns Ledger, the central nervous system for warehouse triage. Across eighty processed returns, the ledger cleanly categorizes items into Awaiting Review, Finalized, Auto-approved, and Auto-disapproved. Items in pristine condition are automatically approved for restock, bypassing human bottlenecks entirely. Units with missing documentation or physical anomalies are instantly isolated for operator review. Every row displays verified catalog identity, missing components, Amazon-grade condition assessment, and computed disposition."*

---

### 6. `02:58 – 03:32` | Deep Dive: Pristine Verification & Auto-Restock
- **Visual:** Inspection details for `SKU-C26RM-041` (Logitech MX Master mouse).
- **On Screen:** Side-by-side visual comparison (Baseline Reference vs Intake P1), Critical Feature Checks (Silhouette matched, Brand markings matched), Component checklist (Mouse, Dongle, Cable 3/3), Salvage recovery values (Restock Used ₹14,999), and operator acceptance.
- **Narration:**
  > *"Now let us examine an individual unit inspection for this Logitech MX Master mouse. On the left, a synchronized side-by-side comparison displays the catalog reference against the warehouse intake photo. The vision engine conducts OCR verification, contour matching, and insignia verification with ninety-eight percent confidence. All expected components—the mouse, USB receiver, and charging cable—are verified present. Our rules engine applies economic salvage recovery formulas, approving the unit for immediate shelf restock."*

---

### 7. `03:32 – 03:55` | Deep Dive: Missing Visual Intake & Fail-Open Safety
- **Visual:** Inspection details for `SKU-PHONE-A` (Samsung smartphone with missing intake photo).
- **On Screen:** "Auto-rejected (Missing intake photo) - Auto-disapproved", Returned photo verification: MISSING PHOTO, Identity & Completeness: UNCERTAIN.
- **Narration:**
  > *"Next, let us observe our fail-open safety principle in action on this smartphone return. The intake record lacked a valid return photograph. Rather than hallucinating or assuming condition, Sydon immediately marks identity and completeness as uncertain, auto-disapproves automatic restock, and routes the unit directly to human operator review."*

---

### 8. `03:55 – 04:22` | Deep Dive: Merchandise Mismatch & Fraud Prevention
- **Visual:** Inspection details for `SKU-C26RM-042` (Sold keyboard vs returned mouse).
- **On Screen:** Discrepancy warning banner, Identity verdict MISMATCH (99.2% confidence), Disposition DISPOSE, followed by a quick check on `SKU-SHAMPOO-A`.
- **Narration:**
  > *"Here is a critical fraud prevention scenario: a severe merchandise mismatch. The order was for a compact keyboard, but the customer returned a worn mouse. Sydon's fused multi-signal verification flags an identity mismatch with ninety-nine point two percent confidence. The system automatically disapproves the return and issues a disposal disposition, safeguarding inventory from counterfeit or swapped goods."*

---

### 9. `04:22 – 04:42` | Dynamic Product Catalogue & Asset Telemetry
- **Visual:** Product Catalogue Page (`/catalog`).
- **On Screen:** Visual product cards across diverse categories (phones, consoles, audio, leashes, food consumables, drones) with live return counters and reference media.
- **Narration:**
  > *"Navigating to the Product Catalogue, we observe how Sydon dynamically maintains catalog intelligence. From gaming consoles and action cameras to consumer electronics and household goods, every product card aggregates live return volume, reference imagery, and historical quality telemetry."*

---

### 10. `04:42 – 05:03` | Executive Analytics & Recovery Yields
- **Visual:** Returns Overview Dashboard (`/overview`).
- **On Screen:** Metric KPI cards (Total returns: 80, Auto-disapproved: 13, Needs attention: 33, Restock eligible: 29, Live model requests: 204), trend line chart, and disposition donut chart.
- **Narration:**
  > *"The Overview dashboard delivers executive-level operational visibility. Supply chain directors can monitor throughput velocity, live Gemini quota consumption, and overall disposition mix—yielding forty-three percent restock recovery, twenty-four percent refurbishment, and nineteen percent disposal."*

---

### 11. `05:03 – 05:25` | Production Architecture: Token & Quota Control
- **Visual:** VS Code editor displaying `.env` configuration file.
- **On Screen:** `RM_QUOTA_RESET_TZ`, `RM_OUTPUT_MODE=json_schema`, `RM_MAX_OUTPUT_TOKENS=16000`, `RM_MAX_ROUND_TRIPS=2`, `RM_MAX_CROPS_PER_SESSION=4`, `RM_USE_FILES_API_FOR_REFERENCES=true`.
- **Narration:**
  > *"Now let us examine the engineering implementation in the codebase. In our environment configuration, we enforce strict token budgets, two-tier round-trip reasoning limits, and ultra-high resolution cropping. Google Cloud Files API caching is leveraged for catalog references, slashing image upload latency and operational overhead."*

---

### 12. `05:25 – 05:45` | Unified Intake Contract
- **Visual:** VS Code editor displaying `agent/manual_test_images/returns_input_50.csv`.
- **On Screen:** Intake manifest schema mapping `unit_id`, `category`, `parts_list`, `sold_record`, `sold_photo_url`, `returned_photo_url`.
- **Narration:**
  > *"Looking at the intake dataset, the schema unifies order identifiers, ASINs, expected component BOMs, and pre-sale reference media with live intake URLs. This enables seamless plug-and-play integration with legacy warehouse management systems and enterprise ERPs."*

---

### 13. `05:45 – 06:05` | Multimodal Prompt Engineering & Spatial Anchors
- **Visual:** VS Code editor displaying `agent/prompts/judgment/system.md`.
- **On Screen:** Prompt specification: 1. Role and Output (judgment/v1 schema), 2. Layers & Bounding Box `box_2d [ymin, xmin, ymax, xmax]`, 4. Strict Absence Rule.
- **Narration:**
  > *"Our multimodal prompt architecture in system dot md strictly enforces the division between observation and disposition. The agent outputs structured JSON adhering to the judgment schema, providing normalized two-D bounding box coordinates for every detected defect while following a strict absence verification rule."*

---

### 14. `06:05 – 06:20` | Robust Backend: Idempotency & Leasing
- **Visual:** VS Code editor exploring `src/returns_manager` (`jobs/`, `inspection/`, `intake/`, `disposition/`).
- **On Screen:** `JobRecord` dataclass, transactional state machine transitions, and idempotency key handling.
- **Narration:**
  > *"The Python backend architecture is built for mission-critical reliability. It features an idempotent job queue with distributed lease timeouts, transactional state machine transitions, and a pure deterministic rule execution engine."*

---

### 15. `06:20 – 06:35` | Enterprise Stack & Type Safety
- **Visual:** VS Code editor displaying `supabase/config.toml`, `ui/` React directory, and test suites.
- **On Screen:** Supabase local stack configuration, React Vite frontend components, and byte-exact `.gitattributes`.
- **Narration:**
  > *"Our persistence layer leverages Supabase PostgreSQL with row-level security and local migrations, paired with a modern, high-performance React frontend and comprehensive test coverage ensuring enterprise robustness."*

---

### 16. `06:35 – 07:03.5` | Live Cloud Deployment & Cryptographic Audit Trail
- **Visual:** Browser returns to live deployed URL on Render (`cube26-rtn-0045-upeshchowdary-1.onrender.com/overview`).
- **On Screen:** Audit Trail timeline: `inspection_started`, `inspection_completed`, `identity_fused`, `disposition_computed`, `operator_decision_recorded`, `record_finalized`, and final copyright banner: "Built for Cube Buildathon 04."
- **Narration:**
  > *"Finally, we see the live cloud deployment on Render. Every inspection produces a cryptographic, tamper-evident audit trail. Each event—from intake and visual inspection to identity fusion and operator signoff—is linked in an immutable SHA-256 hash chain. Sydon Returns delivers precision, speed, and auditability to reverse logistics. Thank you for watching."*
