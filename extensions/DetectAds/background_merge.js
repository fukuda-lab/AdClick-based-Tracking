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

/* ============================
   LOAD LOCAL MERGED RULE JSON
   ============================ */
async function loadMergedRules() {
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
  }
}

loadMergedRules
/* ============================
   INITIALIZE ON INSTALL + STARTUP
   ============================ */


//chrome.runtime.onInstalled.addListener(loadMergedRules);
//chrome.runtime.onStartup.addListener(loadMergedRules);

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
    //console.log(BLOCK_RULES.length)
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

