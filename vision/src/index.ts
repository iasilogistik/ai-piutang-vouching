import { Hono } from 'hono';
import { fileURLToPath } from 'node:url';
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
      workerPath: fileURLToPath(new URL('../worker.cjs', import.meta.url)),
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

function orientationTextScore(text: string, expectedBillingDocument?: string | null): number {
  const value = String(text || '');
  const upper = value.toUpperCase();
  const compact = upper.replace(/[^A-Z0-9]/g, '');
  const expected = String(expectedBillingDocument || '').replace(/[^A-Z0-9]/gi, '').toUpperCase();
  let score = Math.min(3, compact.length / 140);
  if (expected && compact.includes(expected)) score += 10;
  if (/SURAT\s+PERINTAH\s+JALAN/i.test(value)) score += 8;
  if (/SEMEN\s+INDONESIA\s+DISTRIBUTOR/i.test(value)) score += 4;
  if (/\b(BILLING|INVOICE|FAKTUR)\b/i.test(value)) score += 5;
  if (/\b(GRAND\s+TOTAL|TOTAL\s+TAGIHAN|NILAI\s+FAKTUR)\b/i.test(value)) score += 3;
  if (/\b(PENERIMA|DRIVER|CHECKER|SATPAM|BRANCH\s+MANAGER)\b/i.test(value)) score += 2;
  return score;
}

async function recognizePage(
  dataUrl: string,
  expectedBillingDocument?: string | null,
): Promise<PageOcr> {
  const input = dataUrlToBuffer(dataUrl);

  // First apply EXIF orientation. Then OCR the physical pixel orientation with
  // rotateAuto disabled so OCR bounding boxes and the image used for signature
  // / stamp crops always share the same coordinate system.
  const baseImage = await sharp(input).rotate().toBuffer();
  const worker = await getWorker();

  async function readVariant(image: Buffer, degrees: number) {
    const metadata = await sharp(image).metadata();
    const width = Number(metadata.width || 0);
    const height = Number(metadata.height || 0);
    if (!width || !height) throw new Error('Unable to determine image size');
    const result = await worker.recognize(image, { rotateAuto: false }, { text: true, blocks: true });
    const text = String(result.data.text || '').trim();
    const flat = flattenBlocks(result.data.blocks as any[] | null | undefined);
    return {
      page: {
        text,
        lines: flat.lines,
        words: flat.words,
        width,
        height,
        image,
      } satisfies PageOcr,
      score: orientationTextScore(text, expectedBillingDocument),
      degrees,
    };
  }

  let best = await readVariant(baseImage, 0);

  // Tesseract auto-orientation is unreliable for camera scans that are exactly
  // 90/180/270 degrees sideways. Only pay the extra OCR cost when the first
  // pass does not contain enough domain text. This keeps normal documents fast.
  if (best.score < 6) {
    for (const degrees of [90, 270, 180]) {
      const rotated = await sharp(baseImage).rotate(degrees).toBuffer();
      const candidate = await readVariant(rotated, degrees);
      if (candidate.score > best.score) best = candidate;
      if (best.score >= 12) break;
    }
  }

  if (best.degrees) {
    console.log('LOCAL_OCR_ROTATION_SELECTED', best.degrees);
  }
  return best.page;
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

function editDistance(a: string, b: string): number {
  const x = norm(a).replace(/ /g, '');
  const y = norm(b).replace(/ /g, '');
  if (!x) return y.length;
  if (!y) return x.length;
  const prev = Array.from({ length: y.length + 1 }, (_, i) => i);
  for (let i = 1; i <= x.length; i++) {
    const cur = [i];
    for (let j = 1; j <= y.length; j++) {
      cur[j] = Math.min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (x[i - 1] === y[j - 1] ? 0 : 1));
    }
    for (let j = 0; j <= y.length; j++) prev[j] = cur[j];
  }
  return prev[y.length];
}

function tokenSimilar(a: string, b: string): boolean {
  if (a === b) return true;
  const maxLen = Math.max(a.length, b.length);
  if (maxLen < 4) return false;
  return editDistance(a, b) <= (maxLen >= 8 ? 2 : 1);
}

function overlapScore(text: string, expected: string | null | undefined): number {
  const a = [...customerTokens(text)];
  const b = [...customerTokens(expected || '')];
  if (!a.length || !b.length) return 0;
  let hit = 0;
  const used = new Set<number>();
  for (const expectedToken of b) {
    const index = a.findIndex((value, i) => !used.has(i) && tokenSimilar(value, expectedToken));
    if (index >= 0) {
      used.add(index);
      hit += 1;
    }
  }
  return hit / Math.max(b.length, 1);
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
    // Most delivery/SPJ forms print the role label at the top of a box and
    // place the handwritten signature/stamp underneath it.
    y0: Math.max(0, Math.floor(label.bbox.y0 - page.height * 0.025)),
    y1: Math.min(page.height, Math.ceil(label.bbox.y1 + page.height * 0.16)),
  };
}

function intersects(a: BBox, b: BBox): boolean {
  return a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0;
}

