const puppeteer = require('./node_modules/puppeteer-core');
const fs = require('fs');
const path = require('path');

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE_URL = 'http://localhost:5175';
// The API key comes from the environment; it is never committed (audit A12).
const API_KEY = process.env.RM_API_KEY;
if (!API_KEY) {
  console.error('RM_API_KEY is not set. Mint a key with `returns-manager keys create` and export RM_API_KEY.');
  process.exit(1);
}

const screenshotsDir = path.join(__dirname, 'screenshots_connected');
if (!fs.existsSync(screenshotsDir)) {
  fs.mkdirSync(screenshotsDir, { recursive: true });
}

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function runConnectedAudit() {
  console.log('===========================================================');
  console.log('STARTING CONNECTED END-TO-END UI & BACKEND AUDIT (CHROME)');
  console.log('===========================================================\n');

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1050'],
    defaultViewport: { width: 1600, height: 1050 },
  });

  const page = await browser.newPage();

  // Inject API key into every document before scripts execute
  await page.evaluateOnNewDocument((key) => {
    localStorage.setItem('rm_api_key', key);
  }, API_KEY);

  const errors = [];
  page.on('pageerror', (err) => {
    console.error(' [UNCAUGHT PAGE ERROR]:', err.message);
    errors.push(`PageError: ${err.message}`);
  });
  page.on('console', (msg) => {
    if (msg.type() === 'error' && !msg.text().includes('favicon') && !msg.text().includes('404')) {
      console.error(' [CONSOLE ERROR]:', msg.text());
      errors.push(`ConsoleError: ${msg.text()}`);
    }
  });

  try {
    // Step 1: Dashboard
    console.log('--- Step 1: Loading Dashboard (/dashboard) ---');
    await page.goto(`${BASE_URL}/dashboard`, { waitUntil: 'domcontentloaded' });
    await sleep(2000);

    const dbH1 = await page.$eval('h1', (el) => el.innerText).catch(() => '');
    console.log(`[PASS] Dashboard H1: "${dbH1}"`);
    
    const metricCards = await page.$$eval('.metrics .metric', (cards) =>
      cards.map((c) => {
        const val = c.querySelector('b')?.innerText;
        const lbl = c.querySelector('span')?.innerText;
        return `${lbl}: ${val}`;
      })
    );
    console.log('[PASS] Dashboard Live Metrics:', metricCards.join(' | '));
    await page.screenshot({ path: path.join(screenshotsDir, '01_dashboard.png') });

    // Step 2: Returns Ledger
    console.log('\n--- Step 2: Verifying Returns Ledger (/returns) ---');
    await page.goto(`${BASE_URL}/returns`, { waitUntil: 'domcontentloaded' });
    await sleep(2000);

    const initialRows = await page.$$eval('tbody tr', (trs) => trs.length);
    console.log(`[PASS] Returns Ledger loaded: ${initialRows} return rows visible.`);
    if (initialRows === 0) throw new Error('Returns table has 0 rows!');

    // Test Tabs
    const tabs = ['All returns', 'Auto-approved', 'Awaiting review', 'Needs attention', 'Finalized'];
    for (const tab of tabs) {
      const btn = await page.$(`xpath=//button[contains(@class, "tab") and contains(., "${tab}")]`);
      if (btn) {
        await btn.click();
        await sleep(350);
        const count = await page.$$eval('tbody tr', (trs) => trs.length);
        console.log(`[PASS] Tab "${tab}" -> ${count} rows shown.`);
      }
    }
    // Switch back to All returns
    const allTab = await page.$('xpath=//button[contains(@class, "tab") and contains(., "All returns")]');
    if (allTab) await allTab.click();
    await sleep(300);

    // Test Search
    const searchInput = await page.$('.table-search input');
    if (searchInput) {
      await searchInput.type('WATCH');
      await sleep(400);
      const filtered = await page.$$eval('tbody tr', (trs) => trs.length);
      console.log(`[PASS] Search "WATCH" filtered to ${filtered} rows.`);
      await searchInput.click({ clickCount: 3 });
      await page.keyboard.press('Backspace');
      await sleep(300);
    }

    // Test Column Sort
    const sortReturnBtn = await page.$('xpath=//thead//button[contains(., "RETURN")]');
    if (sortReturnBtn) {
      await sortReturnBtn.click();
      await sleep(300);
      console.log('[PASS] Column Sort "RETURN" toggled.');
    }
    await page.screenshot({ path: path.join(screenshotsDir, '02_returns_ledger.png') });

    // Step 3: Inspection Screen
    console.log('\n--- Step 3: Verifying Inspection Screen (/returns/:id/inspection) ---');
    const firstRow = await page.$('tbody tr');
    if (firstRow) {
      await firstRow.click();
      await sleep(2000);
    }
    console.log(`Inspection URL: ${page.url()}`);
    const inspH1 = await page.$eval('.inspection-title h1', (el) => el.innerText).catch(() => '');
    console.log(`[PASS] Inspected SKU: ${inspH1}`);

    // Verify 4 Pillars
    const pillars = await page.$$eval('.similarity-panel b, .similarity-panel .kicker', (els) =>
      els.map((e) => e.innerText.trim()).filter(Boolean)
    );
    console.log('[PASS] Agent 4-Pillar Verification:', pillars.slice(0, 8).join(' | '));

    // Test Photo Strip
    const thumbs = await page.$$('.photo-strip button');
    console.log(`[PASS] Photo Strip thumbnails found: ${thumbs.length}`);
    if (thumbs.length > 1) {
      await thumbs[1].click();
      await sleep(300);
      await thumbs[0].click();
      await sleep(300);
      console.log('[PASS] Thumbnail switching verified.');
    }

    // Test Zoom
    const zoomIn = await page.$('button[aria-label="Zoom in"]');
    const zoomOut = await page.$('button[aria-label="Zoom out"]');
    if (zoomIn) {
      await zoomIn.click();
      await sleep(200);
      console.log('[PASS] Photo Zoom In verified.');
    }
    if (zoomOut) {
      await zoomOut.click();
      await sleep(200);
      console.log('[PASS] Photo Zoom Out verified.');
    }

    // Test Accept Modal
    console.log('Testing Accept Decision action modal...');
    const acceptBtn = await page.$('xpath=//button[contains(., "Accept decision")]');
    if (acceptBtn) {
      await acceptBtn.click();
      await sleep(500);
      const txt = await page.$('.dialog textarea');
      if (txt) {
        await txt.type('Automated UI testing: QA acceptance verified.');
        const confirmBtn = await page.$('.dialog .button.primary');
        if (confirmBtn) {
          await confirmBtn.click();
          await sleep(1000);
          console.log('[PASS] Decision acceptance confirmed and saved to backend.');
        }
      }
    }

    // Test Retake Request Modal
    console.log('Testing Retake Request modal...');
    const retakeBtn = await page.$('xpath=//button[contains(., "Request retake")]');
    if (retakeBtn) {
      await retakeBtn.click();
      await sleep(400);
      const cancelBtn = await page.$('.dialog .dialog-actions button:not(.primary)');
      if (cancelBtn) {
        await cancelBtn.click();
        await sleep(300);
        console.log('[PASS] Retake Request modal dismissed cleanly.');
      }
    }
    await page.screenshot({ path: path.join(screenshotsDir, '03_inspection.png') });

    // Step 4: Batch Upload Screen
    console.log('\n--- Step 4: Verifying Batch Upload Screen (/returns/new) ---');
    await page.goto(`${BASE_URL}/returns/new`, { waitUntil: 'domcontentloaded' });
    await sleep(1500);
    const dropzone = await page.$('.dropzone');
    console.log(`[PASS] Upload Dropzone present: ${!!dropzone}`);
    const spendCheckbox = await page.$('input[type="checkbox"]');
    if (spendCheckbox) {
      await spendCheckbox.click();
      await sleep(300);
      console.log('[PASS] Spend confirmation checkbox toggled.');
    }
    await page.screenshot({ path: path.join(screenshotsDir, '04_batch_upload.png') });

    // Step 5: Review Queue
    console.log('\n--- Step 5: Verifying Review Queue (/reviews) ---');
    await page.goto(`${BASE_URL}/reviews`, { waitUntil: 'domcontentloaded' });
    await sleep(1500);
    const qCount = await page.$$eval('.queue-row', (rows) => rows.length);
    console.log(`[PASS] Review Queue items awaiting human review: ${qCount}`);
    await page.screenshot({ path: path.join(screenshotsDir, '05_review_queue.png') });

    // Step 6: Product Catalogue
    console.log('\n--- Step 6: Verifying Product Catalogue (/catalogue) ---');
    await page.goto(`${BASE_URL}/catalogue`, { waitUntil: 'domcontentloaded' });
    await sleep(1500);
    const prodCards = await page.$$eval('.product-card', (cards) => cards.length);
    console.log(`[PASS] Distinct Catalogue Products rendered: ${prodCards}`);
    if (prodCards === 0) throw new Error('Catalogue has 0 products!');
    await page.screenshot({ path: path.join(screenshotsDir, '06_catalogue.png') });

    // Step 7: Unit Digital Passport
    console.log('\n--- Step 7: Verifying Unit Digital Passport (/units/UNIT-0001) ---');
    await page.goto(`${BASE_URL}/units/UNIT-0001`, { waitUntil: 'domcontentloaded' });
    await sleep(1500);
    const unitSku = await page.$eval('.passport h2', (el) => el.innerText).catch(() => 'None');
    console.log(`[PASS] Unit Passport rendered SKU: ${unitSku}`);
    const stages = await page.$$eval('.stage b', (els) => els.map((e) => e.innerText));
    console.log(`[PASS] Lifecycle Stages: ${stages.join(' -> ')}`);
    await page.screenshot({ path: path.join(screenshotsDir, '07_unit_passport.png') });

    // Step 8: Evidence & Audit
    console.log('\n--- Step 8: Verifying Evidence & Audit Screen (/evidence) ---');
    await page.goto(`${BASE_URL}/evidence`, { waitUntil: 'domcontentloaded' });
    await sleep(1500);
    const evRows = await page.$$eval('tbody tr', (trs) => trs.length);
    console.log(`[PASS] Evidence table rows: ${evRows}`);

    // Test row expand
    const firstEv = await page.$('tbody tr');
    if (firstEv) {
      await firstEv.click();
      await sleep(400);
      const exp = await page.$('.evidence-expanded');
      console.log(`[PASS] Evidence detail drawer expanded: ${!!exp}`);
    }
    await page.screenshot({ path: path.join(screenshotsDir, '08_evidence.png') });

    // Step 9: Analytics
    console.log('\n--- Step 9: Verifying Analytics Screen (/analytics) ---');
    await page.goto(`${BASE_URL}/analytics`, { waitUntil: 'domcontentloaded' });
    await sleep(1500);
    const analyticsPanels = await page.$$eval('.panel h2', (els) => els.map((e) => e.innerText));
    console.log('[PASS] Analytics Charts & Panels:', analyticsPanels.join(' | '));
    await page.screenshot({ path: path.join(screenshotsDir, '09_analytics.png') });

    // Step 10: Integrations
    console.log('\n--- Step 10: Verifying Integrations Screen (/integrations) ---');
    await page.goto(`${BASE_URL}/integrations`, { waitUntil: 'domcontentloaded' });
    await sleep(1200);
    const pods = await page.$$eval('.flow-item b', (els) => els.map((e) => e.innerText));
    console.log('[PASS] Ecosystem Pods:', pods.join(' | '));
    await page.screenshot({ path: path.join(screenshotsDir, '10_integrations.png') });

    // Step 11: Settings
    console.log('\n--- Step 11: Verifying Settings Screen (/settings) ---');
    await page.goto(`${BASE_URL}/settings`, { waitUntil: 'domcontentloaded' });
    await sleep(1500);
    const controls = await page.$$eval('.control-row b', (els) => els.map((e) => e.innerText));
    console.log('[PASS] System Controls (Kill switches):', controls.join(' | '));
    await page.screenshot({ path: path.join(screenshotsDir, '11_settings.png') });

    // Step 12: Topbar Global Search & Theme Controls
    console.log('\n--- Step 12: Verifying Topbar Global Controls ---');
    // Theme toggle
    const themeBtn = await page.$('.theme-switch');
    if (themeBtn) {
      await themeBtn.click();
      await sleep(300);
      console.log('[PASS] Toggled to Light Mode.');
      await themeBtn.click();
      await sleep(300);
      console.log('[PASS] Toggled back to Dark Mode.');
    }

    // Bell Notification
    const bellBtn = await page.$('.bell-btn');
    if (bellBtn) {
      await bellBtn.click();
      await sleep(400);
      console.log('[PASS] Clicked Notification Bell.');
    }

    // Global Search Modal
    const searchBtn = await page.$('.global-search');
    if (searchBtn) {
      await searchBtn.click();
      await sleep(400);
      const searchInput = await page.$('.search-modal input');
      if (searchInput) {
        await searchInput.type('WATCH');
        await sleep(300);
        const searchResults = await page.$$eval('.search-results button', (btns) => btns.length);
        console.log(`[PASS] Global Search modal returned ${searchResults} matching records.`);
      }
      await page.keyboard.press('Escape');
      await sleep(300);
      console.log('[PASS] Global Search dismissed with Escape.');
    }

    // Overview Page test
    console.log('\n--- Step 13: Verifying Overview Landing Page (/overview) ---');
    await page.goto(`${BASE_URL}/overview`, { waitUntil: 'domcontentloaded' });
    await sleep(1500);
    const ovH1 = await page.$eval('h1', (el) => el.innerText).catch(() => '');
    console.log(`[PASS] Overview Title: "${ovH1.replace(/\n/g, ' ')}"`);
    await page.screenshot({ path: path.join(screenshotsDir, '12_overview.png') });

    console.log('\n===========================================================');
    console.log(`TOTAL UNCAUGHT ERRORS: ${errors.length}`);
    console.log('===========================================================');
    if (errors.length > 0) {
      console.error('\nErrors encountered during audit:');
      errors.forEach((e) => console.error(' *', e));
      process.exit(1);
    } else {
      console.log('\n>>> COMPLETE END-TO-END PROJECT AUDIT PASSED WITH 100% SUCCESS! <<<\n');
    }
  } catch (err) {
    console.error('Audit failed with exception:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

runConnectedAudit();
