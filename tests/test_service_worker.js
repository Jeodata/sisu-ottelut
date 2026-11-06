// Run with: node tests/test_service_worker.js (no dependencies).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const scope = 'https://jeodata.github.io/sisu-ottelut/';
const listeners = {};
const stores = new Map([
  ['sisu-shell-v1', new Map()], ['another-pages-app', new Map([['keep', 'foreign']])]
]);
let offline = false;
let fetches = [];
let requestsInstalled = [];
const response = label => ({ ok: true, label, clone() { return response(label); } });
const cacheStorage = {
  keys: async () => [...stores.keys()],
  delete: async key => stores.delete(key),
  open: async key => {
    if (!stores.has(key)) stores.set(key, new Map());
    const store = stores.get(key);
    return {
      addAll: async requests => { requestsInstalled = requests; },
      match: async req => store.get(req.url),
      put: async (req, res) => store.set(req.url, res)
    };
  }
};
const context = {
  URL, Request, caches: cacheStorage,
  fetch: async (req, options) => {
    fetches.push({ url: req.url, options });
    if (offline) throw new Error('offline');
    return response('network');
  },
  self: { location: new URL(scope), registration: { scope },
    skipWaiting: async () => {}, clients: { claim: async () => {} },
    addEventListener: (name, handler) => { listeners[name] = handler; } }
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../service-worker.js'), 'utf8'), context);
const request = (route, mode = 'cors', method = 'GET') => ({ url: new URL(route, scope).href, mode, method });
async function dispatch(name, req) {
  let promise;
  listeners[name]({ request: req, waitUntil: p => { promise = p; }, respondWith: p => { promise = p; } });
  return promise === undefined ? undefined : await promise;
}

(async () => {
  await dispatch('install');
  assert.equal(requestsInstalled.length, 5);
  assert.ok(requestsInstalled.every(r => r.cache === 'no-store' && r.url.startsWith(scope)));
  await dispatch('activate');
  assert.ok(!stores.has('sisu-shell-v1'));
  assert.ok(stores.has('another-pages-app'));
  for (const route of ['./', './?t=123', './index.html', './games.json', './latest.json', './archive/2026-11-07.json']) {
    fetches = [];
    const result = await dispatch('fetch', request(route, route.startsWith('./?') || route === './' ? 'navigate' : 'cors'));
    assert.equal(result.label, 'network');
    assert.equal(fetches[0].options.cache, 'no-store');
  }
  const logo = request('./assets/logo.png');
  stores.get('sisu-shell-v2').set(logo.url, response('stale'));
  assert.equal((await dispatch('fetch', logo)).label, 'network');
  assert.equal(stores.get('sisu-shell-v2').get(logo.url).label, 'network');
  offline = true;
  assert.equal((await dispatch('fetch', logo)).label, 'network'); // refreshed offline fallback
  await assert.rejects(dispatch('fetch', request('./games.json')), /offline/);
  offline = false;
  assert.equal(await dispatch('fetch', request('./assets/team-logos/hash.png')), undefined);
  assert.equal(await dispatch('fetch', request('https://tulospalvelu.leijonat.fi/logo.png')), undefined);
  assert.equal(await dispatch('fetch', request('./games.json', 'cors', 'POST')), undefined);
  console.log('PWA routing, refresh, offline fallback and cache isolation: PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
