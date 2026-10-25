/* ============================
   MERGED RULE FILE (LOCAL)
   ============================ */
const MERGED_RULE_FILE = "rules/merged_rules.json";

/* ============================
   STORAGE IN MEMORY
   ============================ */
let BLOCK_RULES = [];
let ALLOW_RULES = [];
let NETWORK_DOMAINS_SET = new Set();
let RULES_LOADING = null;

/* ============================
   LOAD LOCAL MERGED RULE JSON
   ============================ */
async function loadMergedRules() {
  if (RULES_LOADING) return RULES_LOADING;

  RULES_LOADING = (async () => {
    try {
      const url = chrome.runtime.getURL(MERGED_RULE_FILE);
      const resp = await fetch(url);
      const data = await resp.json();

      BLOCK_RULES = data.block || [];
      ALLOW_RULES = data.allow || [];

      const networkDomains = (data.networkDomains || [])
        .map(d => d.trim().toLowerCase())
        .filter(Boolean);

      NETWORK_DOMAINS_SET = new Set(networkDomains);

      console.log(
        `[AdblockDB] Loaded merged rules → block: ${BLOCK_RULES.length}, allow: ${ALLOW_RULES.length}, network: ${NETWORK_DOMAINS_SET.size}`
      );
    } catch (e) {
      console.error("[AdblockDB] Failed to load merged_rules.json:", e);
    } finally {
      RULES_LOADING = null;
    }
  })();

  return RULES_LOADING;
}

/* ============================
   INITIALIZE ON INSTALL + STARTUP
   ============================ */
chrome.runtime.onInstalled.addListener(() => {
  loadMergedRules();
});

chrome.runtime.onStartup.addListener(() => {
  loadMergedRules();
});
loadMergedRules();

/* ============================
   CONTENT SCRIPT REQUEST → RULES
   ============================ */
chrome.runtime.onMessage.addListener((msg, sender, send) => {
  if (msg === "getAllRules") {
    if (BLOCK_RULES.length === 0 && ALLOW_RULES.length === 0) {
      loadMergedRules().then(() => {
        send({ blocked: BLOCK_RULES, allowed: ALLOW_RULES });
      });
      return true;
    }
    send({ blocked: BLOCK_RULES, allowed: ALLOW_RULES });
    return true;
  }
});

/* ============================
   SAFE SEND MESSAGE TO TAB
   ============================ */
function safeSendMessage(tabId, payload) {
  if (!tabId || tabId < 0) return;

  chrome.tabs.get(tabId, (tab) => {
    if (chrome.runtime.lastError || !tab) return;

    chrome.tabs.sendMessage(tabId, payload, () => {
      if (chrome.runtime.lastError) {
        if (!chrome.runtime.lastError.message.includes("Receiving end does not exist")) {
          console.warn("[AdblockDB] sendMessage error:", chrome.runtime.lastError.message);
        }
      }
    });
  });
}


const MULTI_PART_SUFFIXES = new Set([
  "co.uk", "org.uk", "gov.uk", "ac.uk",
  "co.jp", "ne.jp", "or.jp",
  "com.au", "net.au", "org.au",
  "co.kr", "or.kr",
  "com.br", "com.vn", "net.vn", "edu.vn", "gov.vn",
  "co.in", "com.cn", "com.tw"
]);

function getRegistrableDomain(host) {
  const parts = host.split(".");
  if (parts.length < 2) return host;

  const lastTwo = parts.slice(-2).join(".");
  const lastThree = parts.slice(-3).join(".");

  if (MULTI_PART_SUFFIXES.has(lastTwo) && parts.length >= 3) {
    return lastThree;
  }
  return lastTwo;
}


chrome.webRequest.onBeforeRequest.addListener(
  function (details) {
    try {
      if (!details.tabId || details.tabId < 0) return;

      const url = new URL(details.url);
      const host = url.hostname.toLowerCase();
      const registrable = getRegistrableDomain(host);

      if (NETWORK_DOMAINS_SET.has(host) || NETWORK_DOMAINS_SET.has(registrable)) {
        safeSendMessage(details.tabId, {
          type: "net-hit",
          host,
          url: details.url
        });
      }
    } catch (e) {
      // ignore malformed URL, etc.
    }
  },
  { urls: ["<all_urls>"] }
);

/* ============================
   OUTBOUND AD CLICK CAPTURE
   ============================ */
const AD_CLICK_DOMAINS = [
  "doubleclick.net",
  "googlesyndication.com",
  "googleadservices.com",
  "adservice.google.com",
  "facebook.com",
  "tpc.googlesyndication.com",
  "g.doubleclick.net",
  "adclick.g.doubleclick.net",
  "amazon-adsystem.com",
  "media.net",
  "pubmatic.com",
  "rubiconproject.com",
  "adform.net",
  "moatads.com",
  "yieldmo.com",
  "apm.yahoo.co.jp",
  "ads-feedback.yahoo.co.jp"
];

chrome.webRequest.onBeforeRequest.addListener(
  function (details) {
    try {
      if (details.tabId < 0) return;

      const url = new URL(details.url);
      const host = url.hostname.toLowerCase();

      const isAdClick = AD_CLICK_DOMAINS.some(d => host === d || host.endsWith("." + d));

      if (isAdClick) {
        safeSendMessage(details.tabId, {
          type: "ad-outbound",
          url: details.url,
          host
        });
      }
    } catch (e) {
      console.warn("[AdblockDB] outbound error:", e);
    }
  },
  { urls: ["<all_urls>"] }
);