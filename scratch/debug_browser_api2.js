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
    console.log('REQ:', req.method(), req.url());
  });
  page.on('response', resp => {
    if (resp.status() >= 400) console.log('ERROR RESP:', resp.status(), resp.url());
  });

  // First open /overview to establish origin
  await page.goto(`${BASE_URL}/overview`, { waitUntil: 'domcontentloaded' });
  await page.evaluate((key) => {
    localStorage.setItem('rm_api_key', key);
  }, API_KEY);

  // Now navigate to /returns
  await page.goto(`${BASE_URL}/returns`, { waitUntil: 'domcontentloaded' });
  await new Promise(r => setTimeout(r, 4000));

  // Check what jobs and rows were fetched
  const storeState = await page.evaluate(async () => {
    const jobs = await fetch('http://127.0.0.1:8000/api/v1/batch/jobs', {
      headers: { 'X-API-Key': localStorage.getItem('rm_api_key') }
    }).then(r => r.json());

    return {
      jobsCount: jobs.length,
      firstJob: jobs[0]
    };
  });
  console.log('Store state from page:', storeState);

  await browser.close();
}

test();
