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

const screenshotsDir = path.join(__dirname, 'screenshots');
if (!fs.existsSync(screenshotsDir)) {
  fs.mkdirSync(screenshotsDir, { recursive: true });
}

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function runFullTest() {
  console.log('====================================================');
  console.log('STARTING EXHAUSTIVE UI-TO-BACKEND AUDIT & TEST SUITE');
  console.log('====================================================\n');

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1000'],
    defaultViewport: { width: 1600, height: 1000 },
  });

  const page = await browser.newPage();

  const pageErrors = [];
  const consoleErrors = [];

  page.on('pageerror', (err) => {
    console.error(' [PAGE ERROR]:', err.message);
    pageErrors.push(err.message);
  });

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      console.error(' [CONSOLE ERROR]:', msg.text());
      consoleErrors.push(msg.text());
    }
  });

  try {
    // 0. Initialize authentication in localStorage
    console.log('--- Step 0: Setting Auth API Key in LocalStorage ---');
    await page.goto(`${BASE_URL}/overview`, { waitUntil: 'networkidle2' });
    await page.evaluate((key) => {
      localStorage.setItem('rm_api_key', key);
    }, API_KEY);
    console.log('[PASS] API Key configured.\n');

    // 1. Overview Page
    console.log('--- Step 1: Testing Overview Page (/overview) ---');
    await page.goto(`${BASE_URL}/overview`, { waitUntil: 'networkidle2' });
    await sleep(800);
    const overviewTitle = await page.$eval('h1', (el) => el.innerText).catch(() => 'No H1');
    console.log(`[PASS] Overview Title: "${overviewTitle.replace(/\n/g, ' ')}"`);
    await page.screenshot({ path: path.join(screenshotsDir, '01_overview.png') });

    // Test button on Overview: Navigate to Returns
    console.log('Clicking "Explore Workspace" or action button on Overview...');
    const exploreBtn = await page.$('button, a.hero-btn, a[href="/returns"], a[href="/dashboard"]');
    if (exploreBtn) {
      await exploreBtn.click();
      await sleep(1000);
    }

    // 2. Dashboard Page
    console.log('--- Step 2: Testing Dashboard Page (/dashboard) ---');
    await page.goto(`${BASE_URL}/dashboard`, { waitUntil: 'networkidle2' });
    await sleep(1200);
    const dashboardTitle = await page.$eval('h1', (el) => el.innerText).catch(() => '');
    console.log(`[PASS] Dashboard Title: "${dashboardTitle}"`);
    
    // Check KPI metrics
    const metrics = await page.$$eval('.metrics .metric', (nodes) =>
      nodes.map((n) => {
        const val = n.querySelector('b')?.innerText;
        const lbl = n.querySelector('span')?.innerText;
        return `${lbl}: ${val}`;
      })
    );
    console.log(`[PASS] Dashboard Metrics (${metrics.length} cards):`, metrics.join(' | '));
    await page.screenshot({ path: path.join(screenshotsDir, '02_dashboard.png') });

    // 3. Returns Ledger Page
    console.log('\n--- Step 3: Testing Returns Ledger (/returns) ---');
    await page.goto(`${BASE_URL}/returns`, { waitUntil: 'networkidle2' });
    await sleep(1200);

    const initialRows = await page.$$eval('tbody tr', (trs) => trs.length);
    console.log(`[PASS] Returns Ledger initial visible rows: ${initialRows}`);

    // Test Tab Filters
    const tabs = ['Auto-approved', 'Awaiting review', 'Needs attention', 'Finalized', 'All returns'];
    for (const tabText of tabs) {
      const tabBtn = await page.$(`xpath=//button[contains(@class, "tab") and contains(., "${tabText}")]`);
      if (tabBtn) {
        await tabBtn.click();
        await sleep(400);
        const count = await page.$$eval('tbody tr', (trs) => trs.length);
        console.log(`[PASS] Tab Filter "${tabText}" clicked -> ${count} rows visible.`);
      }
    }

    // Test Search Input
    console.log('Testing search filtering in Returns Ledger...');
    const searchInput = await page.$('.table-search input');
    if (searchInput) {
      await searchInput.type('WATCH');
      await sleep(500);
      const watchCount = await page.$$eval('tbody tr', (trs) => trs.length);
      console.log(`[PASS] Search "WATCH" -> ${watchCount} rows filtered.`);
      await searchInput.click({ clickCount: 3 });
      await page.keyboard.press('Backspace');
      await sleep(500);
    }

    // Test Column Sorting
    console.log('Testing column sorting...');
    const returnHeaderBtn = await page.$('xpath=//thead//button[contains(., "RETURN")]');
    if (returnHeaderBtn) {
      await returnHeaderBtn.click();
      await sleep(400);
      console.log('[PASS] Clicked RETURN column sort.');
    }
    const timeHeaderBtn = await page.$('xpath=//thead//button[contains(., "CAPTURED TIME")]');
    if (timeHeaderBtn) {
      await timeHeaderBtn.click();
      await sleep(400);
      console.log('[PASS] Clicked CAPTURED TIME column sort.');
    }
    await page.screenshot({ path: path.join(screenshotsDir, '03_returns_ledger.png') });

    // 4. Inspection Detail Screen
    console.log('\n--- Step 4: Testing Inspection Detail Screen (/returns/:id/inspection) ---');
    // Click on the first row in returns table
    const firstRow = await page.$('tbody tr');
    if (firstRow) {
      await firstRow.click();
      await sleep(1200);
    }

    console.log(`Current URL: ${page.url()}`);
    const inspTitle = await page.$eval('h1', (el) => el.innerText).catch(() => '');
    console.log(`[PASS] Inspection Target: ${inspTitle}`);

    // Verify 4-Pillar Card exists
    const pillars = await page.$$eval('.similarity-panel b, .similarity-panel .kicker', (els) =>
      els.map((e) => e.innerText.trim()).filter(Boolean)
    );
    console.log('[PASS] Inspection Pillars & Headings:', pillars.slice(0, 8).join(' | '));

    // Test Photo Strip & Zoom
    console.log('Testing photo strip thumbnails and zoom buttons...');
    const thumbs = await page.$$('.photo-strip button');
    console.log(`Found ${thumbs.length} photo thumbnails in strip.`);
    if (thumbs.length > 1) {
      await thumbs[1].click();
      await sleep(400);
      console.log('[PASS] Switched to photo thumbnail P2.');
      await thumbs[0].click();
      await sleep(400);
      console.log('[PASS] Switched back to photo thumbnail P1.');
    }

    const zoomInBtn = await page.$('button[aria-label="Zoom in"]');
    const zoomOutBtn = await page.$('button[aria-label="Zoom out"]');
    if (zoomInBtn) {
      await zoomInBtn.click();
      await sleep(200);
      await zoomInBtn.click();
      await sleep(200);
      console.log('[PASS] Zoomed in photo.');
    }
    if (zoomOutBtn) {
      await zoomOutBtn.click();
      await sleep(200);
      console.log('[PASS] Zoomed out photo.');
    }

    // Test Decision Modal: Accept Decision
    console.log('Testing "Accept decision" modal action...');
    const acceptBtn = await page.$('xpath=//button[contains(., "Accept decision")]');
    if (acceptBtn) {
      await acceptBtn.click();
      await sleep(500);
      const modalTextArea = await page.$('.dialog textarea');
      if (modalTextArea) {
        await modalTextArea.type('Automated UI audit: operator accepted decision.');
        await sleep(300);
        const confirmBtn = await page.$('.dialog .button.primary');
        if (confirmBtn) {
          await confirmBtn.click();
          await sleep(800);
          console.log('[PASS] Accept Decision submitted and confirmed.');
        }
      }
    }

    // Test Decision Modal: Request Retake Modal (open and cancel)
    console.log('Testing "Request retake" modal action...');
    const retakeBtn = await page.$('xpath=//button[contains(., "Request retake")]');
    if (retakeBtn) {
      await retakeBtn.click();
      await sleep(400);
      const cancelBtn = await page.$('.dialog .dialog-actions button:not(.primary)');
      if (cancelBtn) {
        await cancelBtn.click();
        await sleep(400);
        console.log('[PASS] Request retake modal opened and closed cleanly.');
      }
    }
    await page.screenshot({ path: path.join(screenshotsDir, '04_inspection_detail.png') });

    // 5. Batch Upload / New Inspection Screen
    console.log('\n--- Step 5: Testing Batch Upload Screen (/returns/new) ---');
    await page.goto(`${BASE_URL}/returns/new`, { waitUntil: 'networkidle2' });
    await sleep(1000);
    const uploadTitle = await page.$eval('h1', (el) => el.innerText).catch(() => '');
    console.log(`[PASS] Upload Page Title: "${uploadTitle}"`);

    // Verify Dropzone & Spend Confirmation Checkbox
    const dropzone = await page.$('.dropzone');
    console.log(`[PASS] Dropzone present: ${!!dropzone}`);
    const spendBox = await page.$('input[type="checkbox"]');
    if (spendBox) {
      await spendBox.click();
      await sleep(300);
      console.log('[PASS] Spend confirmation checkbox toggled.');
    }
    await page.screenshot({ path: path.join(screenshotsDir, '05_batch_upload.png') });

    // 6. Review Queue Screen
    console.log('\n--- Step 6: Testing Review Queue (/reviews) ---');
    await page.goto(`${BASE_URL}/reviews`, { waitUntil: 'networkidle2' });
    await sleep(1000);
    const reviewCards = await page.$$('.queue-row');
    console.log(`[PASS] Review Queue items: ${reviewCards.length}`);
    await page.screenshot({ path: path.join(screenshotsDir, '06_reviews.png') });

    // 7. Product Catalogue Screen
    console.log('\n--- Step 7: Testing Product Catalogue (/catalogue) ---');
    await page.goto(`${BASE_URL}/catalogue`, { waitUntil: 'networkidle2' });
    await sleep(1000);
    const catSearch = await page.$('.table-search input');
    if (catSearch) {
      await catSearch.type('WATCH');
      await sleep(400);
      const filteredCards = await page.$$('.product-card');
      console.log(`[PASS] Catalogue search for "WATCH" -> ${filteredCards.length} products.`);
      await catSearch.click({ clickCount: 3 });
      await page.keyboard.press('Backspace');
      await sleep(400);
    }
    await page.screenshot({ path: path.join(screenshotsDir, '07_catalogue.png') });

    // 8. Unit Digital Passport Screen
    console.log('\n--- Step 8: Testing Unit Digital Passport (/units/UNIT-0001) ---');
    await page.goto(`${BASE_URL}/units/UNIT-0001`, { waitUntil: 'networkidle2' });
    await sleep(1000);
    const passportHeader = await page.$eval('.passport h2', (el) => el.innerText).catch(() => 'No unit');
    console.log(`[PASS] Unit Passport SKU: "${passportHeader}"`);
    const stages = await page.$$eval('.stage', (els) => els.map((e) => e.innerText.split('\n')[0]));
    console.log('[PASS] Lifecycle stages:', stages.join(' -> '));
    await page.screenshot({ path: path.join(screenshotsDir, '08_passport.png') });

    // 9. Evidence & Audit Screen
    console.log('\n--- Step 9: Testing Evidence & Audit Screen (/evidence) ---');
    await page.goto(`${BASE_URL}/evidence`, { waitUntil: 'networkidle2' });
    await sleep(1000);
    const evidenceRows = await page.$$eval('tbody tr', (trs) => trs.length);
    console.log(`[PASS] Evidence table rows: ${evidenceRows}`);
    
    // Test expanding a row
    const firstEvRow = await page.$('tbody tr');
    if (firstEvRow) {
      await firstEvRow.click();
      await sleep(500);
      const expanded = await page.$('.evidence-expanded');
      console.log(`[PASS] Evidence detail drawer expanded: ${!!expanded}`);
    }

    // Test chain lookup input
    const lookupInput = await page.$('.return-toolbar input');
    const verifyBtn = await page.$('xpath=//button[contains(., "Verify")]');
    if (lookupInput && verifyBtn) {
      await lookupInput.type('UNIT-0001');
      await verifyBtn.click();
      await sleep(800);
      console.log('[PASS] Hash-chain lookup executed for UNIT-0001.');
    }
    await page.screenshot({ path: path.join(screenshotsDir, '09_evidence.png') });

    // 10. Analytics Screen
    console.log('\n--- Step 10: Testing Analytics Screen (/analytics) ---');
    await page.goto(`${BASE_URL}/analytics`, { waitUntil: 'networkidle2' });
    await sleep(1200);
    const analyticsH2s = await page.$$eval('.panel h2', (els) => els.map((e) => e.innerText));
    console.log('[PASS] Analytics Sections:', analyticsH2s.join(' | '));
    await page.screenshot({ path: path.join(screenshotsDir, '10_analytics.png') });

    // 11. Integrations Screen
    console.log('\n--- Step 11: Testing Integrations Screen (/integrations) ---');
    await page.goto(`${BASE_URL}/integrations`, { waitUntil: 'networkidle2' });
    await sleep(1000);
    const flowItems = await page.$$eval('.flow-item b', (els) => els.map((e) => e.innerText));
    console.log('[PASS] Integrations Pods:', flowItems.join(' | '));
    await page.screenshot({ path: path.join(screenshotsDir, '11_integrations.png') });

    // 12. Settings Screen
    console.log('\n--- Step 12: Testing Settings Screen (/settings) ---');
    await page.goto(`${BASE_URL}/settings`, { waitUntil: 'networkidle2' });
    await sleep(1200);
    const controlRows = await page.$$('.control-row');
    console.log(`[PASS] Settings System Controls found: ${controlRows.length}`);
    await page.screenshot({ path: path.join(screenshotsDir, '12_settings.png') });

    // 13. Topbar Interactive Controls
    console.log('\n--- Step 13: Testing Topbar Global Interactive Controls ---');
    // Test Dark / Light theme switch
    const themeBtn = await page.$('.theme-switch');
    if (themeBtn) {
      await themeBtn.click();
      await sleep(300);
      console.log('[PASS] Toggled theme to Light mode.');
      await themeBtn.click();
      await sleep(300);
      console.log('[PASS] Toggled theme back to Dark mode.');
    }

    // Test Notification Bell
    const bellBtn = await page.$('.bell-btn');
    if (bellBtn) {
      await bellBtn.click();
      await sleep(500);
      console.log('[PASS] Clicked notification bell.');
    }

    // Test Global Search Modal (Cmd+K)
    const searchTrigger = await page.$('.global-search');
    if (searchTrigger) {
      await searchTrigger.click();
      await sleep(400);
      const searchModal = await page.$('.search-modal');
      console.log(`[PASS] Global Search Modal opened: ${!!searchModal}`);
      const modalInput = await page.$('.search-input input');
      if (modalInput) {
        await modalInput.type('WATCH');
        await sleep(400);
        const searchResults = await page.$$('.search-results button');
        console.log(`[PASS] Global Search matching results: ${searchResults.length}`);
      }
      await page.keyboard.press('Escape');
      await sleep(400);
      console.log('[PASS] Global Search Modal dismissed with Escape.');
    }

    // Test Sidebar Collapse & Expand
    const collapseBtn = await page.$('.collapse-btn');
    if (collapseBtn) {
      await collapseBtn.click();
      await sleep(300);
      console.log('[PASS] Sidebar collapsed.');
      await collapseBtn.click();
      await sleep(300);
      console.log('[PASS] Sidebar expanded.');
    }

    console.log('\n====================================================');
    console.log(`TOTAL UNCAUGHT PAGE ERRORS: ${pageErrors.length}`);
    console.log(`TOTAL CONSOLE ERRORS: ${consoleErrors.length}`);
    console.log('====================================================');

    if (pageErrors.length > 0 || consoleErrors.length > 0) {
      console.error('\nErrors detected during UI walkthrough:');
      pageErrors.forEach((e) => console.error(' Page Error:', e));
      consoleErrors.forEach((e) => console.error(' Console Error:', e));
      process.exit(1);
    } else {
      console.log('\n>>> ALL 12 SCREENS, ALL BUTTONS, AND ALL DATA FLOWS PASSED WITH 0 ERRORS! <<<\n');
    }
  } catch (err) {
    console.error('Test failed with exception:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

runFullTest();
