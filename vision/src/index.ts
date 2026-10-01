import { Hono } from 'hono';
import path from 'node:path';
import sharp from 'sharp';
import { createWorker } from 'tesseract.js';

const app = new Hono();

type BBox = { x0: number; y0: number; x1: number; y1: number };
type OcrLine = { text: string; bbox: BBox };
type OcrWord = { text: string; bbox: BBox };
type PageOcr = {
  text: string;
  lines: OcrLine[];
  words: OcrWord[];
  width: number;
  height: number;
  image: Buffer;
};

let workerPromise: ReturnType<typeof createWorker> | null = null;

function getWorker() {
  if (!workerPromise) {
    workerPromise = createWorker('eng', undefined, {
      corePath: path.resolve(process.cwd(), 'src/tesseract-core'),
      langPath: 'https://tessdata.projectnaptha.com/4.0.0_fast',
      logger: (message) => {
        if (message?.status === 'recognizing text' && message?.progress === 1) {
          console.log('LOCAL_OCR_PAGE_COMPLETE');
        }
      },
    });
  }
  return workerPromise;
}

function dataUrlToBuffer(value: string): Buffer {
  const match = /^data:[^;]+;base64,(.+)$/s.exec(value || '');
  if (!match) throw new Error('Invalid image data URL');
  return Buffer.from(match[1], 'base64');
}

function flattenBlocks(blocks: any[] | null | undefined): { lines: OcrLine[]; words: OcrWord[] } {
  const lines: OcrLine[] = [];
  const words: OcrWord[] = [];
  for (const block of blocks || []) {
    for (const paragraph of block?.paragraphs || []) {
      for (const line of paragraph?.lines || []) {
        if (line?.text && line?.bbox) {
          lines.push({ text: String(line.text).trim(), bbox: line.bbox });
        }
        for (const word of line?.words || []) {
          if (word?.text && word?.bbox) {
            words.push({ text: String(word.text).trim(), bbox: word.bbox });
          }
        }
      }
    }
  }
  return { lines, words };
}

async function recognizePage(dataUrl: string): Promise<PageOcr> {
  const image = dataUrlToBuffer(dataUrl);
  const metadata = await sharp(image).metadata();
  const width = Number(metadata.width || 0);
  const height = Number(metadata.height || 0);
  if (!width || !height) throw new Error('Unable to determine image size');

  const worker = await getWorker();
  const result = await worker.recognize(image, { rotateAuto: true }, { text: true, blocks: true });
  const flat = flattenBlocks(result.data.blocks as any[] | null | undefined);
  return {
    text: String(result.data.text || '').trim(),
    lines: flat.lines,
    words: flat.words,
    width,
    height,
    image,
  };
}

