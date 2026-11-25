/*
 * ios-shim.js —— iPhone/iPad 端唯一的 Web 侧改动，由原生在 documentStart 注入。
 * 目的：让安卓那套 app.js / learning.js / sync-core.js 一行不改就能在 WKWebView 上跑。
 *
 * WKWebView 没有 addJavascriptInterface，所以这里把安卓的
 *   ReaderNative.send(id, action, JSON.stringify(body))
 * 三参数调用，翻译成 iOS 的
 *   window.webkit.messageHandlers.ReaderNative.postMessage({id, action, body})
 * 原生 Bridge.swift 同时接受字符串和对象两种 body，因此这里的转换是透明的。
 *
 * 第二件事：给 localStorage 加一层“写回原生”的镜像钩子。
 * WKWebView 的 localStorage 属于系统可回收缓存，存储紧张或系统清理网站数据时会被抹掉，
 * 页面就会“文章全没了”。documentStart 的原生快照 + 这里的写回，构成完整自愈闭环。
 *
 * 注意：window.nativeReply / nativeNotice / nativeSpeechDone 由 app.js、learning.js
 * 自己定义（它们是回调的唯一分发者），本文件绝不覆盖，只在缺失时补一个兜底实现。
 */
(function () {
  'use strict';

  var handler = window.webkit && window.webkit.messageHandlers
    ? window.webkit.messageHandlers.ReaderNative : null;
  if (!handler) return;                       // 非 iOS 壳（浏览器预览 / 安卓）直接放行

  var sequence = 0;

  function post(action, body, id) {
    try {
      handler.postMessage({ id: id, action: action, body: body });
      return true;
    } catch (error) {
      return false;
    }
  }

  // ---- 1. ReaderNative 兼容层：与安卓签名完全一致 -----------------------------
  // Bridge.swift 里 `envelope["body"] as? String` 命中就按原始 JSON 文本解析，
  // 所以 raw 字符串原样透传即可，不做二次编码。
  window.ReaderNative = {
    send: function (id, action, raw) {
      post(action, typeof raw === 'string' ? raw : JSON.stringify(raw), id);
    }
  };

  // ---- 2. 兜底通知（页面若没定义 nativeNotice 才生效）-------------------------
  if (typeof window.nativeNotice !== 'function') {
    window.nativeNotice = function (text) {
      var toast = document.getElementById('toast');
      if (!toast) { console.log(text); return; }
      toast.textContent = text;
      toast.hidden = false;
      clearTimeout(toast.timer);
      toast.timer = setTimeout(function () { toast.hidden = true; }, 4000);
    };
  }

  // ---- 3. localStorage 写回镜像 ----------------------------------------------
  var mirror = window.__storageMirror__ || {};
  var store = window.localStorage;
  if (store && typeof store.setItem === 'function') {
    var rawSet = store.setItem.bind(store);
    var rawRemove = store.removeItem.bind(store);

    function persist(key, value) {
      if (mirror[key] === value) return;          // 内容没变就不发（省掉大量重复写盘）
      mirror[key] = value;
      sequence += 1;
      post('storage', { key: key, value: value }, 'mirror-' + sequence);   // 不等回包
    }

    store.setItem = function (key, value) {
      var text = value == null ? '' : String(value);
      rawSet(key, text);
      persist(String(key), text);
    };
    store.removeItem = function (key) {
      rawRemove(key);
      persist(String(key), '');
    };
    // clear() 要把镜像一起清空，否则下次启动又被快照灌回来
    if (typeof store.clear === 'function') {
      var rawClear = store.clear.bind(store);
      store.clear = function () {
        rawClear();
        Object.keys(mirror).forEach(function (key) { persist(key, ''); });
      };
    }
  }

  // ---- 4. 快照回填后的提示 ----------------------------------------------------
  document.addEventListener('DOMContentLoaded', function () {
    if (!window.__storageRestored__) return;
    if (typeof window.nativeNotice === 'function') {
      window.nativeNotice('检测到系统清理了网页存储，已按本机备份恢复数据');
    }
  });
})();
