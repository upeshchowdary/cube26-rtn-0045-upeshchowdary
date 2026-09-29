const puppeteer = require('./node_modules/puppeteer-core');

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE_URL = 'http://localhost:5175';
const API_KEY = 'rmk_local_s8dPJ1uaqqsA89grddXAj3SEUEKIWPbthNkKURXH';

async function test() {
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  const page = await browser.newPage();

  page.on('console', msg => console.log('BROWSER LOG:', msg.type(), msg.text()));
  page.on('request', req => {
    if (req.url().includes('/api/')) console.log('API REQ:', req.method(), req.url(), 'Key:', req.headers()['x-api-key']);
  });
  page.on('response', resp => {
    if (resp.url().includes('/api/')) console.log('API RESP:', resp.status(), resp.url());
  });

  // First open /overview to establish origin
  await page.goto(`${BASE_URL}/overview`, { waitUntil: 'domcontentloaded' });
  await page.evaluate((key) => {
    localStorage.setItem('rm_api_key', key);
    console.log('Set key:', localStorage.getItem('rm_api_key'));
  }, API_KEY);

  // Now navigate to /returns
  await page.goto(`${BASE_URL}/returns`, { waitUntil: 'domcontentloaded' });
  await new Promise(r => setTimeout(r, 3000));

  const content = await page.evaluate(() => {
    return {
      connectedKey: localStorage.getItem('rm_api_key'),
      hasTable: !!document.querySelector('table'),
      trCount: document.querySelectorAll('tbody tr').length,
      bodyText: document.body.innerText.slice(0, 300)
    };
  });
  console.log('Page state:', content);

  await browser.close();
}

test();