function norm(value: string): string {
  return String(value || '')
    .toUpperCase()
    .replace(/[^A-Z0-9 ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function customerTokens(value: string | null | undefined): Set<string> {
  return new Set(
    norm(value || '')
      .split(' ')
      .filter((token) => token.length >= 3 && !['TOKO', 'TB', 'CV', 'PT', 'UD'].includes(token)),
  );
}

function overlapScore(text: string, expected: string | null | undefined): number {
  const a = customerTokens(text);
  const b = customerTokens(expected || '');
  if (!a.size || !b.size) return 0;
  let hit = 0;
  for (const token of a) if (b.has(token)) hit += 1;
  return hit / Math.max(b.size, 1);
}

const ROLE_PATTERNS: Record<string, RegExp[]> = {
  receiver: [
    /\bPENERIMA\b/i,
    /DITERIMA\s+OLEH/i,
    /BARANG\s+TELAH\s+DITERIMA/i,
    /CUSTOMER/i,
  ],
  driver: [/\bDRIVER\b/i, /\bSOPIR\b/i, /PENGEMUDI/i, /EKSPEDISI/i],
  security: [/SECURITY/i, /SATPAM/i],
  bm: [/BRANCH\s+MANAGER/i, /(^|\s)BM(\s|$)/i],
  checker: [/CHECKER/i, /PEMERIKSA/i, /GUDANG/i, /QC\s+PENGIRIMAN/i],
};

function findRoleLabels(page: PageOcr): Array<{ role: string; bbox: BBox; text: string }> {
  const found: Array<{ role: string; bbox: BBox; text: string }> = [];
  for (const line of page.lines) {
    for (const [role, patterns] of Object.entries(ROLE_PATTERNS)) {
      if (patterns.some((pattern) => pattern.test(line.text))) {
        found.push({ role, bbox: line.bbox, text: line.text });
        break;
      }
    }
  }
  return found;
}

function roleRegion(
  page: PageOcr,
  label: { role: string; bbox: BBox },
  allLabels: Array<{ role: string; bbox: BBox }>,
): BBox {
  const cy = (label.bbox.y0 + label.bbox.y1) / 2;
  const cx = (label.bbox.x0 + label.bbox.x1) / 2;
  const sameBand = allLabels
    .filter((item) => {
      const itemCy = (item.bbox.y0 + item.bbox.y1) / 2;
      return Math.abs(itemCy - cy) <= page.height * 0.12;
    })
    .sort((a, b) => (a.bbox.x0 + a.bbox.x1) / 2 - (b.bbox.x0 + b.bbox.x1) / 2);

  const centers = sameBand.map((item) => ({
    role: item.role,
    center: (item.bbox.x0 + item.bbox.x1) / 2,
  }));
  const index = centers.findIndex((item) => item.role === label.role && Math.abs(item.center - cx) < 3);
  const left =
    index > 0
      ? (centers[index - 1].center + cx) / 2
      : Math.max(0, cx - page.width * 0.12);
  const right =
    index >= 0 && index < centers.length - 1
      ? (cx + centers[index + 1].center) / 2
      : Math.min(page.width, cx + page.width * 0.12);

  return {
    x0: Math.max(0, Math.floor(left)),
    x1: Math.min(page.width, Math.ceil(right)),
    y0: Math.max(0, Math.floor(label.bbox.y0 - page.height * 0.105)),
    y1: Math.min(page.height, Math.ceil(label.bbox.y1 + page.height * 0.065)),
  };
}

function intersects(a: BBox, b: BBox): boolean {
  return a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0;
}

async function residualInkStats(page: PageOcr, region: BBox) {
  const left = Math.max(0, Math.floor(region.x0));
  const top = Math.max(0, Math.floor(region.y0));
  const width = Math.max(1, Math.min(page.width - left, Math.floor(region.x1 - region.x0)));
  const height = Math.max(1, Math.min(page.height - top, Math.floor(region.y1 - region.y0)));
  const { data, info } = await sharp(page.image)
    .extract({ left, top, width, height })
    .removeAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });

  const pixels = info.width * info.height;
  const excluded = new Uint8Array(pixels);

  for (const word of page.words) {
    if (!intersects(word.bbox, region)) continue;
    const x0 = Math.max(0, Math.floor(word.bbox.x0 - left - 3));
    const y0 = Math.max(0, Math.floor(word.bbox.y0 - top - 3));
    const x1 = Math.min(info.width, Math.ceil(word.bbox.x1 - left + 3));
    const y1 = Math.min(info.height, Math.ceil(word.bbox.y1 - top + 3));
    for (let y = y0; y < y1; y++) {
      const row = y * info.width;
      for (let x = x0; x < x1; x++) excluded[row + x] = 1;
    }
  }

  const dark = new Uint8Array(pixels);
  const colored = new Uint8Array(pixels);
  for (let i = 0; i < pixels; i++) {
    if (excluded[i]) continue;
    const offset = i * info.channels;
    const r = data[offset] ?? 255;
    const g = data[offset + 1] ?? r;
    const b = data[offset + 2] ?? r;
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const brightness = (r + g + b) / 3;
    if (brightness < 170) dark[i] = 1;
    if (max - min > 42 && brightness < 235) colored[i] = 1;
  }

  // Remove table borders/long printed rules.
  const removeRows = new Uint8Array(info.height);
  const removeCols = new Uint8Array(info.width);
  for (let y = 0; y < info.height; y++) {
    let count = 0;
    for (let x = 0; x < info.width; x++) count += dark[y * info.width + x];
    if (count / info.width > 0.52) removeRows[y] = 1;
  }
  for (let x = 0; x < info.width; x++) {
    let count = 0;
    for (let y = 0; y < info.height; y++) count += dark[y * info.width + x];
    if (count / info.height > 0.52) removeCols[x] = 1;
  }

  let darkCount = 0;
  let colorCount = 0;
  for (let y = 0; y < info.height; y++) {
    for (let x = 0; x < info.width; x++) {
      if (removeRows[y] || removeCols[x]) continue;
      const i = y * info.width + x;
      darkCount += dark[i];
      colorCount += colored[i];
    }
  }

  return {
    darkRatio: darkCount / Math.max(pixels, 1),
    colorRatio: colorCount / Math.max(pixels, 1),
    darkCount,
    colorCount,
  };
}

function signatureFromStats(stats: { darkRatio: number; colorRatio: number; darkCount: number; colorCount: number }) {
  if (stats.colorCount >= 35 && stats.colorRatio >= 0.0007) {
    return { status: 'PRESENT', confidence: 0.9 };
  }
  if (stats.darkCount >= 180 && stats.darkRatio >= 0.0035) {
    return { status: 'PRESENT', confidence: 0.68 };
  }
  return { status: 'UNCLEAR', confidence: 0.25 };
}

function lineInside(line: OcrLine, region: BBox): boolean {
  const cx = (line.bbox.x0 + line.bbox.x1) / 2;
  const cy = (line.bbox.y0 + line.bbox.y1) / 2;
  return cx >= region.x0 && cx <= region.x1 && cy >= region.y0 && cy <= region.y1;
}

async function localAnalyze(images: string[], expectedCustomer?: string | null) {
  const pages: PageOcr[] = [];
  for (const image of images.slice(0, 3)) {
    pages.push(await recognizePage(String(image)));
  }

  const signatures: Record<string, { status: string; confidence: number; page_number: number | null }> = {};
  const roleBest: Record<string, { status: string; confidence: number; page_number: number | null }> = {};
  let stamp = { status: 'UNCLEAR', text: null as string | null, confidence: 0.2, page_number: null as number | null };
  let receiverName: string | null = null;

  for (let pageIndex = 0; pageIndex < pages.length; pageIndex++) {
    const page = pages[pageIndex];
    const labels = findRoleLabels(page);

    for (const label of labels) {
      const region = roleRegion(page, label, labels);
      const stats = await residualInkStats(page, region);
      const detected = signatureFromStats(stats);
      const previous = roleBest[label.role];
      if (!previous || detected.confidence > previous.confidence) {
        roleBest[label.role] = {
          ...detected,
          page_number: pageIndex + 1,
        };
      }

      if (label.role === 'receiver') {
        const regionLines = page.lines.filter((line) => lineInside(line, region));
        if (!receiverName) {
          const candidates = regionLines
            .map((line) => line.text.trim())
            .filter((text) => text.length >= 3)
            .filter((text) => !ROLE_PATTERNS.receiver.some((pattern) => pattern.test(text)))
            .filter((text) => overlapScore(text, expectedCustomer) < 0.8);
          receiverName = candidates.find((text) => /[A-Za-z]{3}/.test(text)) || null;
        }

        const stampTextCandidate = regionLines
          .map((line) => line.text.trim())
          .filter((text) => overlapScore(text, expectedCustomer) >= 0.5)
          .sort((a, b) => overlapScore(b, expectedCustomer) - overlapScore(a, expectedCustomer))[0];

        const stampPresentByColor = stats.colorCount >= 75 && stats.colorRatio >= 0.0012;
        const stampPresentByInk = stats.darkCount >= 500 && stats.darkRatio >= 0.008;
        if ((stampPresentByColor || stampPresentByInk) && stamp.confidence < 0.8) {
          stamp = {
            status: 'PRESENT',
            text: stampTextCandidate || null,
            confidence: stampPresentByColor ? 0.88 : 0.66,
            page_number: pageIndex + 1,
          };
        }
      }
    }
  }

  for (const role of ['receiver', 'driver', 'security', 'bm', 'checker']) {
    signatures[role] = roleBest[role] || {
      status: 'UNCLEAR',
      confidence: 0.15,
      page_number: null,
    };
  }

  const ocrText = pages.map((page, index) => `--- PAGE ${index + 1} ---\n${page.text}`).join('\n\n');

  return {
    engine: 'LOCAL_TESSERACT_VISUAL',
    billing_document: null,
    invoice_date: null,
    grand_total: null,
    spj_number: null,
    delivery_order_number: null,
    receiver_name: receiverName,
    partial_payments: [],
    signatures,
    stamp,
    notes: [
      'OCR teks dan deteksi visual dijalankan lokal tanpa AI Gateway berbayar.',
      'PRESENT tanda tangan/stempel berarti terdapat mark/ink visual pada area role; bukan autentikasi identitas.',
    ],
    ocr_text: ocrText,
  };
}

app.get('/health', (c) =>
  c.json({
    status: 'ok',
    service: 'vision',
    engine: 'LOCAL_TESSERACT_VISUAL',
  }),
);

app.get('/vision-ai-health', async (c) => {
  // Preview-only diagnostic route used while this branch is under test.
  return c.json({
    status: 'ok',
    engine: 'LOCAL_TESSERACT_VISUAL',
    paid_gateway_required: false,
  });
});

app.get('/vision-local-selftest', async (c) => {
  try {
    const svg = `
      <svg width="1200" height="900" xmlns="http://www.w3.org/2000/svg">
        <rect width="1200" height="900" fill="white"/>
        <text x="70" y="90" font-size="38" font-family="Arial">BILLING DOCUMENT 8501735930</text>
        <text x="70" y="145" font-size="34" font-family="Arial">NO SPJ S41C/202608/2501787882</text>
        <text x="70" y="200" font-size="34" font-family="Arial">GRAND TOTAL 3000000</text>
        <text x="70" y="255" font-size="34" font-family="Arial">PARTIAL PAYMENT 1000000</text>
        <rect x="60" y="560" width="1080" height="230" fill="none" stroke="black" stroke-width="3"/>
        <text x="90" y="620" font-size="30" font-family="Arial">PENERIMA</text>
        <text x="335" y="620" font-size="30" font-family="Arial">DRIVER</text>
        <text x="565" y="620" font-size="30" font-family="Arial">SECURITY</text>
        <text x="790" y="620" font-size="30" font-family="Arial">CHECKER</text>
        <path d="M100 700 C160 630 210 760 270 680" fill="none" stroke="#1557d5" stroke-width="10"/>
        <path d="M340 700 C390 640 450 760 500 680" fill="none" stroke="#1557d5" stroke-width="10"/>
        <path d="M580 700 C630 650 690 760 740 680" fill="none" stroke="#1557d5" stroke-width="10"/>
        <path d="M800 700 C850 645 910 755 970 680" fill="none" stroke="#1557d5" stroke-width="10"/>
        <ellipse cx="1080" cy="690" rx="70" ry="50" fill="none" stroke="#0a8a55" stroke-width="10"/>
        <text x="1020" y="700" font-size="22" font-family="Arial" fill="#0a8a55">SANTOSO</text>
      </svg>`;
    const image = await sharp(Buffer.from(svg)).jpeg({ quality: 88 }).toBuffer();
    const dataUrl = 'data:image/jpeg;base64,' + image.toString('base64');
    const result = await localAnalyze([dataUrl], 'SANTOSO');
    return c.json({
      status: 'ok',
      engine: result.engine,
      ocr_text: String(result.ocr_text || '').slice(0, 700),
      signatures: result.signatures,
      stamp: result.stamp,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('VISION_LOCAL_SELFTEST_ERROR', message);
    return c.json({ status: 'error', detail: message }, 502);
  }
});

app.post('/analyze', async (c) => {
  try {
    const body = await c.req.json();
    const images = Array.isArray(body?.images) ? body.images.slice(0, 3) : [];
    const expectedCustomer =
      typeof body?.expected_customer === 'string' ? body.expected_customer : null;

    if (images.length === 0) {
      return c.json({ detail: 'at least one image is required' }, 400);
    }

    const result = await localAnalyze(images.map(String), expectedCustomer);
    return c.json({ result });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('VISION_SERVICE_ERROR', message);
    return c.json({ detail: message }, 502);
  }
});

export default app;
