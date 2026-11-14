"use strict";

(() => {
  const STORAGE_KEY = "ledger.connection";
  const NETWORK_MESSAGE = "目前連不上記帳服務";
  const app = document.querySelector("#app");
  const state = {
    apiBaseUrl: "",
    activeTab: "home",
    ledgerType: "income",
    pageData: {},
    busy: false,
  };

  class ApiError extends Error {}

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[character]);
  }

  function setNotice(message, success = false) {
    const notice = document.querySelector("#global-notice");
    if (!notice) return;
    notice.textContent = message || "";
    notice.classList.toggle("success", success);
  }

  function normalizeApiUrl(value) {
    let url;
    try {
      url = new URL(value.trim());
    } catch {
      throw new ApiError("請輸入有效的後端網址。");
    }

    if (!["http:", "https:"].includes(url.protocol) || !url.hostname) {
      throw new ApiError("後端網址必須使用 http 或 https。");
    }
    if (url.username || url.password || url.search || url.hash) {
      throw new ApiError("網址不可包含帳密、查詢參數或片段。");
    }
    if (url.hostname.toLowerCase() === "localhost" && url.port === "5000") {
      url.hostname = "127.0.0.1";
    }
    url.pathname = url.pathname.replace(/\/+$/, "");
    return url.toString().replace(/\/$/, "");
  }

  function buildRequestUrl(path, query = {}) {
    const url = new URL(`${state.apiBaseUrl}${path}`);
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
    url.searchParams.set("_t", String(Date.now()));
    return url.toString();
  }

  async function requestApi(method, path, body, query = {}) {
    const headers = {};
    const options = {
      method,
      cache: "no-store",
      mode: "cors",
      headers,
    };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }

    let response;
    try {
      const url = method === "GET"
        ? buildRequestUrl(path, query)
        : `${state.apiBaseUrl}${path}`;
      response = await fetch(url, options);
    } catch {
      throw new ApiError(NETWORK_MESSAGE);
    }

    let payload;
    try {
      payload = await response.json();
    } catch {
      throw new ApiError("服務回應格式不正確。");
    }

    if (!response.ok || payload.code !== response.status) {
      throw new ApiError(
        typeof payload.message === "string" && payload.message
          ? payload.message
          : "服務暫時無法處理請求。",
      );
    }
    return payload;
  }

  async function checkConnection(apiBaseUrl) {
    state.apiBaseUrl = apiBaseUrl;
    const response = await requestApi("GET", "/api/health");
    if (response.code !== 200 || response.data?.status !== "ok") {
      throw new ApiError(response.message || "後端健康檢查未通過。");
    }
  }

  function saveConnection(apiBaseUrl) {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ apiBaseUrl }),
    );
    state.apiBaseUrl = apiBaseUrl;
  }

  function renderConnection(message = "", value = "") {
    app.innerHTML = `
      <main class="connection-screen">
        <section class="connection-card" aria-labelledby="connect-title">
          <div class="brand">
            <span class="brand-mark" aria-hidden="true">記</span>
            <span>日常記帳</span>
          </div>
          <p class="eyebrow">PERSONAL LEDGER</p>
          <h1 id="connect-title">連接你的帳本</h1>
          <p class="subheading">輸入已啟動的記帳服務網址，確認連線後即可開始使用。</p>
          <p id="connect-notice" class="notice" role="status">${escapeHtml(message)}</p>
          <form id="connect-form" class="form-grid">
            <div class="field">
              <label for="api-url">後端網址</label>
              <input id="api-url" name="apiBaseUrl" type="url" inputmode="url"
                placeholder="http://127.0.0.1:5000" value="${escapeHtml(value)}"
                autocomplete="url" required>
              <p class="input-hint">例如 http://127.0.0.1:5000</p>
            </div>
            <button id="connect-submit" class="primary-button full-width" type="submit">
              測試連線並開始
            </button>
          </form>
          <p class="connection-note">只儲存後端網址，不需要會員帳號或金鑰。</p>
        </section>
      </main>`;
    document.title = "日常記帳｜連線";

    document.querySelector("#connect-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = document.querySelector("#api-url");
      const button = document.querySelector("#connect-submit");
      const notice = document.querySelector("#connect-notice");
      button.disabled = true;
      button.textContent = "正在確認連線…";
      notice.textContent = "";
      try {
        const apiBaseUrl = normalizeApiUrl(input.value);
        await checkConnection(apiBaseUrl);
        saveConnection(apiBaseUrl);
        await enterApp();
      } catch (error) {
        notice.textContent = error instanceof ApiError
          ? error.message
          : NETWORK_MESSAGE;
        button.disabled = false;
        button.textContent = "測試連線並開始";
      }
    });
  }

  function currentMonth() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const lastDay = new Date(year, now.getMonth() + 1, 0).getDate();
    return {
      month: `${year}-${month}`,
      from: `${year}-${month}-01`,
      to: `${year}-${month}-${String(lastDay).padStart(2, "0")}`,
    };
  }

  function today() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  }

  function formatAmount(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return "—";
    return new Intl.NumberFormat("zh-TW", {
      maximumFractionDigits: 2,
    }).format(amount);
  }

  function readValue(source, keys) {
    if (typeof source === "number" || typeof source === "string") return source;
    if (!source || typeof source !== "object") return undefined;
    for (const key of keys) {
      if (source[key] !== undefined && source[key] !== null) return source[key];
    }
    return undefined;
  }

  function formatDate(value) {
    if (!value) return "—";
    return escapeHtml(String(value).slice(0, 10));
  }

  function renderShell() {
    const pages = {
      home: renderHome,
      ledger: renderLedger,
      investments: renderInvestments,
      invoices: renderInvoices,
    };
    const pageTitle = {
      home: "首頁",
      ledger: "記帳",
      investments: "投資",
      invoices: "發票",
    };

    app.innerHTML = `
      <header class="topbar">
        <div class="brand"><span class="brand-mark" aria-hidden="true">記</span><span>日常記帳</span></div>
        <button id="clear-connection" class="clear-link" type="button">清除連線</button>
      </header>
      <main class="main-content">
        <p id="global-notice" class="notice" role="status"></p>
        <div id="page-content">${pages[state.activeTab]()}</div>
      </main>
      <nav class="bottom-nav" aria-label="主要導覽">
        ${[
          ["home", "首頁", "⌂"],
          ["ledger", "記帳", "＋"],
          ["investments", "投資", "↗"],
          ["invoices", "發票", "▤"],
        ].map(([tab, label, icon]) => `
          <button class="nav-button" type="button" data-tab="${tab}"
            aria-current="${state.activeTab === tab ? "page" : "false"}"
            aria-label="${label}">
            <span class="nav-icon" aria-hidden="true">${icon}</span>
            <span>${label}</span>
          </button>`).join("")}
      </nav>`;

    document.querySelector("#clear-connection").addEventListener("click", clearConnection);
    document.querySelectorAll("[data-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        state.activeTab = button.dataset.tab;
        state.pageData = {};
        renderShell();
        loadActivePage();
      });
    });
    document.title = `日常記帳｜${pageTitle[state.activeTab]}`;
  }

  function renderHome() {
    const month = currentMonth().month;
    const summary = state.pageData.summary;
    const accounts = state.pageData.accounts;
    const summaryError = state.pageData.summaryError;
    const accountError = state.pageData.accountError;

    return `
      <div class="page-heading">
        <div>
          <p class="eyebrow">MONTHLY OVERVIEW</p>
          <h1>本月概況</h1>
          <p class="subheading">${month}</p>
        </div>
      </div>
      ${summaryError ? `<p class="notice-box">${escapeHtml(summaryError)}</p>` : ""}
      <section class="summary-grid" aria-label="本月收支">
        <article class="summary-card income">
          <span class="summary-label">本月入帳</span>
          <strong class="summary-amount">${summary ? formatAmount(summary.income_twd) : "—"}</strong>
          <span class="summary-label">TWD</span>
        </article>
        <article class="summary-card expense">
          <span class="summary-label">本月花費</span>
          <strong class="summary-amount">${summary ? formatAmount(summary.expense_twd) : "—"}</strong>
          <span class="summary-label">TWD</span>
        </article>
      </section>
      <div class="section-title"><h2>我的帳戶</h2></div>
      ${accountError ? `<p class="notice-box">${escapeHtml(accountError)}</p>` : ""}
      ${accounts?.length
        ? `<section class="account-list" aria-label="帳戶清單">
            ${accounts.map((account) => {
              const balance = state.pageData.balances?.[account.id];
              const balanceError = state.pageData.balanceErrors?.[account.id];
              const twdBalance = balance?.twd_balance ?? balance?.balance_twd;
              return `<article class="account-row">
                <div class="row-top">
                  <div class="row-primary">
                    <h3>${escapeHtml(account.name)}</h3>
                    <p class="muted">${escapeHtml(account.currency || "TWD")} · ${escapeHtml(account.kind || "")}</p>
                  </div>
                  <div class="account-balance">
                    <strong class="money">${twdBalance === undefined ? "—" : formatAmount(twdBalance)}</strong>
                    <span class="muted">台幣餘額</span>
                  </div>
                </div>
                ${balanceError ? `<p class="inline-error">${escapeHtml(balanceError)}</p>` : ""}
              </article>`;
            }).join("")}
          </section>`
        : accounts && !accounts.length
          ? `<section class="card section-card">
              <div class="empty-state">
                <span class="empty-icon" aria-hidden="true">＋</span>
                <h3>先建立你的第一個帳戶</h3>
                <p class="muted">建立現金帳戶後，就可以開始記錄收支。</p>
              </div>
              <form id="create-account-form" class="form-grid" style="margin-top:16px">
                <div class="field">
                  <label for="account-name">帳戶名稱</label>
                  <input id="account-name" name="name" value="現金錢包" required>
                </div>
                <button class="primary-button full-width" type="submit">建立現金帳戶</button>
              </form>
            </section>`
          : `<p class="loading-line">正在載入帳戶…</p>`}`;
  }

  function renderLedger() {
    const type = state.ledgerType;
    const isIncome = type === "income";
    const categories = state.pageData.categories;
    const accounts = state.pageData.accounts;
    const entries = state.pageData.entries;
    const categoryError = state.pageData.categoryError;
    const accountError = state.pageData.accountError;
    const entryError = state.pageData.entryError;

    return `
      <div class="page-heading">
        <div><p class="eyebrow">DAILY RECORD</p><h1>記一筆</h1><p class="subheading">簡單留下每一筆日常。</p></div>
      </div>
      <div class="segmented" role="group" aria-label="切換收支類型">
        <button type="button" data-ledger-type="income" aria-pressed="${isIncome}">入帳</button>
        <button type="button" data-ledger-type="expense" aria-pressed="${!isIncome}">花費</button>
      </div>
      ${categoryError ? `<p class="notice-box" style="margin-top:14px">${escapeHtml(categoryError)}</p>` : ""}
      ${accountError ? `<p class="notice-box" style="margin-top:14px">${escapeHtml(accountError)}</p>` : ""}
      ${!accounts?.length && !accountError
        ? `<div class="empty-state" style="margin-top:14px"><h3>先建立帳戶</h3><p class="muted">請到首頁建立現金帳戶後再記帳。</p><button class="secondary-button" type="button" data-go-home>前往首頁</button></div>`
        : ""}
      <form id="entry-form" class="card form-card" style="margin-top:14px">
        <div class="form-grid">
          <div class="field">
            <label for="entry-date">${isIncome ? "入帳日期" : "消費日期"}</label>
            <input id="entry-date" name="date" type="date" value="${today()}" required>
          </div>
          <div class="field">
            <label for="entry-amount">金額</label>
            <input id="entry-amount" name="amount" type="number" min="0.01" step="any"
              inputmode="decimal" placeholder="0" required>
          </div>
          <div class="field">
            <label for="entry-category">${isIncome ? "入帳分類" : "花費分類"}</label>
            ${categories?.length
              ? `<select id="entry-category" name="category_id" required>
                  ${categories.map((category) => `<option value="${escapeHtml(category.id)}">${escapeHtml(category.name)}</option>`).join("")}
                </select>`
              : `<input id="entry-category" name="category_name" placeholder="例如：${isIncome ? "薪資" : "餐飲"}" required>
                 <p class="input-hint">目前沒有分類，送出時會先建立此分類。</p>`}
          </div>
          <div class="field">
            <label for="entry-account">帳戶</label>
            <select id="entry-account" name="account_id" required ${accounts?.length ? "" : "disabled"}>
              ${(accounts || []).map((account) => `<option value="${escapeHtml(account.id)}" data-currency="${escapeHtml(account.currency || "TWD")}">${escapeHtml(account.name)} · ${escapeHtml(account.currency || "TWD")}</option>`).join("")}
            </select>
          </div>
          <div class="field">
            <label for="entry-currency">幣別</label>
            <input id="entry-currency" name="currency" value="${escapeHtml(accounts?.[0]?.currency || "TWD")}" readonly>
          </div>
          <div class="field">
            <label for="entry-fx">台幣匯率</label>
            <input id="entry-fx" name="fx_rate_to_twd" type="number" min="0.000001"
              step="any" value="${accounts?.[0]?.currency === "TWD" || !accounts?.length ? "1" : ""}" required>
          </div>
          ${isIncome
            ? `<div class="field">
                <label for="entry-source">來源</label>
                <input id="entry-source" name="source" placeholder="例如：薪資">
                <p class="input-hint">來源與備註至少填寫一項。</p>
              </div>
              <div class="field">
                <label for="entry-note">備註（選填）</label>
                <input id="entry-note" name="note" placeholder="補充說明">
              </div>`
            : `<div class="field">
                <label for="entry-merchant">商家</label>
                <input id="entry-merchant" name="merchant" placeholder="例如：咖啡店">
                <p class="input-hint">商家與備註至少填寫一項。</p>
              </div>
              <div class="field">
                <label for="entry-note">備註（選填）</label>
                <input id="entry-note" name="note" placeholder="補充說明">
              </div>`}
          <button class="primary-button full-width" type="submit" ${accounts?.length && !categoryError ? "" : "disabled"}>
            新增${isIncome ? "入帳" : "花費"}
          </button>
        </div>
      </form>
      <div class="section-title"><h2>本月${isIncome ? "入帳" : "花費"}</h2><span class="tag">${currentMonth().month}</span></div>
      ${entryError ? `<p class="notice-box">${escapeHtml(entryError)}</p>` : ""}
      ${entries
        ? entries.length
          ? `<section class="entry-list" aria-label="本月${isIncome ? "入帳" : "花費"}清單">
              ${entries.map((entry) => renderEntry(entry, isIncome)).join("")}
            </section>`
          : `<div class="empty-state"><span class="empty-icon" aria-hidden="true">◷</span><h3>本月還沒有紀錄</h3><p class="muted">新增一筆收支，這裡就會立即更新。</p></div>`
        : `<p class="loading-line">正在載入本月紀錄…</p>`}`;
  }

  function renderEntry(entry, isIncome) {
    const detail = isIncome
      ? entry.source || entry.note || "入帳"
      : entry.merchant || entry.note || "花費";
    const date = isIncome ? entry.received_on : entry.spent_on;
    return `<article class="entry-row">
      <div class="row-primary">
        <h3>${escapeHtml(detail)}</h3>
        <p class="muted">${formatDate(date)} · ${escapeHtml(entry.currency || "TWD")}</p>
      </div>
      <strong class="entry-amount ${isIncome ? "income" : "expense"}">${isIncome ? "+" : "−"}${formatAmount(entry.amount)}</strong>
    </article>`;
  }

  function renderInvestments() {
    const instruments = state.pageData.instruments;
    const error = state.pageData.instrumentError;
    const fetchMessage = state.pageData.fetchMessage;
    return `
      <div class="page-heading">
        <div><p class="eyebrow">PORTFOLIO</p><h1>投資</h1><p class="subheading">台股持有與最新報價。</p></div>
      </div>
      <button id="fetch-quotes" class="primary-button full-width" type="button" ${state.busy ? "disabled" : ""}>
        ${state.busy ? "正在更新報價…" : "更新台股報價"}
      </button>
      ${fetchMessage ? `<p class="notice success" style="margin-top:10px">${escapeHtml(fetchMessage)}</p>` : ""}
      ${error ? `<p class="notice-box" style="margin-top:12px">${escapeHtml(error)}</p>` : ""}
      <div class="section-title"><h2>台股標的</h2></div>
      ${instruments
        ? instruments.length
          ? `<section class="investment-list" aria-label="台股投資標的">
              ${instruments.map((instrument) => {
                const holdingResult = state.pageData.holdings?.[instrument.id];
                const quoteResult = state.pageData.quotes?.[instrument.id];
                const holdingError = state.pageData.holdingErrors?.[instrument.id];
                const quoteError = state.pageData.quoteErrors?.[instrument.id];
                const holdingLoaded = Object.prototype.hasOwnProperty.call(
                  state.pageData.holdings || {},
                  instrument.id,
                );
                const quoteLoaded = Object.prototype.hasOwnProperty.call(
                  state.pageData.quotes || {},
                  instrument.id,
                );
                const holding = readValue(holdingResult, [
                  "quantity",
                  "holding",
                  "shares",
                  "holding_quantity",
                  "held_quantity",
                ]);
                const quote = readValue(quoteResult, [
                  "price",
                  "latest_price",
                  "close",
                  "close_price",
                ]);
                return `<article class="investment-card">
                  <div class="investment-top">
                    <div class="row-primary">
                      <h3>${escapeHtml(instrument.name)}</h3>
                      <p class="muted">${escapeHtml(instrument.symbol)} · ${escapeHtml(instrument.currency || "TWD")}</p>
                    </div>
                    <span class="tag">台股</span>
                  </div>
                  <div class="investment-stats">
                    <div class="investment-stat">
                      <span class="muted">持有數量</span>
                      <strong>${holdingError ? "—" : !holdingLoaded ? "載入中" : holding === undefined ? "—" : formatAmount(holding)}</strong>
                      ${holdingError ? `<p class="inline-error">${escapeHtml(holdingError)}</p>` : ""}
                    </div>
                    <div class="investment-stat">
                      <span class="muted">最新報價</span>
                      <strong>${quoteError ? "—" : !quoteLoaded ? "載入中" : quote === undefined ? "還沒有報價" : formatAmount(quote)}</strong>
                      ${quoteError ? `<p class="inline-error">${escapeHtml(quoteError)}</p>` : ""}
                    </div>
                  </div>
                </article>`;
              }).join("")}
            </section>`
          : `<div class="empty-state"><span class="empty-icon" aria-hidden="true">↗</span><h3>還沒有台股標的</h3><p class="muted">新增 tw_stock 標的後會顯示在這裡。</p></div>`
        : `<p class="loading-line">正在載入投資標的…</p>`}`;
  }

  function renderInvoices() {
    const invoices = state.pageData.invoices;
    const error = state.pageData.invoiceError;
    const prizeLabels = {
      unchecked: "尚未對獎",
      lost: "未中獎",
      won: "已中獎",
      claimed: "已領取",
      void: "已作廢",
    };
    return `
      <div class="page-heading">
        <div><p class="eyebrow">INVOICE ARCHIVE</p><h1>發票</h1><p class="subheading">查看已記錄的發票。</p></div>
      </div>
      ${error ? `<p class="notice-box">${escapeHtml(error)}</p>` : ""}
      ${invoices
        ? invoices.length
          ? `<section class="invoice-list" aria-label="發票清單">
              ${invoices.map((invoice) => `<article class="invoice-row">
                <div class="row-primary">
                  <h3>${escapeHtml(invoice.number)}</h3>
                  <p class="muted">${formatDate(invoice.issued_on)}</p>
                  <span class="tag invoice-status">${escapeHtml(prizeLabels[invoice.prize_status] || invoice.prize_status || "未設定")}</span>
                </div>
                <strong class="entry-amount">${formatAmount(invoice.amount)} <small>${escapeHtml(invoice.currency || "TWD")}</small></strong>
              </article>`).join("")}
            </section>`
          : `<div class="empty-state"><span class="empty-icon" aria-hidden="true">▤</span><h3>目前沒有發票</h3><p class="muted">新增的發票會出現在這裡。</p></div>`
        : `<p class="loading-line">正在載入發票…</p>`}`;
  }

  async function loadHome() {
    state.pageData = {};
    renderShell();
    const month = currentMonth().month;
    const [summaryResult, accountsResult] = await Promise.allSettled([
      requestApi("GET", "/api/summary", undefined, { month }),
      requestApi("GET", "/api/accounts"),
    ]);

    if (summaryResult.status === "fulfilled") {
      state.pageData.summary = summaryResult.value.data;
    } else {
      state.pageData.summaryError = summaryResult.reason.message;
    }
    if (accountsResult.status === "fulfilled") {
      state.pageData.accounts = accountsResult.value.data || [];
    } else {
      state.pageData.accountError = accountsResult.reason.message;
    }
    renderShell();

    if (state.pageData.accounts?.length) {
      const balances = {};
      const balanceErrors = {};
      await Promise.all(state.pageData.accounts.map(async (account) => {
        try {
          const result = await requestApi("GET", `/api/accounts/${account.id}/balance`);
          balances[account.id] = result.data;
        } catch (error) {
          balanceErrors[account.id] = error.message;
        }
      }));
      state.pageData.balances = balances;
      state.pageData.balanceErrors = balanceErrors;
      renderShell();
    }

    const form = document.querySelector("#create-account-form");
    if (form) {
      form.addEventListener("submit", createCashAccount);
    }
  }

  async function createCashAccount(event) {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      await requestApi("POST", "/api/accounts", {
        name: new FormData(event.currentTarget).get("name"),
        kind: "cash",
        currency: "TWD",
        opening_balance: 0,
      });
      await loadHome();
    } catch (error) {
      button.disabled = false;
      setNotice(error.message);
    }
  }

  async function loadLedger() {
    state.pageData = {};
    renderShell();
    const isIncome = state.ledgerType === "income";
    const month = currentMonth();
    const categoryPath = isIncome ? "/api/income-categories" : "/api/expense-categories";
    const entryPath = isIncome ? "/api/incomes" : "/api/expenses";
    const dateQuery = { date_from: month.from, date_to: month.to };
    const [categoryResult, accountResult, entryResult] = await Promise.allSettled([
      requestApi("GET", categoryPath),
      requestApi("GET", "/api/accounts"),
      requestApi("GET", entryPath, undefined, dateQuery),
    ]);

    if (categoryResult.status === "fulfilled") {
      state.pageData.categories = categoryResult.value.data || [];
    } else {
      state.pageData.categoryError = categoryResult.reason.message;
    }
    if (accountResult.status === "fulfilled") {
      state.pageData.accounts = accountResult.value.data || [];
    } else {
      state.pageData.accountError = accountResult.reason.message;
    }
    if (entryResult.status === "fulfilled") {
      const dateField = isIncome ? "received_on" : "spent_on";
      state.pageData.entries = (entryResult.value.data || [])
        .slice()
        .sort((left, right) => String(right[dateField]).localeCompare(String(left[dateField])));
    } else {
      state.pageData.entryError = entryResult.reason.message;
    }
    renderShell();
    bindLedgerEvents();
  }

  function bindLedgerEvents() {
    document.querySelectorAll("[data-ledger-type]").forEach((button) => {
      button.addEventListener("click", () => {
        state.ledgerType = button.dataset.ledgerType;
        loadLedger();
      });
    });

    const accountSelect = document.querySelector("#entry-account");
    accountSelect?.addEventListener("change", () => {
      const currency = accountSelect.selectedOptions[0]?.dataset.currency || "TWD";
      document.querySelector("#entry-currency").value = currency;
      const rateInput = document.querySelector("#entry-fx");
      if (currency === "TWD") rateInput.value = "1";
      else if (rateInput.value === "1") rateInput.value = "";
    });

    document.querySelector("[data-go-home]")?.addEventListener("click", () => {
      state.activeTab = "home";
      loadHome();
    });
    document.querySelector("#entry-form")?.addEventListener("submit", submitEntry);
  }

  async function submitEntry(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const button = form.querySelector("button[type=submit]");
    const isIncome = state.ledgerType === "income";
    const categoryList = state.pageData.categories || [];
    const selectedAccount = (state.pageData.accounts || []).find(
      (account) => String(account.id) === String(values.get("account_id")),
    );
    if (!selectedAccount) {
      setNotice("請先建立帳戶。");
      return;
    }
    button.disabled = true;
    try {
      let categoryId;
      if (categoryList.length) {
        categoryId = Number(values.get("category_id"));
      } else {
        const categoryName = String(values.get("category_name") || "").trim();
        if (!categoryName) throw new ApiError("請輸入分類名稱。");
        const categoryPath = isIncome ? "/api/income-categories" : "/api/expense-categories";
        const createdCategory = await requestApi("POST", categoryPath, { name: categoryName });
        categoryId = createdCategory.data.id;
      }

      const amount = Number(values.get("amount"));
      const fxRate = Number(values.get("fx_rate_to_twd"));
      if (!Number.isFinite(amount) || amount <= 0) {
        throw new ApiError("金額必須大於 0。");
      }
      if (!Number.isFinite(fxRate) || fxRate <= 0) {
        throw new ApiError("台幣匯率必須大於 0。");
      }

      const payload = {
        [isIncome ? "received_on" : "spent_on"]: values.get("date"),
        amount,
        currency: selectedAccount.currency || "TWD",
        fx_rate_to_twd: fxRate,
        category_id: categoryId,
        account_id: Number(selectedAccount.id),
      };
      if (isIncome) {
        payload.source = String(values.get("source") || "").trim() || null;
        payload.note = String(values.get("note") || "").trim() || null;
        if (!payload.source && !payload.note) {
          throw new ApiError("來源與備註至少需填寫一項。");
        }
      } else {
        payload.merchant = String(values.get("merchant") || "").trim() || null;
        payload.note = String(values.get("note") || "").trim() || null;
        if (!payload.merchant && !payload.note) {
          throw new ApiError("商家與備註至少需填寫一項。");
        }
      }

      const path = isIncome ? "/api/incomes" : "/api/expenses";
      const created = await requestApi("POST", path, payload);
      const dateField = isIncome ? "received_on" : "spent_on";
      const month = currentMonth();
      if (created.data && created.data[dateField] >= month.from && created.data[dateField] <= month.to) {
        state.pageData.entries = [created.data, ...(state.pageData.entries || [])];
      }
      renderShell();
      bindLedgerEvents();
      setNotice(`已新增${isIncome ? "入帳" : "花費"}。`, true);
    } catch (error) {
      button.disabled = false;
      setNotice(error.message);
    }
  }

  async function loadInvestments() {
    const fetchMessage = state.pageData.fetchMessage;
    state.pageData = {};
    if (fetchMessage) state.pageData.fetchMessage = fetchMessage;
    renderShell();
    try {
      const result = await requestApi("GET", "/api/instruments");
      state.pageData.instruments = (result.data || []).filter(
        (instrument) => instrument.market === "tw_stock",
      );
    } catch (error) {
      state.pageData.instrumentError = error.message;
    }
    renderShell();
    bindQuoteFetch();

    if (!state.pageData.instruments?.length) return;
    const holdings = {};
    const quotes = {};
    const holdingErrors = {};
    const quoteErrors = {};
    await Promise.all(state.pageData.instruments.map(async (instrument) => {
      const [holdingResult, quoteResult] = await Promise.allSettled([
        requestApi("GET", `/api/instruments/${instrument.id}/holding`),
        requestApi("GET", `/api/instruments/${instrument.id}/quote`),
      ]);
      if (holdingResult.status === "fulfilled") {
        holdings[instrument.id] = holdingResult.value.data;
      } else {
        holdingErrors[instrument.id] = holdingResult.reason.message;
      }
      if (quoteResult.status === "fulfilled") {
        quotes[instrument.id] = quoteResult.value.data;
      } else {
        quoteErrors[instrument.id] = quoteResult.reason.message;
      }
    }));
    state.pageData.holdings = holdings;
    state.pageData.quotes = quotes;
    state.pageData.holdingErrors = holdingErrors;
    state.pageData.quoteErrors = quoteErrors;
    renderShell();
    bindQuoteFetch();
  }

  function countValue(value) {
    if (Array.isArray(value)) return value.length;
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
  }

  function bindQuoteFetch() {
    document.querySelector("#fetch-quotes")?.addEventListener("click", async () => {
      state.busy = true;
      state.pageData.fetchMessage = "";
      renderShell();
      bindQuoteFetch();
      try {
        const result = await requestApi("POST", "/api/tw-stock-quotes/fetch");
        const missing = countValue(result.data?.missing);
        const skipped = countValue(result.data?.skipped);
        state.pageData.fetchMessage = `報價更新完成，${missing} 檔暫無資料、${skipped} 檔略過。`;
        state.busy = false;
        await loadInvestments();
      } catch (error) {
        state.busy = false;
        setNotice(error.message);
        renderShell();
        bindQuoteFetch();
      }
    });
  }

  async function loadInvoices() {
    state.pageData = {};
    renderShell();
    try {
      const result = await requestApi("GET", "/api/invoices");
      state.pageData.invoices = result.data || [];
    } catch (error) {
      state.pageData.invoiceError = error.message;
    }
    renderShell();
  }

  async function enterApp() {
    state.activeTab = "home";
    state.pageData = {};
    renderShell();
    await loadHome();
  }

  async function clearConnection() {
    localStorage.removeItem(STORAGE_KEY);
    state.apiBaseUrl = "";
    state.pageData = {};
    renderConnection();
  }

  async function initialize() {
    const savedValue = localStorage.getItem(STORAGE_KEY);
    if (!savedValue) {
      renderConnection();
      return;
    }

    let saved;
    try {
      saved = JSON.parse(savedValue);
    } catch {
      localStorage.removeItem(STORAGE_KEY);
      renderConnection("請重新輸入後端網址。");
      return;
    }
    if (!saved || typeof saved.apiBaseUrl !== "string") {
      localStorage.removeItem(STORAGE_KEY);
      renderConnection("請重新輸入後端網址。");
      return;
    }

    let apiBaseUrl;
    try {
      apiBaseUrl = normalizeApiUrl(saved.apiBaseUrl);
      renderConnection("正在重新確認後端連線…", apiBaseUrl);
      await checkConnection(apiBaseUrl);
      saveConnection(apiBaseUrl);
      await enterApp();
    } catch (error) {
      localStorage.removeItem(STORAGE_KEY);
      renderConnection(
        error instanceof ApiError ? error.message : NETWORK_MESSAGE,
        saved.apiBaseUrl,
      );
    }
  }

  initialize();
})();