async function residualInkStats(page: PageOcr, region: BBox, excludeOcrWords = true) {
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

  if (excludeOcrWords) {
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
  let colorMinX = info.width;
  let colorMaxX = -1;
  let colorMinY = info.height;
  let colorMaxY = -1;
  for (let y = 0; y < info.height; y++) {
    for (let x = 0; x < info.width; x++) {
      if (removeRows[y] || removeCols[x]) continue;
      const i = y * info.width + x;
      darkCount += dark[i];
      if (colored[i]) {
        colorCount += 1;
        colorMinX = Math.min(colorMinX, x);
        colorMaxX = Math.max(colorMaxX, x);
        colorMinY = Math.min(colorMinY, y);
        colorMaxY = Math.max(colorMaxY, y);
      }
    }
  }

  const colorWidthRatio =
    colorCount > 0 ? (colorMaxX - colorMinX + 1) / Math.max(info.width, 1) : 0;
  const colorHeightRatio =
    colorCount > 0 ? (colorMaxY - colorMinY + 1) / Math.max(info.height, 1) : 0;

  return {
    darkRatio: darkCount / Math.max(pixels, 1),
    colorRatio: colorCount / Math.max(pixels, 1),
    darkCount,
    colorCount,
    colorWidthRatio,
    colorHeightRatio,
  };
}

function signatureFromStats(stats: { darkRatio: number; colorRatio: number; darkCount: number; colorCount: number }) {
  // Presence-only detection. Authenticity/identity is intentionally not analysed.
  if (stats.colorCount >= 28 && stats.colorRatio >= 0.00045) {
    return { status: 'PRESENT', confidence: 0.92 };
  }
  if (stats.darkCount >= 135 && stats.darkRatio >= 0.0024) {
    return { status: 'PRESENT', confidence: 0.76 };
  }
  return { status: 'MISSING', confidence: 0.72 };
}

function signatureFromOfficialTemplateStats(
  stats: { darkRatio: number; colorRatio: number; darkCount: number; colorCount: number },
) {
  // The official SID SPJ boxes are tightly cropped to the handwriting band, so
  // a lower threshold is appropriate. This also avoids a false MISSING when
  // Tesseract interprets a real handwritten signature as OCR text.
  if (stats.colorCount >= 12 && stats.colorRatio >= 0.00018) {
    return { status: 'PRESENT', confidence: 0.9 };
  }
  if (stats.darkCount >= 60 && stats.darkRatio >= 0.0010) {
    return { status: 'PRESENT', confidence: 0.8 };
  }
  return { status: 'MISSING', confidence: 0.7 };
}

function lineInside(line: OcrLine, region: BBox): boolean {
  const cx = (line.bbox.x0 + line.bbox.x1) / 2;
  const cy = (line.bbox.y0 + line.bbox.y1) / 2;
  return cx >= region.x0 && cx <= region.x1 && cy >= region.y0 && cy <= region.y1;
}

async function recognizeBufferText(buffer: Buffer): Promise<string> {
  const worker = await getWorker();
  const result = await worker.recognize(buffer, { rotateAuto: false }, { text: true });
  return String(result.data.text || '').trim();
}

async function stampRegionVariants(page: PageOcr, region: BBox): Promise<string[]> {
  const left = Math.max(0, Math.floor(region.x0));
  const top = Math.max(0, Math.floor(region.y0));
  const width = Math.max(1, Math.min(page.width - left, Math.floor(region.x1 - region.x0)));
  const height = Math.max(1, Math.min(page.height - top, Math.floor(region.y1 - region.y0)));
  try {
    const crop = sharp(page.image).extract({ left, top, width, height });
    const targetWidth = Math.min(1800, Math.max(800, width * 2));
    const grayscale = await crop.clone().resize({ width: targetWidth, withoutEnlargement: false }).grayscale().normalise().sharpen().threshold(212).png().toBuffer();

    const rawResult = await crop.clone().resize({ width: targetWidth, withoutEnlargement: false }).removeAlpha().raw().toBuffer({ resolveWithObject: true });
    const data = rawResult.data;
    const info = rawResult.info;
    const mask = Buffer.alloc(info.width * info.height);
    for (let i = 0; i < info.width * info.height; i++) {
      const offset = i * info.channels;
      const r = data[offset] ?? 255;
      const g = data[offset + 1] ?? r;
      const b = data[offset + 2] ?? r;
      const max = Math.max(r, g, b);
      const min = Math.min(r, g, b);
      const brightness = (r + g + b) / 3;
      const chroma = max - min;
      mask[i] = chroma >= 25 && brightness < 245 ? 0 : 255;
    }
    const colored = await sharp(mask, { raw: { width: info.width, height: info.height, channels: 1 } }).png().toBuffer();

    const outputs: string[] = [];
    const grayText = await recognizeBufferText(grayscale);
    if (grayText) outputs.push(grayText);
    const colorText = await recognizeBufferText(colored);
    if (colorText) outputs.push(colorText);
    return outputs;
  } catch (error) {
    console.warn('STAMP_REGION_OCR_FAILED', error instanceof Error ? error.message : String(error));
    return [];
  }
}

function bestCustomerLine(text: string, expectedCustomer?: string | null): string | null {
  const lines = String(text || '').split(/\r?\n/).map((value) => value.trim()).filter((value) => value.length >= 3);
  return lines.filter((value) => overlapScore(value, expectedCustomer) >= 0.22).sort((a, b) => overlapScore(b, expectedCustomer) - overlapScore(a, expectedCustomer))[0] || null;
}

function officialSpjScore(page: PageOcr): number {
  const text = norm(page.text);
  let score = 0;
  if (text.includes('SURAT PERINTAH JALAN')) score += 7;
  if (text.includes('SEMEN INDONESIA DISTRIBUTOR')) score += 5;
  if (/SPJ\s*\/\s*[A-Z0-9]+\s*\/\s*\d{6}\s*\/\s*\d{8,12}/i.test(page.text)) score += 5;
  const roles = new Set(findRoleLabels(page).map((item) => item.role));
  if (roles.size >= 4) score += 2;
  return score;
}

function extractOfficialSpjNumber(text: string): string | null {
  const patterns = [
    /SPJ\s*\/\s*([A-Z0-9]+)\s*\/\s*(\d{6})\s*\/\s*(\d{8,12})/i,
    /SPJ[\s:/-]+([A-Z0-9]+)[\s/-]+(\d{6})[\s/-]+(\d{8,12})/i,
  ];
  for (const pattern of patterns) {
    const match = pattern.exec(text);
    if (match) return 'SPJ/' + match[1].toUpperCase() + '/' + match[2] + '/' + match[3];
  }
  return null;
}

function officialTemplateRegion(page: PageOcr, role: string): BBox | null {
  // Standard PT Semen Indonesia Distributor SPJ layout:
  // Penerima | Driver | Checker | Satpam | Branch Manager.
  // Only crop the handwriting band above the printed name/baseline. This is
  // more reliable for long slanted BM signatures like the SANTOSO sample.
  const x: Record<string, [number, number]> = {
    receiver: [0.025, 0.245],
    driver: [0.235, 0.415],
    checker: [0.395, 0.595],
    security: [0.575, 0.775],
    bm: [0.72, 0.995],
  };
  const span = x[role];
  if (!span) return null;
  return {
    x0: Math.floor(page.width * span[0]),
    x1: Math.ceil(page.width * span[1]),
    y0: Math.floor(page.height * 0.575),
    y1: Math.ceil(page.height * 0.69),
  };
}

function parseMoneyToken(value: string): number | null {
  let raw = String(value || '').replace(/\s+/g, '').replace(/:/g, '.').replace(/[^0-9,.-]/g, '');
  if (!raw) return null;
  if (raw.includes(',') && raw.includes('.')) {
    raw = raw.lastIndexOf(',') > raw.lastIndexOf('.')
      ? raw.replace(/\./g, '').replace(',', '.')
      : raw.replace(/,/g, '');
  } else if ((raw.match(/\./g) || []).length >= 1 && raw.split('.').slice(1).every((p) => p.length === 3)) {
    raw = raw.replace(/\./g, '');
  } else if ((raw.match(/,/g) || []).length >= 1 && raw.split(',').slice(1).every((p) => p.length === 3)) {
    raw = raw.replace(/,/g, '');
  } else {
    raw = raw.replace(',', '.');
  }
  const amount = Number(raw);
  return Number.isFinite(amount) && amount > 0 ? amount : null;
}

function findLabeledAmount(
  text: string,
  patterns: RegExp[],
): { amount: number; reference: string } | null {
  for (const pattern of patterns) {
    const match = pattern.exec(text);
    if (!match) continue;
    const amount = parseMoneyToken(match[1]);
    if (amount !== null) return { amount, reference: match[0].trim().slice(0, 140) };
  }
  return null;
}

function parseInvoiceDateValue(rawValue: string): string | null {
  const raw = String(rawValue || '').trim().replace(/,/g, ' ').replace(/\s+/g, ' ');
  if (!raw) return null;

  const numeric = /^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$/.exec(raw);
  if (numeric) {
    const day = Number(numeric[1]);
    const month = Number(numeric[2]);
    let year = Number(numeric[3]);
    if (year < 100) year += 2000;
    const date = new Date(Date.UTC(year, month - 1, day));
    if (
      date.getUTCFullYear() === year &&
      date.getUTCMonth() === month - 1 &&
      date.getUTCDate() === day
    ) {
      return year.toString().padStart(4, '0') + '-' +
        month.toString().padStart(2, '0') + '-' +
        day.toString().padStart(2, '0');
    }
  }

  const months: Record<string, number> = {
    JAN: 1, JANUARY: 1, JANUARI: 1,
    FEB: 2, FEBRUARY: 2, FEBRUARI: 2,
    MAR: 3, MARCH: 3, MARET: 3,
    APR: 4, APRIL: 4,
    MAY: 5, MEI: 5,
    JUN: 6, JUNE: 6, JUNI: 6,
    JUL: 7, JULY: 7, JULI: 7,
    AUG: 8, AUGUST: 8, AGUSTUS: 8,
    SEP: 9, SEPT: 9, SEPTEMBER: 9,
    OCT: 10, OCTOBER: 10, OKTOBER: 10,
    NOV: 11, NOVEMBER: 11,
    DEC: 12, DECEMBER: 12, DESEMBER: 12,
  };

  let match = /^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$/i.exec(raw);
  if (match) {
    const day = Number(match[1]);
    const month = months[match[2].toUpperCase()];
    const year = Number(match[3]);
    if (month) {
      return year.toString().padStart(4, '0') + '-' +
        month.toString().padStart(2, '0') + '-' +
        day.toString().padStart(2, '0');
    }
  }

  match = /^([A-Za-z]+)\s+(\d{1,2})\s+(\d{4})$/i.exec(raw);
  if (match) {
    const month = months[match[1].toUpperCase()];
    const day = Number(match[2]);
    const year = Number(match[3]);
    if (month) {
      return year.toString().padStart(4, '0') + '-' +
        month.toString().padStart(2, '0') + '-' +
        day.toString().padStart(2, '0');
    }
  }
  return null;
}

function invoiceDateCandidates(text: string): string[] {
  const values = new Set<string>();
  const forbiddenPattern = /\b(DUE\s+DATE|PAYMENT\s+DUE|NET\s+DUE|JATUH\s+TEMPO|TANGGAL\s+JATUH\s+TEMPO|TGL\.?\s+JATUH\s+TEMPO|BATAS\s+PEMBAYARAN|DELIVERY\s+DATE|TANGGAL\s+PENGIRIMAN|POSTING\s+DATE|PRINT\s+DATE|TANGGAL\s+CETAK|TGL\.?\s+CETAK|ORDER\s+DATE|PO\s+DATE)\b/i;
  const lines = String(text || '').split(/\r?\n/);

  for (const line of lines) {
    // Only dates printed on the Billing page and not explicitly labelled as
    // due/delivery/posting/print/order dates are eligible as a fallback.
    if (forbiddenPattern.test(line)) continue;

    const numeric = line.match(/\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b/g) || [];
    const dmyText = line.match(/\b\d{1,2}\s+[A-Za-z]{3,12}\s+\d{4}\b/g) || [];
    const mdyText = line.match(/\b[A-Za-z]{3,12}\s+\d{1,2},?\s+\d{4}\b/g) || [];
    for (const raw of [...numeric, ...dmyText, ...mdyText]) {
      const normalized = parseInvoiceDateValue(raw);
      if (normalized) values.add(normalized);
    }
  }
  return [...values];
}

function daysBetweenIso(left: string, right: string): number {
  const a = Date.parse(left + 'T00:00:00Z');
  const b = Date.parse(right + 'T00:00:00Z');
  if (!Number.isFinite(a) || !Number.isFinite(b)) return Number.MAX_SAFE_INTEGER;
  return Math.abs(a - b) / 86400000;
}

function parseInvoiceDate(text: string, expectedDocDate?: string | null): string | null {
  const lines = String(text || '').split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const datePattern = /(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,12}\s+\d{4}|[A-Za-z]{3,12}\s+\d{1,2},?\s+\d{4})/i;

  // Physical Doc. Date must be the printed Faktur/Invoice/Billing issue date,
  // never due date / jatuh tempo. Include common OCR confusions such as
  // TANGGAI, TG1 and FAKT0R so a slightly rotated/faint label is still usable.
  const invoiceLabels = [
    /\bTANGGA[L1I]\s+F[A4]KT[UO0]R(?:\s+PAJAK)?\b/i,
    /\bTG[L1I]\.?\s+F[A4]KT[UO0]R(?:\s+PAJAK)?\b/i,
    /\bFAKT[UO0]R\s+DATE\b/i,
    /\bINVOICE\s+DATE\b/i,
    /\bDATE\s+OF\s+INVOICE\b/i,
    /\bTANGGA[L1I]\s+INVOICE\b/i,
    /\bTG[L1I]\.?\s+INVOICE\b/i,
    /\bBILLING\s+DATE\b/i,
    /\bBILL\s+DATE\b/i,
    /\bDOCUMENT\s+DATE\b/i,
    /\bTANGGA[L1I]\s+DOKUMEN\b/i,
  ];
  const forbiddenLabels = /\b(DUE\s+DATE|PAYMENT\s+DUE|NET\s+DUE|JATUH\s+TEMPO|TANGGA[L1I]\s+JATUH\s+TEMPO|TG[L1I]\.?\s+JATUH\s+TEMPO|BATAS\s+PEMBAYARAN|DELIVERY\s+DATE|TANGGA[L1I]\s+PENGIRIMAN|POSTING\s+DATE|PRINT\s+DATE|TANGGA[L1I]\s+CETAK|TG[L1I]\.?\s+CETAK|ORDER\s+DATE|PO\s+DATE)\b/i;

  const labeled: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!invoiceLabels.some((pattern) => pattern.test(line))) continue;
    if (forbiddenLabels.test(line)) continue;

    // Prefer a date on the same line. A one/two-line fallback is allowed for
    // table layouts where the label and value are vertically stacked.
    for (let offset = 0; offset <= 2 && i + offset < lines.length; offset++) {
      const candidateLine = lines[i + offset];
      if (forbiddenLabels.test(candidateLine)) continue;
      const match = datePattern.exec(candidateLine);
      if (!match) continue;
      const normalized = parseInvoiceDateValue(match[1]);
      if (normalized && !labeled.includes(normalized)) labeled.push(normalized);
      if (offset === 0 && normalized) break;
    }
  }
  if (!labeled.length) return null;

  const expected = expectedDocDate ? parseInvoiceDateValue(expectedDocDate) : null;
  if (expected) {
    const printedCandidates = invoiceDateCandidates(text);
    const expectedPrinted = printedCandidates.includes(expected);
    if (expectedPrinted && labeled.includes(expected)) return expected;

    if (expectedPrinted && labeled.length === 1) {
      const delta = daysBetweenIso(labeled[0], expected);
      // 30/45/60/90-day terms are a typical symptom of the due date being
      // associated with a damaged Invoice Date label. Use SAP only when the SAP
      // date itself is also visibly printed on this Billing page.
      if ([30, 45, 60, 90].includes(delta)) return expected;
    }

    if (expectedPrinted && labeled.length > 1) {
      return labeled.slice().sort((a, b) => daysBetweenIso(a, expected) - daysBetweenIso(b, expected))[0];
    }
  }

  return labeled[0];
}

