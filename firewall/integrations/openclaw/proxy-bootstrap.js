// Node bootstrap: route the global fetch() through the firewall proxy.
//
// OpenClaw 2026.6.x uses Node's native fetch (undici). undici's HTTP
// client does NOT honour HTTP_PROXY / HTTPS_PROXY. To intercept those
// requests we install our own dispatcher on the undici module the
// runtime is using.
//
// Usage:
//   npm install -g undici            # one-time, so this script can resolve it
//   export FIREWALL_PROXY=http://127.0.0.1:8080
//   NODE_OPTIONS="--require $(firewall integrations openclaw-bootstrap)" \
//     openclaw skills search hello
//
// Caveats: see README "OpenClaw" section. Some apps bundle their own
// undici copy and ignore the global dispatcher; for those, use Docker
// mode (`firewall start --mode docker`).

'use strict';

// Idempotent — this preload can fire more than once per process tree
// (child workers, npm shims, etc.). Once we have a dispatcher installed
// in this process, do nothing further.
if (!globalThis.__firewallBootstrapInstalled) {
  const proxyUrl =
    process.env.FIREWALL_PROXY ||
    process.env.HTTPS_PROXY    ||
    process.env.HTTP_PROXY     ||
    'http://127.0.0.1:8080';

  let undici;
  try { undici = require('undici'); }
  catch (_) {
    try { undici = require('node:undici'); }
    catch (_) { /* leave undefined */ }
  }

  if (undici && typeof undici.setGlobalDispatcher === 'function' && undici.ProxyAgent) {
    undici.setGlobalDispatcher(new undici.ProxyAgent(proxyUrl));
    globalThis.__firewallBootstrapInstalled = true;
    if (process.env.FIREWALL_DEBUG) {
      process.stderr.write('[firewall] undici routed through ' + proxyUrl + '\n');
    }
  } else if (process.env.FIREWALL_DEBUG) {
    // Stay quiet by default — many parent shells preload the bootstrap
    // before NODE_PATH points at a globally-installed undici, and the
    // child re-load succeeds. Only complain when the user asked.
    process.stderr.write(
      '[firewall] proxy-bootstrap: undici not resolvable in this process. ' +
      'Run `npm install -g undici` once, or use `firewall start --mode docker`.\n'
    );
  }
}
