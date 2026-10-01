'use strict';

const { parentPort } = require('worker_threads');
const worker = require('tesseract.js/src/worker-script');
const gunzip = require('tesseract.js/src/worker-script/node/gunzip');
const cache = require('tesseract.js/src/worker-script/node/cache');

let Core = null;

async function getCore(_oem, _corePath, res) {
  if (!Core) {
    res.progress({ status: 'loading tesseract core', progress: 0 });
    // Use the embedded-WASM build. Unlike the default Node adapter this file
    // does not need a sibling .wasm asset in the Vercel function bundle.
    Core = require('tesseract.js-core/tesseract-core-lstm.wasm.js');
    res.progress({ status: 'loading tesseract core', progress: 1 });
  }
  return Core;
}

parentPort.on('message', (packet) => {
  worker.dispatchHandlers(packet, (obj) => parentPort.postMessage(obj));
});

worker.setAdapter({
  getCore,
  gunzip,
  fetch: global.fetch,
  ...cache,
});
