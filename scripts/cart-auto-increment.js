/**
 * プレミアムバンダイ カート内商品の個数を自動変更するスクリプト
 *
 * 使い方:
 *   1. node scripts/cart-auto-increment.js
 *   2. ブラウザが開き、自動ログイン後にカート処理開始
 *
 * 動作:
 *   - 自動ログイン
 *   - カートページをリロード
 *   - 各商品のselect要素を検出
 *   - 現在の値が最大値未満（最大4）なら変更して送信
 *   - 3秒おきにリロード→選択を繰り返す
 */

const puppeteer = require('puppeteer-core');
const readline = require('readline');

const LOGIN_URL = 'https://p-bandai.jp/login/?c=1';
const CART_URL = 'https://p-bandai.jp/cart/';
const LOGIN_ID = 'kenduen@gmail.com';
const LOGIN_PW = 'ken0325';
const MAX_QTY = 4;
const RELOAD_INTERVAL_MS = 3000;

function waitForEnter(prompt) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(prompt, () => {
      rl.close();
      resolve();
    });
  });
}

async function findChromePath() {
  const { execSync } = require('child_process');
  const candidates = [
    'google-chrome',
    'google-chrome-stable',
    'chromium',
    'chromium-browser',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  ];
  for (const c of candidates) {
    try {
      const resolved = execSync(`which "${c}" 2>/dev/null || where "${c}" 2>nul`, {
        encoding: 'utf-8',
        timeout: 3000,
      }).trim();
      if (resolved) return resolved;
    } catch (_) {}
  }
  // Try common macOS/Windows paths directly
  const fs = require('fs');
  const directPaths = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  ];
  for (const p of directPaths) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

async function main() {
  const chromePath = await findChromePath();

  let browser;
  if (chromePath) {
    console.log(`Chrome検出: ${chromePath}`);
    browser = await puppeteer.launch({
      executablePath: chromePath,
      headless: false,
      defaultViewport: null,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--start-maximized'],
    });
  } else {
    // puppeteer-core にはバンドルされたブラウザがないので、
    // フルのpuppeteerが必要
    console.error('Chromeが見つかりません。');
    console.error('以下のいずれかをインストールしてください:');
    console.error('  - Google Chrome');
    console.error('  - Chromium');
    console.error('または、npm install puppeteer でバンドル版をインストール');
    process.exit(1);
  }

  const page = (await browser.pages())[0] || (await browser.newPage());

  // 自動ログイン
  console.log('ログインページを開きます...');
  await page.goto(LOGIN_URL, { waitUntil: 'networkidle2', timeout: 60000 });

  // ログインフォームに入力
  console.log('ログインID・パスワードを入力中...');
  await page.waitForSelector('#login_id', { timeout: 10000 });
  await page.type('#login_id', LOGIN_ID, { delay: 50 });
  await page.type('#password', LOGIN_PW, { delay: 50 });

  // ログインボタンをクリック
  console.log('ログインボタンをクリック...');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 }),
    page.click('#btnLogin'),
  ]);
  console.log('ログイン完了。');

  await waitForEnter('\nカート処理を開始するにはEnterを押してください...');

  console.log('自動処理を開始します...');
  let round = 0;

  while (true) {
    round++;
    console.log(`\n--- ラウンド ${round} ---`);

    // カートページへ遷移/リロード
    try {
      await page.goto(CART_URL, { waitUntil: 'networkidle2', timeout: 30000 });
    } catch (e) {
      console.log(`ページ読み込みエラー: ${e.message}`);
      await sleep(RELOAD_INTERVAL_MS);
      continue;
    }

    // select要素を検出して数量変更
    const result = await page.evaluate((maxQty) => {
      const selects = document.querySelectorAll('select[name^="odr_"]');
      if (selects.length === 0) {
        return { found: 0, changed: 0, details: [] };
      }

      let changed = 0;
      const details = [];

      selects.forEach((select) => {
        const currentVal = parseInt(select.value, 10);
        const options = Array.from(select.options);
        const maxAvailable = Math.max(...options.map((o) => parseInt(o.value, 10)).filter((v) => !isNaN(v)));
        const targetVal = Math.min(maxQty, maxAvailable);

        details.push({
          name: select.name,
          current: currentVal,
          maxAvailable,
          target: targetVal,
        });

        if (currentVal < targetVal) {
          // 値を1つずつ上げるのではなく、直接ターゲット値に設定
          select.value = String(targetVal);
          // onchangeイベントを発火させる
          const event = new Event('change', { bubbles: true });
          select.dispatchEvent(event);
          changed++;
        }
      });

      return { found: selects.length, changed, details };
    }, MAX_QTY);

    console.log(`商品数: ${result.found}`);
    result.details.forEach((d) => {
      console.log(`  ${d.name}: 現在=${d.current}, 最大=${d.maxAvailable}, 目標=${d.target}`);
    });

    if (result.changed > 0) {
      console.log(`${result.changed}件の数量を変更しました。フォーム送信中...`);

      // onchangeでsubmitされるが、念のため手動でもsubmit
      try {
        await page.evaluate(() => {
          const form = document.querySelector('form[name="recalc"]');
          if (form) form.submit();
        });
        // ページ遷移を待つ
        await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 }).catch(() => {});
      } catch (e) {
        console.log(`フォーム送信エラー: ${e.message}`);
      }

      console.log('数量変更完了。');
    } else {
      console.log('変更不要（全て目標数量に到達済み、または商品なし）');

      // 全商品が目標に達しているか確認
      const allMaxed = result.found > 0 && result.details.every((d) => d.current >= Math.min(MAX_QTY, d.maxAvailable));
      if (allMaxed) {
        console.log('\n全商品が最大数量に達しました。完了！');
        break;
      }
    }

    console.log(`${RELOAD_INTERVAL_MS / 1000}秒後にリロードします...`);
    await sleep(RELOAD_INTERVAL_MS);
  }

  await waitForEnter('\n処理完了。Enterでブラウザを閉じます...');
  await browser.close();
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

main().catch((err) => {
  console.error('エラー:', err);
  process.exit(1);
});
