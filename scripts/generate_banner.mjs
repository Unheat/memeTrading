import puppeteer from '/Users/dangtruongan/study/Kites/node_modules/puppeteer/lib/esm/puppeteer/puppeteer.js';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, '..');
const outPath = path.resolve(rootDir, 'README_images/hero_banner.png');

async function renderBanner() {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--font-render-hinting=none']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 880, deviceScaleFactor: 2 });

  const html = `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        * {
          box-sizing: border-box;
          margin: 0;
          padding: 0;
          font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", "Segoe UI", Roboto, sans-serif;
          -webkit-font-smoothing: antialiased;
        }

        body {
          width: 1920px;
          height: 880px;
          background: #060913;
          color: #f8fafc;
          overflow: hidden;
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: space-between;
          padding: 60px 90px 50px 90px;
        }

        /* Subtle ambient glow & grid background */
        .ambient-glow-1 {
          position: absolute;
          width: 800px;
          height: 450px;
          top: -120px;
          left: 50%;
          transform: translateX(-50%);
          background: radial-gradient(circle, rgba(14, 165, 233, 0.18) 0%, rgba(59, 130, 246, 0.08) 45%, transparent 70%);
          filter: blur(80px);
          pointer-events: none;
        }

        .ambient-glow-2 {
          position: absolute;
          width: 600px;
          height: 350px;
          bottom: -80px;
          left: 15%;
          background: radial-gradient(circle, rgba(168, 85, 247, 0.12) 0%, transparent 65%);
          filter: blur(90px);
          pointer-events: none;
        }

        .ambient-glow-3 {
          position: absolute;
          width: 600px;
          height: 350px;
          bottom: -80px;
          right: 15%;
          background: radial-gradient(circle, rgba(16, 185, 129, 0.12) 0%, transparent 65%);
          filter: blur(90px);
          pointer-events: none;
        }

        .grid-overlay {
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background-image: 
            linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
          background-size: 48px 48px;
          mask-image: radial-gradient(ellipse at 50% 45%, black 40%, transparent 80%);
          pointer-events: none;
        }

        /* Top badges bar */
        .top-badges {
          display: flex;
          align-items: center;
          gap: 14px;
          z-index: 2;
        }

        .pill-badge {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 7px 18px;
          border-radius: 9999px;
          font-size: 13px;
          font-weight: 700;
          letter-spacing: 0.8px;
          text-transform: uppercase;
          border: 1px solid rgba(255, 255, 255, 0.1);
          background: rgba(15, 23, 42, 0.6);
          backdrop-filter: blur(12px);
        }

        .pill-badge.cyan {
          color: #38bdf8;
          border-color: rgba(56, 189, 248, 0.3);
          background: rgba(56, 189, 248, 0.08);
        }

        .pill-badge.emerald {
          color: #34d399;
          border-color: rgba(52, 211, 153, 0.3);
          background: rgba(52, 211, 153, 0.08);
        }

        .pill-badge.purple {
          color: #c084fc;
          border-color: rgba(192, 132, 252, 0.3);
          background: rgba(192, 132, 252, 0.08);
        }

        /* Header typography */
        .header-section {
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          z-index: 2;
          margin-top: 10px;
        }

        .main-title {
          font-size: 74px;
          font-weight: 900;
          letter-spacing: -2px;
          line-height: 1.05;
          margin-bottom: 14px;
          background: linear-gradient(135deg, #ffffff 30%, #cbd5e1 65%, #38bdf8 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          display: flex;
          align-items: center;
          gap: 20px;
        }

        .main-title .search-icon {
          -webkit-text-fill-color: initial;
          font-size: 68px;
        }

        .subtitle {
          font-size: 24px;
          font-weight: 500;
          color: #94a3b8;
          letter-spacing: -0.3px;
          max-width: 1100px;
          line-height: 1.4;
        }

        .subtitle strong {
          color: #e2e8f0;
          font-weight: 600;
        }

        /* Unique Selling Points 4-Card Grid */
        .usp-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 24px;
          width: 100%;
          z-index: 2;
          margin-top: 28px;
        }

        .usp-card {
          background: rgba(15, 23, 42, 0.55);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 18px;
          padding: 24px 22px;
          display: flex;
          flex-direction: column;
          position: relative;
          backdrop-filter: blur(14px);
          transition: all 0.2s ease;
        }

        .usp-card::before {
          content: "";
          position: absolute;
          top: 0;
          left: 20px;
          right: 20px;
          height: 1px;
          background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.15), transparent);
        }

        .card-header {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 12px;
        }

        .card-icon {
          width: 40px;
          height: 40px;
          border-radius: 10px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 20px;
          flex-shrink: 0;
        }

        .card-icon.blue { background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.25); color: #38bdf8; }
        .card-icon.emerald { background: rgba(52, 211, 153, 0.12); border: 1px solid rgba(52, 211, 153, 0.25); color: #34d399; }
        .card-icon.purple { background: rgba(192, 132, 252, 0.12); border: 1px solid rgba(192, 132, 252, 0.25); color: #c084fc; }
        .card-icon.amber { background: rgba(251, 191, 36, 0.12); border: 1px solid rgba(251, 191, 36, 0.25); color: #fbbf24; }

        .card-title-group {
          display: flex;
          flex-direction: column;
        }

        .card-title {
          font-size: 17px;
          font-weight: 700;
          color: #f1f5f9;
          line-height: 1.25;
        }

        .card-method {
          font-size: 11px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-top: 2px;
        }

        .card-method.blue { color: #38bdf8; }
        .card-method.emerald { color: #34d399; }
        .card-method.purple { color: #c084fc; }
        .card-method.amber { color: #fbbf24; }

        .card-desc {
          font-size: 13.5px;
          color: #94a3b8;
          line-height: 1.5;
          margin-top: 4px;
        }

        /* Bottom Feature Ticker */
        .bottom-bar {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 36px;
          width: 100%;
          padding-top: 20px;
          border-top: 1px solid rgba(255, 255, 255, 0.06);
          z-index: 2;
        }

        .feature-item {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 14px;
          font-weight: 600;
          color: #cbd5e1;
        }

        .feature-dot {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background: #38bdf8;
          box-shadow: 0 0 10px #38bdf8;
        }

        .feature-dot.green { background: #10b981; box-shadow: 0 0 10px #10b981; }
        .feature-dot.purple { background: #a855f7; box-shadow: 0 0 10px #a855f7; }
        .feature-dot.amber { background: #f59e0b; box-shadow: 0 0 10px #f59e0b; }
      </style>
    </head>
    <body>
      <div class="ambient-glow-1"></div>
      <div class="ambient-glow-2"></div>
      <div class="ambient-glow-3"></div>
      <div class="grid-overlay"></div>

      <!-- Top Tag Badges -->
      <div class="top-badges">
        <div class="pill-badge cyan">
          <span>⚡</span>
          <span>Grassroots-To-Footnote Diligence</span>
        </div>
        <div class="pill-badge emerald">
          <span>🛡️</span>
          <span>Deterministic SEC Accounting</span>
        </div>
        <div class="pill-badge purple">
          <span>🏛️</span>
          <span>Wall Street Decision Gates</span>
        </div>
      </div>

      <!-- Header / Title -->
      <div class="header-section">
        <div class="main-title">
          <span class="search-icon">🔎</span>
          <span>MemeForensics</span>
        </div>
        <p class="subtitle">
          An institutional-grade <strong>LangGraph research agent</strong> bridging grassroots narrative velocity with 
          <strong>audited SEC filings</strong>, <strong>Reverse DCF math</strong>, and <strong>viral character reels</strong>.
        </p>
      </div>

      <!-- 4 Core USPs -->
      <div class="usp-grid">
        <div class="usp-card">
          <div class="card-header">
            <div class="card-icon blue">🌐</div>
            <div class="card-title-group">
              <span class="card-title">Scuttlebutt Discovery</span>
              <span class="card-method blue">Fisher & Lynch Method</span>
            </div>
          </div>
          <p class="card-desc">
            Detects real physical supply shortages, hardware bottlenecks, and narrative momentum on Reddit, forums, and specialized news before Wall Street.
          </p>
        </div>

        <div class="usp-card">
          <div class="card-header">
            <div class="card-icon emerald">📑</div>
            <div class="card-title-group">
              <span class="card-title">SEC Forensic Audit</span>
              <span class="card-method emerald">Beneish & Sloan Shield</span>
            </div>
          </div>
          <p class="card-desc">
            Audits 10-K/10-Q filings with accession receipts. De-cumulates YTD cash flows, tracks inventory DIO drift, and flags manipulation risk.
          </p>
        </div>

        <div class="usp-card">
          <div class="card-header">
            <div class="card-icon purple">📉</div>
            <div class="card-title-group">
              <span class="card-title">Reverse Expectations</span>
              <span class="card-method purple">Michael Mauboussin DCF</span>
            </div>
          </div>
          <p class="card-desc">
            Solves DCF backwards: backs out the exact implied cash-flow growth hurdle and ROIC priced into current shares. No price guessing.
          </p>
        </div>

        <div class="usp-card">
          <div class="card-header">
            <div class="card-icon amber">🎬</div>
            <div class="card-title-group">
              <span class="card-title">Dual Deliverables</span>
              <span class="card-method amber">Memos + Viral Reels</span>
            </div>
          </div>
          <p class="card-desc">
            Emits audit-ready investment memos with 5-year financials alongside 60-second animated dialogue reels (Peter & Stewie / Rick & Morty).
          </p>
        </div>
      </div>

      <!-- Bottom Status Bar -->
      <div class="bottom-bar">
        <div class="feature-item">
          <span class="feature-dot"></span>
          <span>Zero LLM Hallucinations</span>
        </div>
        <div class="feature-item">
          <span class="feature-dot green"></span>
          <span>Immutable SEC Disk Receipts</span>
        </div>
        <div class="feature-item">
          <span class="feature-dot purple"></span>
          <span>Point-in-Time (PIT) Backtesting</span>
        </div>
        <div class="feature-item">
          <span class="feature-dot amber"></span>
          <span>Fractional Kelly Position Sizing</span>
        </div>
      </div>
    </body>
    </html>
  `;

  await page.setContent(html, { waitUntil: 'networkidle0' });
  await page.screenshot({ path: outPath, type: 'png' });
  await browser.close();

  console.log(`✅ Banner successfully generated at: ${outPath}`);
}

renderBanner().catch((err) => {
  console.error('❌ Failed to render banner:', err);
  process.exit(1);
});
