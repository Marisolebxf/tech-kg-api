// Keep this script independent of the application bundle: it must run when that bundle fails.
(function () {
  'use strict';
  function install() {
    var shell = document.getElementById('kg-page-loading');
    if (!shell) return false;
    var title = document.getElementById('kg-loading-title');
    var message = document.getElementById('kg-loading-message');
    var retry = document.getElementById('kg-loading-retry');
    if (!title || !message || !retry) return false;
    var timer;
    var pending = false;
    var retryUrl = window.location.href;
    var sequence = 0;

    function normalizeOrigin(value) {
      try { return value ? new URL(value, window.location.origin).origin : ''; }
      catch (_) { return ''; }
    }

    function releasePortalLoading() {
      if (window.parent === window) return;
      var config = window.__RUNTIME_CONFIG__ || {};
      var allowed = [window.location.origin];
      String(config.portalAllowedOrigins || '').split(',').forEach(function (value) {
        var origin = normalizeOrigin(value.trim());
        if (origin && allowed.indexOf(origin) < 0) allowed.push(origin);
      });
      var configured = normalizeOrigin(config.portalTargetOrigin);
      var referrer = normalizeOrigin(document.referrer);
      var target = allowed.indexOf(configured) >= 0 ? configured
        : allowed.indexOf(referrer) >= 0 ? referrer : allowed[0];
      try {
        window.parent.postMessage({
          protocol: 'iframe-bridge', version: '1.0',
          id: 'shell_' + Date.now() + '_' + (++sequence),
          action: 'loading.hide', data: {}
        }, target);
      } catch (_) {
        // A portal failure must not stop rendering the child application.
      }
    }

    function fail() {
      window.clearTimeout(timer);
      pending = false;
      shell.hidden = false;
      shell.setAttribute('data-state', 'error');
      shell.setAttribute('role', 'alert');
      shell.setAttribute('aria-busy', 'false');
      title.textContent = '页面暂时无法加载';
      message.textContent = '请重新加载，或通过左侧菜单切换其他业务。';
      retry.hidden = false;
      releasePortalLoading();
    }

    function start(url) {
      window.clearTimeout(timer);
      // Retry only a same-origin route supplied by the router, never an external redirect.
      try {
        var candidate = new URL(url || window.location.href, window.location.href);
        if (candidate.origin === window.location.origin) retryUrl = candidate.href;
      } catch (_) { retryUrl = window.location.href; }
      pending = true;
      var app = document.getElementById('app');
      if (app) app.setAttribute('inert', '');
      shell.hidden = false;
      shell.setAttribute('data-state', 'loading');
      shell.setAttribute('role', 'status');
      shell.setAttribute('aria-busy', 'true');
      title.textContent = '正在加载页面';
      message.textContent = '正在准备业务页面，请稍候。';
      retry.hidden = true;
      timer = window.setTimeout(fail, 20000);
      releasePortalLoading();
    }

    function finish() {
      window.clearTimeout(timer);
      pending = false;
      var app = document.getElementById('app');
      if (app) app.removeAttribute('inert');
      shell.hidden = true;
      shell.setAttribute('aria-busy', 'false');
      releasePortalLoading();
    }

    retry.addEventListener('click', function () { window.location.assign(retryUrl); });
    window.addEventListener('error', function (event) {
      var target = event.target;
      // runtime-config.js is optional outside containers; its absence is not an app failure.
      if (target && target.id === 'kg-runtime-config') {
        releasePortalLoading();
        return;
      }
      // Image/icon failures are local content issues, not startup failures.
      if (pending && (target === window || (target &&
        (target.tagName === 'SCRIPT' || (target.tagName === 'LINK' && target.rel === 'stylesheet'))))) fail();
    }, true);
    window.addEventListener('unhandledrejection', function () {
      if (pending) fail();
    });
    document.addEventListener('load', function (event) {
      if (event.target && event.target.id === 'kg-runtime-config') releasePortalLoading();
    }, true);

    window.__KG_PAGE_LOADING__ = { start: start, finish: finish, fail: fail };
    start();
    return true;
  }

  // Installed in the head before app CSS/module requests. Observe the shell instead of
  // waiting for DOMContentLoaded/window.load, which would wait for deferred application JS.
  if (install()) return;
  var observer = new MutationObserver(function () {
    if (install()) observer.disconnect();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();