function billingPageScore(page: PageOcr, expectedBillingDocument?: string | null): number {
  const text = norm(page.text);
  const compact = text.replace(/ /g, '');
  const expected = norm(expectedBillingDocument || '').replace(/ /g, '');
  let score = 0;
  if (expected && compact.includes(expected)) score += 8;
  if (/\b(BILLING|INVOICE|FAKTUR)\b/i.test(page.text)) score += 5;
  if (/\b(GRAND\s+TOTAL|TOTAL\s+TAGIHAN|AMOUNT\s+DUE|PPN|DPP)\b/i.test(page.text)) score += 2;
  if (/SURAT\s+PERINTAH\s+JALAN/i.test(page.text)) score -= 6;
  if (/DELIVERY\s+ORDER/i.test(page.text)) score -= 4;
  return score;
}

function selectBillingPageIndex(pages: PageOcr[], expectedBillingDocument?: string | null): number {
  let bestIndex = -1;
  let bestScore = 0;
  pages.forEach((page, index) => {
    const score = billingPageScore(page, expectedBillingDocument);
    if (score > bestScore) {
      bestScore = score;
      bestIndex = index;
    }
  });
  return bestScore >= 5 ? bestIndex : -1;
}

function parsePaymentMoneyToken(value: string): number | null {
  // Payment lines are often printed as negative credits. For a partial-payment
  // amount we need the absolute paid value, while gross/outstanding parsers stay
  // positive-only.
  const cleaned = String(value || '').trim().replace(/^\(/, '').replace(/^[-–—]+/, '');
  return parseMoneyToken(cleaned);
}

function parsePartialPayments(
  text: string,
  allowPrintedDerivation = true,
) {
  const rows: Array<{ amount: number; date: string | null; reference: string | null }> = [];

  const explicitPatterns = [
    /(?:PARTIAL\s+PAYMENT|PARTIAL\s+PAID|PAYMENT\s+PARTIAL|PARTIAL\s+BILLING)[ \t]*[:#=-]?[ \t]*(?:RP\.?[ \t]*)?([-–—(]?[0-9][0-9.,: \t-]*)/gi,
    /(?:PAYMENT\s+RECEIVED|PAYMENT\s+PAID|PAYMENT\s+AMOUNT|AMOUNT\s+PAID|PAID\s+AMOUNT)[ \t]*[:#=-]?[ \t]*(?:RP\.?[ \t]*)?([-–—(]?[0-9][0-9.,: \t-]*)/gi,
    /(?:JUMLAH\s+DIBAYAR|NILAI\s+PEMBAYARAN|TOTAL\s+PEMBAYARAN|JUMLAH\s+PEMBAYARAN|PEMBAYARAN\s+(?:PARTIAL|PARSIAL|SEBAGIAN|DITERIMA|SEBELUMNYA|TERDAHULU)|PELUNASAN\s+SEBAGIAN|TELAH\s+DIBAYAR|SUDAH\s+DIBAYAR)[ \t]*[:#=-]?[ \t]*(?:RP\.?[ \t]*)?([-–—(]?[0-9][0-9.,: \t-]*)/gi,
    /(?:DOWN\s+PAYMENT|\bDP\b|UANG\s+MUKA)[ \t]*[:#=-]?[ \t]*(?:RP\.?[ \t]*)?([-–—(]?[0-9][0-9.,: \t-]*)/gi,
  ];

  for (const pattern of explicitPatterns) {
    pattern.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(text)) !== null) {
      const amount = parsePaymentMoneyToken(match[1]);
      if (amount === null) continue;
      const reference = match[0].trim().slice(0, 160);
      if (!rows.some((row) => Math.abs(row.amount - amount) < 0.01 && row.reference === reference)) {
        rows.push({ amount, date: null, reference });
      }
    }
  }

  const gross = findLabeledAmount(text, [
    /(?:GRAND[ \t]+TOTAL|TOTAL[ \t]+TAGIHAN|TOTAL[ \t]+INVOICE|JUMLAH[ \t]+TAGIHAN|INVOICE[ \t]+TOTAL|TOTAL[ \t]+BILLING|NILAI[ \t]+FAKTUR|TOTAL[ \t]+FAKTUR)[ \t]*[:#=-]?[ \t]*(?:RP\.?[ \t]*)?([0-9][0-9.,: \t-]*)/i,
  ]);
  const subtotal = findLabeledAmount(text, [
    /(?:SUB[ \t]*TOTAL|DPP)[ \t]*[:#=-]?[ \t]*(?:RP\.?[ \t]*)?([0-9][0-9.,: \t-]*)/i,
  ]);
  const tax = findLabeledAmount(text, [
    /(?:PPN|VAT)[ \t]*[:#=-]?[ \t]*(?:RP\.?[ \t]*)?([0-9][0-9.,: \t-]*)/i,
  ]);
  const outstanding = findLabeledAmount(text, [
    /(?:OUTSTANDING(?:[ \t]+PIUTANG)?|TOTAL[ \t]+OUTSTANDING|BALANCE[ \t]+DUE|AMOUNT[ \t]+DUE|SISA[ \t]+TAGIHAN|SISA[ \t]+TAGIH|SISA[ \t]+PEMBAYARAN|SISA[ \t]+PIUTANG|SISA[ \t]+BILLING|SALDO[ \t]+TERUTANG|SALDO[ \t]+PIUTANG|NET[ \t]+DUE|NET[ \t]+OUTSTANDING)[ \t]*[:#=-]?[ \t]*(?:RP\.?[ \t]*)?([0-9][0-9.,: \t-]*)/i,
  ]);

  let grossTotal = gross?.amount ?? null;

  // Real SID billings often print Sub Total + PPN + Grand Total. When OCR drops
  // a zero in Grand Total (e.g. 8.815.890 -> 881.589), the printed arithmetic is
  // stronger evidence than the damaged total token. Use it only when the direct
  // total is absent or clearly below its own subtotal.
  if (subtotal && tax) {
    const componentTotal = Math.round((subtotal.amount + tax.amount) * 100) / 100;
    if (grossTotal === null || grossTotal < subtotal.amount || grossTotal < componentTotal * 0.5) {
      grossTotal = componentTotal;
    }
  }

  // Derive partial payment only from values printed on the physical evidence.
  // SAP outstanding is never used to manufacture a payment.
  if (
    allowPrintedDerivation &&
    rows.length === 0 &&
    grossTotal !== null &&
    outstanding &&
    grossTotal > outstanding.amount
  ) {
    const derived = Math.round((grossTotal - outstanding.amount) * 100) / 100;
    if (derived > 0) {
      rows.push({
        amount: derived,
        date: null,
        reference:
          'DERIVED_DOCUMENT_TOTAL_MINUS_PRINTED_OUTSTANDING | GROSS ' +
          grossTotal +
          ' | ' +
          outstanding.reference,
      });
    }
  }

  return { rows, grossTotal };
}

async function localAnalyze(
  images: string[],
  expectedCustomer?: string | null,
  expectedBillingDocument?: string | null,
  expectedNominal?: number | null,
  expectedDocDate?: string | null,
) {
  const pages: PageOcr[] = [];
  for (const image of images.slice(0, 3)) {
    pages.push(await recognizePage(String(image), expectedBillingDocument));
  }

  // When a package contains Delivery Order + Billing + SPJ, only the official
  // PT SID page headed "SURAT PERINTAH JALAN" is authoritative for SPJ number,
  // signatures and receiver stamp.
  let officialPageIndex = -1;
  let officialScore = 0;
  pages.forEach((page, index) => {
    const score = officialSpjScore(page);
    if (score > officialScore) {
      officialScore = score;
      officialPageIndex = index;
    }
  });
  if (officialScore < 7) officialPageIndex = -1;

  const signaturePageIndexes = officialPageIndex >= 0
    ? [officialPageIndex]
    : pages.map((_, index) => index);

  const signatures: Record<string, { status: string; confidence: number; page_number: number | null }> = {};
  const roleBest: Record<string, { status: string; confidence: number; page_number: number | null }> = {};
  let stamp = { status: 'UNCLEAR', text: null as string | null, confidence: 0.2, page_number: null as number | null };
  let bestStampRegion: { page: PageOcr; region: BBox; pageNumber: number; score: number } | null = null;

  for (const pageIndex of signaturePageIndexes) {
    const page = pages[pageIndex];
    const labels = findRoleLabels(page);
    const labelByRole = new Map(labels.map((item) => [item.role, item]));

    for (const role of ['receiver', 'driver', 'checker', 'security', 'bm']) {
      const label = labelByRole.get(role);
      const regions: Array<{ region: BBox; official: boolean }> = [];
      if (label) regions.push({ region: roleRegion(page, label, labels), official: false });
      if (pageIndex === officialPageIndex) {
        const template = officialTemplateRegion(page, role);
        if (template) regions.push({ region: template, official: true });
      }
      if (!regions.length) continue;

      let best: { status: string; confidence: number; page_number: number | null; stats: any; region: BBox } | null = null;
      for (const item of regions) {
        const stats = await residualInkStats(page, item.region, !item.official);
        const detected = item.official
          ? signatureFromOfficialTemplateStats(stats)
          : signatureFromStats(stats);
        const candidate = { ...detected, page_number: pageIndex + 1, stats, region: item.region };
        if (!best || candidate.confidence > best.confidence || (candidate.status === 'PRESENT' && best.status !== 'PRESENT')) {
          best = candidate;
        }
      }
      if (!best) continue;
      const previous = roleBest[role];
      if (!previous || best.status === 'PRESENT' || best.confidence > previous.confidence) {
        roleBest[role] = { status: best.status, confidence: best.confidence, page_number: best.page_number };
      }

      if (role === 'receiver') {
        const regionLines = page.lines.filter((line) => lineInside(line, best!.region));
        const stampTextCandidate = regionLines
          .map((line) => line.text.trim())
          .filter((value) => overlapScore(value, expectedCustomer) >= 0.22)
          .sort((a, b) => overlapScore(b, expectedCustomer) - overlapScore(a, expectedCustomer))[0] || null;

        const stats = best.stats;

        // Stamp presence must be independent from signature presence. Earlier
        // versions treated any dark ink in the receiver box as a stamp, so a
        // handwritten receiver signature could make every document look
        // STAMP=PRESENT. V12 only accepts a visually stamp-like coloured shape
        // here; black/grey ink without readable stamp text remains UNCLEAR and
        // goes to reviewer rather than becoming a false PASS.
        const stampPresentByColorShape =
          stats.colorCount >= 65 &&
          stats.colorRatio >= 0.0008 &&
          stats.colorWidthRatio >= 0.28 &&
          stats.colorHeightRatio >= 0.28;
        const stampTextBackedInk =
          Boolean(stampTextCandidate) &&
          stats.darkCount >= 320 &&
          stats.darkRatio >= 0.0045;
        const visualStamp = stampPresentByColorShape || stampTextBackedInk;
        const score =
          stats.colorRatio * 8 +
          stats.colorWidthRatio +
          stats.colorHeightRatio +
          (stampTextCandidate ? 1 : 0);

        if (visualStamp && (!bestStampRegion || score > bestStampRegion.score)) {
          bestStampRegion = { page, region: best.region, pageNumber: pageIndex + 1, score };
        }
        if (visualStamp && stampTextCandidate) {
          stamp = { status: 'PRESENT', text: stampTextCandidate, confidence: 0.94, page_number: pageIndex + 1 };
        } else if (stampPresentByColorShape && stamp.status !== 'PRESENT') {
          stamp = { status: 'PRESENT', text: null, confidence: 0.88, page_number: pageIndex + 1 };
        }
      }
    }
  }

  if (stamp.status === 'PRESENT' && !stamp.text && bestStampRegion) {
    const variants = await stampRegionVariants(bestStampRegion.page, bestStampRegion.region);
    const candidates = variants
      .map((value) => bestCustomerLine(value, expectedCustomer))
      .filter((value): value is string => Boolean(value))
      .sort((a, b) => overlapScore(b, expectedCustomer) - overlapScore(a, expectedCustomer));
    if (candidates[0]) {
      stamp = { status: 'PRESENT', text: candidates[0], confidence: 0.95, page_number: bestStampRegion.pageNumber };
    }
  }

  for (const role of ['receiver', 'driver', 'security', 'bm', 'checker']) {
    if (roleBest[role]) {
      signatures[role] = roleBest[role];
    } else if (officialPageIndex >= 0) {
      // Standard official SPJ contains all five signature roles. If a role box
      // cannot be read at all, do not borrow evidence from another page.
      signatures[role] = { status: 'MISSING', confidence: 0.6, page_number: officialPageIndex + 1 };
    } else {
      signatures[role] = { status: 'NOT_APPLICABLE', confidence: 0.9, page_number: null };
    }
  }

  const officialSpjNumber = officialPageIndex >= 0
    ? extractOfficialSpjNumber(pages[officialPageIndex].text)
    : null;
  const ocrText = pages.map((page, index) => '--- PAGE ' + (index + 1) + ' ---\n' + page.text).join('\n\n');
  const expectedBillingNorm = norm(expectedBillingDocument || '').replace(/ /g, '');
  const billingPageIndex = selectBillingPageIndex(pages, expectedBillingDocument);
  const normalizedOcr = norm(ocrText).replace(/ /g, '');
  const billingDocument = expectedBillingNorm && normalizedOcr.includes(expectedBillingNorm)
    ? (expectedBillingDocument || null)
    : null;

  // Read Doc. Date only from the Billing/Invoice/Faktur page. When OCR loses
  // the label but keeps the printed date, expected SAP date only disambiguates
  // among dates that are actually visible on that Billing page.
  const billingText = billingPageIndex >= 0 ? pages[billingPageIndex].text : '';
  const invoiceDate = billingText ? parseInvoiceDate(billingText, expectedDocDate) : null;
  let paymentResult = parsePartialPayments(billingText, true);
  if (paymentResult.rows.length === 0 && billingPageIndex >= 0) {
    const crossPagePayments = parsePartialPayments(ocrText, false);
    paymentResult = {
      rows: crossPagePayments.rows,
      grossTotal: paymentResult.grossTotal,
    };
  }

  // Partial payment must be supported by the physical evidence itself.
  // Never manufacture a payment as Gross Billing - SAP outstanding: that can
  // make reconciliation appear correct even when the document has no payment
  // history. Only explicit payment labels or Total - printed Outstanding on the
  // same Billing evidence are accepted by parsePartialPayments().

  return {
    engine: 'LOCAL_TESSERACT_VISUAL_V16',
    billing_document: billingDocument,
    invoice_date: invoiceDate,
    grand_total: paymentResult.grossTotal,
    spj_number: officialSpjNumber,
    delivery_order_number: null,
    receiver_name: null,
    partial_payments: paymentResult.rows,
    signatures,
    stamp,
    official_spj_page: officialPageIndex >= 0 ? officialPageIndex + 1 : null,
    notes: [
      officialPageIndex >= 0
        ? 'SPJ resmi dipilih dari halaman PT Semen Indonesia Distributor berjudul SURAT PERINTAH JALAN.'
        : 'Header SPJ resmi tidak terbaca; sistem memakai fallback dokumen.',
      'TTD hanya dinilai dari ada/tidaknya coretan visual; keaslian dan identitas tidak dianalisis.',
      'Tanggal fisik Billing hanya diambil dari tanggal Faktur/Invoice/Billing/Document yang tercetak pada halaman Billing; Due/Jatuh Tempo/Delivery tidak pernah dipakai.',
      'Nominal fisik memakai Gross/Grand Total yang tercetak, dengan recovery Sub Total + PPN bila token Grand Total kehilangan digit.',
      'Partial payment hanya dibaca dari bukti fisik: label pembayaran atau Total dikurangi Outstanding/Sisa yang sama-sama tercetak pada Billing. Selisih terhadap SAP tidak pernah dianggap sebagai partial payment.'
    ],
    ocr_text: ocrText,
  };
}

app.get('/health', (c) =>
  c.json({
    status: 'ok',
    service: 'vision',
    engine: 'LOCAL_TESSERACT_VISUAL_V16',
  }),
);

app.get('/vision-ai-health', async (c) => {
  // Preview-only diagnostic route used while this branch is under test.
  return c.json({
    status: 'ok',
    engine: 'LOCAL_TESSERACT_VISUAL_V16',
    paid_gateway_required: false,
  });
});

app.get('/vision-local-selftest', async (c) => {
  try {
    // Billing page is deliberately rotated 90 degrees and its Grand Total is
    // deliberately missing one zero. The self-test therefore covers the two
    // production failures reported in the working paper: rotated scans and
    // gross-total magnitude loss.
    const billingSvg = `
      <svg width="1200" height="900" xmlns="http://www.w3.org/2000/svg">
        <rect width="1200" height="900" fill="white"/>
        <text x="70" y="90" font-size="38" font-family="Arial">BILLING DOCUMENT 8501681202</text>
        <text x="70" y="155" font-size="34" font-family="Arial">TANGGAL FAKTUR 03 Juli 2026</text>
        <text x="70" y="215" font-size="30" font-family="Arial">POSTING DATE 10/09/2026</text>
        <text x="70" y="330" font-size="34" font-family="Arial">SUB TOTAL 7.942.224</text>
        <text x="70" y="390" font-size="34" font-family="Arial">PPN 873.666</text>
        <text x="70" y="450" font-size="34" font-family="Arial">GRAND TOTAL 881.589</text>
        <text x="70" y="520" font-size="34" font-family="Arial">PEMBAYARAN SEBAGIAN 3.400.008</text>
      </svg>`;
    const billingUpright = await sharp(Buffer.from(billingSvg)).jpeg({ quality: 92 }).toBuffer();
    const billingRotated = await sharp(billingUpright).rotate(90).jpeg({ quality: 92 }).toBuffer();

    const spjSvg = `
      <svg width="1200" height="900" xmlns="http://www.w3.org/2000/svg">
        <rect width="1200" height="900" fill="white"/>
        <text x="70" y="70" font-size="30" font-family="Arial">PT SEMEN INDONESIA DISTRIBUTOR</text>
        <text x="620" y="70" font-size="36" font-family="Arial">SURAT PERINTAH JALAN</text>
        <text x="620" y="115" font-size="28" font-family="Arial">SPJ/S41C/202607/2501731412</text>
        <text x="85" y="545" font-size="28" font-family="Arial">Penerima</text>
        <text x="325" y="545" font-size="28" font-family="Arial">Driver</text>
        <text x="510" y="545" font-size="28" font-family="Arial">Checker</text>
        <text x="710" y="545" font-size="28" font-family="Arial">Satpam</text>
        <text x="900" y="545" font-size="28" font-family="Arial">Branch Manager</text>
        <path d="M90 595 C145 540 190 650 245 575" fill="none" stroke="#1557d5" stroke-width="10"/>
        <path d="M330 595 C380 545 425 650 485 575" fill="none" stroke="#1557d5" stroke-width="10"/>
        <path d="M520 595 C570 545 620 650 680 575" fill="none" stroke="#1557d5" stroke-width="10"/>
        <path d="M715 595 C765 545 815 650 870 575" fill="none" stroke="#1557d5" stroke-width="10"/>
        <path d="M915 595 C965 545 1030 650 1090 575" fill="none" stroke="#1557d5" stroke-width="10"/>
        <ellipse cx="170" cy="620" rx="72" ry="45" fill="none" stroke="#0a8a55" stroke-width="9"/>
        <text x="112" y="628" font-size="20" font-family="Arial" fill="#0a8a55">BERKAH</text>
      </svg>`;
    const spjImage = await sharp(Buffer.from(spjSvg)).jpeg({ quality: 92 }).toBuffer();

    const result = await localAnalyze(
      [
        'data:image/jpeg;base64,' + billingRotated.toString('base64'),
        'data:image/jpeg;base64,' + spjImage.toString('base64'),
      ],
      'BERKAH AL AQSO, TB',
      '8501681202',
      5415882,
      '2026-09-10',
    );

    const partial = result.partial_payments.reduce(
      (sum: number, row: { amount: number }) => sum + Number(row.amount || 0),
      0,
    );
    const netPhysical =
      result.grand_total == null ? null : Number(result.grand_total) - partial;

    return c.json({
      status:
        result.invoice_date === '2026-07-03' &&
        Number(result.grand_total) === 8815890 &&
        partial === 3400008 &&
        netPhysical === 5415882
          ? 'ok'
          : 'failed',
      engine: result.engine,
      invoice_date: result.invoice_date,
      grand_total: result.grand_total,
      partial_payment: partial,
      net_physical: netPhysical,
      spj_number: result.spj_number,
      signatures: result.signatures,
      stamp: result.stamp,
      ocr_text: String(result.ocr_text || '').slice(0, 1200),
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

    const expectedBillingDocument = typeof body?.expected_billing_document === 'string' ? body.expected_billing_document : null;
    const expectedNominalRaw = body?.expected_nominal;
    const expectedNominal =
      expectedNominalRaw == null || expectedNominalRaw === ''
        ? null
        : Number(String(expectedNominalRaw).replace(/[^0-9.-]/g, ''));
    const expectedDocDate =
      typeof body?.expected_doc_date === 'string' ? body.expected_doc_date : null;
    const result = await localAnalyze(
      images.map(String),
      expectedCustomer,
      expectedBillingDocument,
      Number.isFinite(expectedNominal) ? expectedNominal : null,
      expectedDocDate,
    );
    return c.json({ result });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('VISION_SERVICE_ERROR', message);
    return c.json({ detail: message }, 502);
  }
});

export default app;
