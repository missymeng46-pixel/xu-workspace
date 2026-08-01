function localIsoDate(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

const todayIso = localIsoDate();

const state = {
  view: "today",
  apiReady: false,
  summary: {
    income: 0,
    expense: 0,
    net: 0,
    netWorth: 0,
    receivable: 0,
    budget: 15000,
    budgetRemaining: 15000,
    breakdown: [],
    allocatedBudget: 0,
    unallocatedBudget: 15000,
    categoryBudgets: [],
  },
  transactions: [],
  accounts: [],
  categories: [],
  inbox: [],
  tasks: [],
  projects: [],
  contentItems: [],
  exerciseCheckins: [],
  notes: [],
  wechatStatus: {
    configured: false,
    autoClassify: true,
    processor: "codex",
    codexAvailable: false,
    allowedOpenIds: 0,
    receivedCount: 0,
    lastReceivedAt: null,
  },
  profile: {
    displayName: "新朋友",
    workspaceName: "我的工作空间",
  },
  pendingDeleteId: null,
  pendingDeleteEntity: null,
  pendingInboxTransactionId: null,
  pendingManualInboxId: null,
  clientLocal: true,
  dataSignature: "",
  remoteSyncing: false,
  expandedTransactionGroups: new Set(),
};

const icons = {
  home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3.5 10.5 12 3.8l8.5 6.7v9a1 1 0 0 1-1 1h-5v-6h-5v6h-5a1 1 0 0 1-1-1z"/></svg>',
  calendar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M8 2.5V7M16 2.5V7M3.5 10h17M8 14h2M14 14h2M8 17h2"/></svg>',
  wallet: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 6.5h14a2 2 0 0 1 2 2v10H5a2 2 0 0 1-2-2v-11a2 2 0 0 1 2-2h12"/><path d="M15 11h6v5h-6a2.5 2.5 0 0 1 0-5Z"/></svg>',
  layers: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="m4 8 8-4 8 4-8 4zM4 12l8 4 8-4M4 16l8 4 8-4"/></svg>',
  pen: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="m14 5 5 5M4 20l3.8-.8L20 7a2.1 2.1 0 0 0-3-3L4.8 16.2z"/></svg>',
  inbox: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 5h16v14H4z"/><path d="M4 14h4l2 3h4l2-3h4"/></svg>',
  exercise: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="7" cy="6" r="2"/><path d="m9 10 3-2 3 3 4 1M12 8l-2 5-4 3M10 13l4 2 2 5M8 20l2-5"/></svg>',
  settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.4 1A8 8 0 0 0 15 6.2L14.7 3h-4L10 6.2a8 8 0 0 0-1.6.9l-2.4-1-2 3.4L6.1 11a7 7 0 0 0 0 2L4 14.5l2 3.4 2.4-1a8 8 0 0 0 1.6.9l.7 3.2h4l.3-3.2a8 8 0 0 0 1.6-.9l2.4 1 2-3.4-2.1-1.5c.1-.3.1-.7.1-1Z"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 5 5"/></svg>',
  bell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4"/></svg>',
  phone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="7" y="2.5" width="10" height="19" rx="2"/><path d="M10 5h4M11 18.5h2"/></svg>',
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error || "操作失败，请稍后重试");
    error.code = payload.code || "";
    error.status = response.status;
    throw error;
  }
  return payload;
}

async function loadData({ quiet = false, renderUnchanged = true } = {}) {
  try {
    const payload = await api("/api/bootstrap");
    const signature = JSON.stringify([
      payload.summary, payload.transactions, payload.inbox, payload.tasks, payload.projects,
      payload.contentItems, payload.exerciseCheckins, payload.notes, payload.profile, payload.wechatStatus,
    ]);
    const dataChanged = signature !== state.dataSignature;
    state.dataSignature = signature;
    state.summary = payload.summary;
    state.transactions = payload.transactions;
    state.accounts = payload.accounts;
    state.categories = payload.categories;
    state.inbox = payload.inbox;
    state.tasks = payload.tasks || [];
    state.projects = payload.projects || [];
    state.contentItems = payload.contentItems || [];
    state.exerciseCheckins = payload.exerciseCheckins || [];
    state.notes = payload.notes || [];
    state.wechatStatus = payload.wechatStatus || state.wechatStatus;
    state.profile = payload.profile || state.profile;
    state.clientLocal = payload.client?.local !== false;
    document.querySelector("#openPhoneAccess").hidden = !state.clientLocal;
    updateProfileUi();
    state.apiReady = true;
    const inboxBadge = document.querySelector("#inboxBadge");
    inboxBadge.textContent = activeInboxItems().length;
    inboxBadge.hidden = activeInboxItems().length === 0;
    if (dataChanged || renderUnchanged) render(state.view);
  } catch (error) {
    state.apiReady = false;
    render(state.view);
    if (error.code === "mobile_auth_required") {
      openMobileLogin();
      return;
    }
    if (!quiet) showToast(`本地数据服务未连接：${error.message}`, true);
  }
}

async function syncLinkedDevices() {
  if (!state.apiReady || state.remoteSyncing || document.visibilityState !== "visible" || document.querySelector("dialog[open]")) return;
  state.remoteSyncing = true;
  try {
    await loadData({ quiet: true, renderUnchanged: false });
  } finally {
    state.remoteSyncing = false;
  }
}

function openMobileLogin() {
  const dialog = document.querySelector("#mobileLoginDialog");
  if (!dialog.open) dialog.showModal();
  setTimeout(() => document.querySelector("#mobileLoginCode").focus(), 80);
}

async function openMobileAccess() {
  try {
    const access = await api("/api/mobile-access");
    if (!access.enabled || !access.url) throw new Error("暂时没有检测到可用的 Wi-Fi 地址，请连接 Wi-Fi 后重启工作台");
    document.querySelector("#mobileAccessUrl").value = access.url;
    document.querySelector("#mobileAccessCode").textContent = String(access.accessCode).replace(/(\d{3})(\d{3})/, "$1 $2");
    const qrRoot = document.querySelector("#mobileQrCode");
    qrRoot.innerHTML = "";
    if (window.QRCode) new QRCode(qrRoot, { text: access.url, width: 180, height: 180, colorDark: "#713a30", colorLight: "#ffffff", correctLevel: QRCode.CorrectLevel.M });
    document.querySelector("#mobileAccessDialog").showModal();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function copyText(value) {
  try {
    await navigator.clipboard.writeText(value);
  } catch (_) {
    const input = document.querySelector("#mobileAccessUrl");
    input.select();
    document.execCommand("copy");
  }
  showToast("手机访问地址已复制");
}

function formatMoney(value, { sign = false } = {}) {
  const amount = Number(value || 0);
  const formatted = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(Math.abs(amount));
  const prefix = sign ? (amount >= 0 ? "+ " : "- ") : (amount < 0 ? "-" : "");
  return `${prefix}¥${formatted}`;
}

function escapeHtml(value = "") {
  return String(value).replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

function budgetPercent() {
  if (!state.summary.budget) return state.summary.expense ? 100 : 0;
  return Math.min(100, Math.round((state.summary.expense / state.summary.budget) * 100));
}

function budgetRemaining() {
  return Number(state.summary.budgetRemaining ?? (state.summary.budget - state.summary.expense));
}

function todayTasks() {
  return state.tasks.filter(task => task.dueDate === todayIso);
}

function isoDateOffset(days) {
  const target = new Date(`${todayIso}T12:00:00`);
  target.setDate(target.getDate() + days);
  return localIsoDate(target);
}

function planGroups() {
  const tomorrow = isoDateOffset(1);
  const weekEnd = isoDateOffset(7);
  const openTasks = state.tasks.filter(task => !task.completedAt);
  return {
    overdue: openTasks.filter(task => task.dueDate < todayIso).sort((a, b) => a.dueDate.localeCompare(b.dueDate)),
    today: openTasks.filter(task => task.dueDate === todayIso),
    tomorrow: openTasks.filter(task => task.dueDate === tomorrow),
    week: openTasks.filter(task => task.dueDate > tomorrow && task.dueDate <= weekEnd).sort((a, b) => a.dueDate.localeCompare(b.dueDate)),
    later: openTasks.filter(task => task.dueDate > weekEnd).sort((a, b) => a.dueDate.localeCompare(b.dueDate)),
    completed: state.tasks.filter(task => task.completedAt).sort((a, b) => String(b.completedAt).localeCompare(String(a.completedAt))),
  };
}

function activeInboxItems() {
  return state.inbox.filter(item => item.status !== "processed");
}

function completedTodayTasks() {
  return state.tasks.filter(task => task.completedAt?.slice(0, 10) === todayIso);
}

function formatClock(value) {
  if (!value) return "--:--";
  const match = String(value).match(/[T ](\d{2}:\d{2})/);
  return match?.[1] || "--:--";
}

function profileInitial(name) {
  const first = Array.from(String(name).trim())[0] || "序";
  return /[a-z]/i.test(first) ? first.toUpperCase() : first;
}

function greetingText() {
  const hour = new Date().getHours();
  const period = hour < 11 ? "早上" : hour < 14 ? "中午" : hour < 18 ? "下午" : "晚上";
  return `${period}好，${state.profile.displayName}`;
}

function updateProfileUi() {
  document.querySelector("#profileName").textContent = state.profile.displayName;
  document.querySelector("#profileWorkspace").textContent = state.profile.workspaceName;
  document.querySelector("#profileAvatar").textContent = profileInitial(state.profile.displayName);
  document.querySelector("#greeting").textContent = greetingText();
}

function openProfile() {
  if (!state.apiReady) return showToast("请先启动本地数据服务", true);
  document.querySelector("#profileDisplayName").value = state.profile.displayName;
  document.querySelector("#profileWorkspaceName").value = state.profile.workspaceName;
  document.querySelector("#profilePreviewName").textContent = state.profile.displayName;
  document.querySelector("#profilePreviewAvatar").textContent = profileInitial(state.profile.displayName);
  document.querySelector("#profileDialog").showModal();
  setTimeout(() => document.querySelector("#profileDisplayName").focus(), 60);
}

const views = {
  today: () => `
    <div class="page-heading">
      <div><span class="micro-label">YOUR PERSONAL OS · 01</span><h1>把生活，过得更有<span class="accent-word">序</span></h1></div>
      <p>钱、项目和想法在同一张桌面上流动。今天只处理真正重要的事。</p>
    </div>
    <div class="dashboard-grid">
      <article class="card balance-card">
        <div class="card-top"><span class="card-kicker">可用净资产</span><button class="period-select">本月⌄</button></div>
        <div class="balance-number"><small>¥</small>${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(state.summary.netWorth)}</div>
        <div class="balance-change"><strong>${state.summary.income || state.summary.expense ? `↗ ${state.summary.net >= 0 ? "正向" : "承压"}` : "从 0 开始"}</strong> 本月净结余 ${formatMoney(state.summary.net)}</div>
        <div class="sparkline">
          <svg viewBox="0 0 600 100" preserveAspectRatio="none">
            <defs><linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".7"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>
            <path class="area" d="M0,75 C50,74 55,45 110,52 S180,78 230,60 S315,20 360,37 S440,76 485,42 S550,29 600,7 L600,100 L0,100Z"/>
            <path class="line" d="M0,75 C50,74 55,45 110,52 S180,78 230,60 S315,20 360,37 S440,76 485,42 S550,29 600,7"/>
            <circle class="dot" cx="600" cy="7" r="5"/>
          </svg>
        </div>
      </article>
      <article class="card day-card">
        <div class="card-top"><span class="card-kicker">今日焦点</span><div class="focus-actions"><button class="text-button" data-go="plan">查看计划</button><button class="text-button" id="addTask">＋ 添加任务</button><button class="receipt-trigger" id="openReceipt">生成小票 ↗</button></div></div>
        <div class="task-progress"><strong>${todayTasks().filter(task => task.completedAt).length}/${todayTasks().length}</strong><span>件已完成</span></div>
        <div class="task-list">${todayTasks().length ? renderTasks() : '<div class="empty-state dark-empty">今天还没有任务。先记录一件最重要的事吧。</div>'}</div>
      </article>
      <div class="lower-grid">
        <article class="card mini-card">
          <div class="mini-card-head"><div><span class="micro-label">CASH FLOW</span><h3>本月收支</h3></div><button class="text-button" data-go="finance">详情 →</button></div>
          <div class="money-split"><div class="income"><span>收入</span><strong>${formatMoney(state.summary.income)}</strong></div><div class="expense"><span>支出</span><strong>${formatMoney(state.summary.expense)}</strong></div></div>
          <div class="budget-bar"><i style="width:${budgetPercent()}%"></i></div><div class="budget-meta"><span>预算使用 ${budgetPercent()}%</span><span>${budgetRemaining() >= 0 ? "剩余" : "已超出"} ${formatMoney(Math.abs(budgetRemaining()))}</span></div>
        </article>
        <article class="card mini-card">
          <div class="mini-card-head"><div><span class="micro-label">IN MOTION</span><h3>推进中的项目</h3></div><button class="text-button" data-go="projects">全部 →</button></div>
          ${renderProjectSnapshot()}
        </article>
        <article class="card mini-card">
          <div class="mini-card-head"><div><span class="micro-label">NEXT TO PUBLISH</span><h3>下一篇内容</h3></div><button class="text-button" data-go="content">管线 →</button></div>
          ${renderContentSnapshot()}
        </article>
      </div>
      <section class="cat-dock" aria-label="今日快捷入口">
        <button class="cat-sticker" type="button" data-cat-action="capture" aria-label="捕捉灵感，打开快速记录"><img src="assets/cats/camera-cat.png" alt=""><span class="cat-card-footer"><strong>捕捉灵感</strong><span>快速记录 · CAPTURE</span></span></button>
        <button class="cat-sticker" type="button" data-cat-action="reading" aria-label="深度阅读，进入内容工作区"><img src="assets/cats/reading-cat.png" alt=""><span class="cat-card-footer"><strong>深度阅读</strong><span>内容工作区 · READ</span></span></button>
        <button class="cat-sticker" type="button" data-cat-action="focus" aria-label="稳定推进，添加今日任务"><img src="assets/cats/seated-cat.png" alt=""><span class="cat-card-footer"><strong>稳定推进</strong><span>添加任务 · FOCUS</span></span></button>
        <button class="cat-sticker" type="button" data-cat-action="receipt" aria-label="今日放空，生成每日小票"><img src="assets/cats/coffee-cat.png" alt=""><span class="cat-card-footer"><strong>今日放空</strong><span>生成小票 · REST</span></span></button>
      </section>
    </div>`,

  plan: () => {
    const groups = planGroups();
    const openCount = groups.overdue.length + groups.today.length + groups.tomorrow.length + groups.week.length + groups.later.length;
    return `
    <div class="page-heading"><div><span class="micro-label">PLANNER · 02</span><h1>提前安排，到了当天<span class="accent-word">就做</span></h1></div><div class="page-heading-tools"><p>明天和未来的任务会立即保存在这里，到计划日期再进入“今日焦点”。</p><button class="primary-button" id="addPlanTask">＋ 添加计划</button></div></div>
    <div class="metric-row plan-metrics"><div class="metric"><span>待完成计划</span><strong>${openCount}</strong><small>所有未来与逾期任务</small></div><div class="metric"><span>今天</span><strong>${groups.today.length}</strong><small>${groups.overdue.length ? `另有 ${groups.overdue.length} 件已逾期` : "没有逾期任务"}</small></div><div class="metric"><span>明天</span><strong>${groups.tomorrow.length}</strong><small>可以提前安排和修改</small></div><div class="metric"><span>已完成</span><strong>${groups.completed.length}</strong><small>保留完成时间与记录</small></div></div>
    <div class="plan-board">
      ${renderPlanSection("已逾期", "OVERDUE", groups.overdue, "overdue")}
      ${renderPlanSection("今天", "TODAY", groups.today, "today")}
      ${renderPlanSection("明天", "TOMORROW", groups.tomorrow, "tomorrow")}
      ${renderPlanSection("未来7天", "NEXT 7 DAYS", groups.week, "week")}
      ${renderPlanSection("更晚", "LATER", groups.later, "later")}
      ${renderPlanSection("已完成", "COMPLETED", groups.completed.slice(0, 30), "completed")}
    </div>`;
  },

  finance: () => `
    <div class="page-heading"><div><span class="micro-label">MONEY DESK · 03</span><h1>看清每一笔钱的<span class="accent-word">去向</span></h1></div><p>不只记账，更要知道什么在赚钱，什么正在消耗你的自由。</p></div>
    <div class="metric-row finance-metrics"><div class="metric"><span>本月收入</span><strong>${formatMoney(state.summary.income)}</strong><small>收入支持随时手动添加</small></div><div class="metric"><span>本月支出</span><strong>${formatMoney(state.summary.expense)}</strong><small>预算使用 · ${budgetPercent()}%</small></div><div class="metric"><span>本月预算</span><strong>${formatMoney(state.summary.budget)}</strong><small>点击下方按钮可修改</small></div><div class="metric ${budgetRemaining() < 0 ? "metric-over" : ""}"><span>${budgetRemaining() >= 0 ? "预算剩余" : "预算超出"}</span><strong>${formatMoney(Math.abs(budgetRemaining()))}</strong><small>会随每日支出自动递减</small></div></div>
    <div class="section-layout finance-layout">
      <article class="card section-card"><div class="mini-card-head"><div><span class="micro-label">GROUPED FLOW</span><h3>分类流水</h3><p class="section-hint">先看每类总额，点击分类展开具体支出。</p></div><div class="button-group"><button class="secondary-button" id="importTransactions">导入 CSV</button><button class="income-button" id="addIncome">＋ 记收入</button><button class="primary-button" id="addExpense">＋ 记支出</button></div></div><div class="transaction-list transaction-groups">${renderTransactions()}</div></article>
      <article class="card section-card"><div class="mini-card-head"><div><span class="micro-label">MONTHLY BUDGET</span><h3>本月预算与支出构成</h3></div><button class="secondary-button" id="editBudget">修改预算</button></div><div class="budget-overview"><div><span>本月预算</span><strong>${formatMoney(state.summary.budget)}</strong></div><div><span>${budgetRemaining() >= 0 ? "还能支出" : "已经超出"}</span><strong>${formatMoney(Math.abs(budgetRemaining()))}</strong></div></div><div class="budget-bar budget-bar-large"><i style="width:${budgetPercent()}%"></i></div>${renderBreakdown()}</article>
    </div>
    <article class="card section-card category-budget-card"><div class="mini-card-head"><div><span class="micro-label">CATEGORY ENVELOPES</span><h3>分类预算</h3><p class="section-hint">饮食、工作和其他必要开支各有自己的额度，流水会自动扣减。</p></div><button class="secondary-button" id="editCategoryBudget">设置分类预算</button></div>${renderCategoryBudgets()}</article>`,

  projects: () => `
    <div class="page-heading"><div><span class="micro-label">PROJECT ROOM · 04</span><h1>让项目持续<span class="accent-word">向前</span></h1></div><div class="page-heading-tools"><p>进度、投入和回报放在一起，避免用忙碌掩盖真正的停滞。</p><button class="primary-button" id="addProject">＋ 添加项目</button></div></div>
    <div class="kanban">
      ${renderProjectColumn("待开始", "todo")}
      ${renderProjectColumn("进行中", "doing")}
      ${renderProjectColumn("待确认", "review")}
    </div>`,

  content: () => `
    <div class="page-heading"><div><span class="micro-label">CONTENT STUDIO · 05</span><h1>从灵感，到<span class="accent-word">作品</span></h1></div><div class="page-heading-tools"><p>让选题、素材、制作和数据复盘形成稳定管线，而不是追着热点奔跑。</p><div class="button-group"><button class="secondary-button return-today" data-go="today">← 返回今日</button><button class="primary-button" id="addContent">＋ 添加内容</button></div></div></div>
    <div class="kanban content-kanban">
      ${renderContentColumn("灵感池", "idea")}
      ${renderContentColumn("制作中", "creating")}
      ${renderContentColumn("待发布", "ready")}
      ${renderContentColumn("已发布", "published")}
    </div>`,

  exercise: () => `
    <div class="page-heading exercise-heading"><div><span class="micro-label">MOVE LOG · 06</span><h1>每天动一点，身体会<span class="accent-word">记得</span></h1></div><div class="page-heading-tools"><p>记录今天主要做了什么，让运动变成看得见的长期积累。</p><button class="primary-button" id="addExercise">＋ 今日运动打卡</button></div></div>
    ${renderExerciseDashboard()}`,

  inbox: () => `
    <div class="page-heading"><div><span class="micro-label">UNIVERSAL INBOX · 07</span><h1>所有碎片，先放<span class="accent-word">这里</span></h1></div><p>文字、语音、图片和链接都会保留原始来源，再由 AI 提取下一步行动。</p></div>
    <article class="card section-card"><div class="mini-card-head"><div><span class="micro-label">NEEDS REVIEW</span><h3>等待你确认 · ${activeInboxItems().length}</h3></div><button class="primary-button" id="inboxCapture">＋ 添加</button></div><div class="inbox-list">${renderInbox()}</div></article>
    <article class="card section-card note-archive"><div class="mini-card-head"><div><span class="micro-label">NOTE ARCHIVE</span><h3>已整理笔记 · ${state.notes.length}</h3></div></div>${renderNotes()}</article>`,

  settings: () => `
    <div class="page-heading"><div><span class="micro-label">SYSTEM · 08</span><h1>按照你的方式<span class="accent-word">运转</span></h1></div><p>所有数据默认留在本地。自动化可以建议，但重要操作永远由你确认。</p></div>
    <div class="metric-row"><div class="metric"><span>数据位置</span><strong style="font-size:20px">本地 SQLite</strong><small>${state.apiReady ? "连接正常 · 持久保存" : "等待连接"}</small></div><div class="metric"><span>账户数量</span><strong>${state.accounts.length}</strong><small>${state.accounts.map(account => escapeHtml(account.name)).join(" · ")}</small></div><div class="metric"><span>真实流水</span><strong>${state.transactions.length}</strong><small>支持新增、编辑、删除和导入</small></div></div>
    <div class="settings-connectors">
      <article class="card section-card mobile-access-card"><div><span class="micro-label">PHONE COMPANION</span><h3>${state.clientLocal ? "同一 Wi-Fi 手机访问" : "正在通过手机访问"}</h3><p>${state.clientLocal ? "用手机扫码，就能添加任务、记录财务和运动打卡。手机与电脑共用同一份数据，打开页面时约 8 秒自动同步。Mac 需保持开机和运行。" : "当前数据仍保存在 Mac 上，手机和电脑页面会自动检查更新。关闭 Mac 的启动终端后，手机访问会同步结束。"}</p></div>${state.clientLocal ? '<button class="primary-button" id="openMobileAccess">显示二维码和访问码 <span>→</span></button>' : '<span class="mobile-connected-badge">已安全连接 · 自动同步</span>'}</article>
      <article class="card section-card wechat-access-card"><div><span class="micro-label">WECHAT → CODEX</span><h3>微信里的 Codex 助手</h3><p>${state.wechatStatus.configured ? `你发给测试公众号的文字会先进入收件箱，再由 ${state.wechatStatus.processor === "codex" ? "Codex" : "DeepSeek"} 理解整理。已接收 ${state.wechatStatus.receivedCount} 条${state.wechatStatus.lastReceivedAt ? `，最近一次 ${formatDateTime(state.wechatStatus.lastReceivedAt)}` : ""}。` : "通过微信公众号测试号给 Codex 发消息，让它替你整理到工作台。双击“配置微信接入.command”即可开始配置。"}</p><small>${state.wechatStatus.configured ? `${state.wechatStatus.autoClassify ? `${state.wechatStatus.processor === "codex" ? "Codex" : "DeepSeek"} 自动整理已开启` : "当前使用手动整理"} · ${state.wechatStatus.allowedOpenIds ? `只允许 ${state.wechatStatus.allowedOpenIds} 个微信` : "建议设置微信白名单"}` : `本机 ${state.wechatStatus.codexAvailable ? "已找到 Codex" : "尚未找到 Codex"} · 还需要公众号测试号和 HTTPS 中转`}</small></div><span class="connector-status ${state.wechatStatus.configured ? "connected" : ""}">${state.wechatStatus.configured ? "已配置" : "等待配置"}</span></article>
    </div>`,
};

function formatDateTime(value) {
  const parsed = new Date(`${String(value).replace(" ", "T")}Z`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(parsed);
}

function renderTasks() {
  return todayTasks().map(task => `<div class="task-row ${task.completedAt ? "done" : ""}" data-task="${task.id}"><button class="task-check" aria-label="${task.completedAt ? "恢复" : "完成"}任务">✓</button><span class="task-copy">${escapeHtml(task.title)}</span><span class="task-time">${task.completedAt ? formatClock(task.completedAt) : "待完成"}</span><button class="task-edit" data-edit-task="${task.id}" aria-label="编辑任务">•••</button></div>`).join("");
}

function formatPlanDate(value) {
  if (value === todayIso) return "今天";
  if (value === isoDateOffset(1)) return "明天";
  const target = new Date(`${value}T12:00:00`);
  return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", weekday: "short" }).format(target);
}

function renderPlanSection(title, eyebrow, tasks, tone) {
  const cards = tasks.length ? tasks.map(task => `
    <div class="plan-task ${task.completedAt ? "done" : ""}" data-task="${task.id}">
      <button class="task-check" aria-label="${task.completedAt ? "恢复" : "完成"}任务">✓</button>
      <div class="plan-task-copy"><strong>${escapeHtml(task.title)}</strong><small>${formatPlanDate(task.dueDate)}${task.completedAt ? ` · ${formatClock(task.completedAt)} 完成` : " · 计划任务"}</small></div>
      <span class="plan-date">${task.dueDate.slice(5).replace("-", ".")}</span>
      <button class="task-edit" data-edit-task="${task.id}" aria-label="编辑任务">•••</button>
    </div>`).join("") : '<div class="empty-state plan-empty">这里暂时没有任务</div>';
  return `<section class="card section-card plan-section plan-${tone}"><div class="mini-card-head"><div><span class="micro-label">${eyebrow}</span><h3>${title}</h3></div><b class="plan-count">${tasks.length}</b></div><div class="plan-list">${cards}</div></section>`;
}

function transactionLabel(transaction) {
  return transaction.note || transaction.counterparty || transaction.category;
}

function renderTransactions() {
  if (!state.transactions.length) return '<div class="empty-state">还没有流水，点击“记一笔”开始。</div>';
  const groups = new Map();
  state.transactions.forEach(transaction => {
    const key = `${transaction.kind}-${transaction.categoryId}`;
    if (!groups.has(key)) groups.set(key, { key, kind: transaction.kind, name: transaction.category, color: transaction.color, total: 0, items: [] });
    const group = groups.get(key);
    group.total += Number(transaction.amount);
    group.items.push(transaction);
  });
  return [...groups.values()].map(group => {
    const expanded = state.expandedTransactionGroups.has(group.key);
    const newest = group.items[0]?.date?.slice(5) || "";
    const rows = group.items.map(transaction => `
    <div class="transaction">
      <span class="transaction-icon" style="background:${transaction.color}20">${transaction.kind === "income" ? "↙" : "↗"}</span>
      <div><strong>${escapeHtml(transactionLabel(transaction))}</strong><small>${escapeHtml(transaction.category)} · ${escapeHtml(transaction.account)} · ${transaction.date.slice(5)}</small></div>
      <span class="transaction-amount ${transaction.kind === "income" ? "positive" : ""}">${transaction.kind === "income" ? "+ " : "- "}${formatMoney(transaction.amount)}</span>
      <button class="transaction-action" data-edit-transaction="${transaction.id}" aria-label="编辑 ${escapeHtml(transactionLabel(transaction))}">•••</button>
    </div>`).join("");
    return `<section class="transaction-group ${expanded ? "expanded" : ""}">
      <button class="transaction-group-head" type="button" data-transaction-group="${group.key}" aria-expanded="${expanded}">
        <span class="transaction-group-icon" style="--group-color:${group.color}">${group.kind === "income" ? "↙" : "↗"}</span>
        <span class="transaction-group-copy"><strong>${escapeHtml(group.name)}</strong><small>${group.items.length} 笔 · 最近 ${newest}</small></span>
        <span class="transaction-group-total ${group.kind === "income" ? "positive" : ""}">${group.kind === "income" ? "+ " : "- "}${formatMoney(group.total)}</span>
        <span class="transaction-group-chevron">⌄</span>
      </button>
      <div class="transaction-group-details">${rows}</div>
    </section>`;
  }).join("");
}

function renderCategoryBudgets() {
  const items = state.summary.categoryBudgets || [];
  if (!items.length) return '<div class="empty-state">还没有可用的支出分类。</div>';
  return `<div class="category-budget-summary"><span>已分配 <b>${formatMoney(state.summary.allocatedBudget)}</b></span><span class="${state.summary.unallocatedBudget < 0 ? "over" : ""}">${state.summary.unallocatedBudget >= 0 ? "尚未分配" : "超出总预算"} <b>${formatMoney(Math.abs(state.summary.unallocatedBudget))}</b></span></div>
    <div class="category-budget-grid">${items.map(item => {
      const remaining = item.remaining;
      const isOver = item.configured && remaining < 0;
      return `<article class="category-budget-item ${isOver ? "over" : ""}">
        <div class="category-budget-head"><span><i style="background:${item.color}"></i>${escapeHtml(item.name)}</span><strong>${item.configured ? formatMoney(item.budget) : "待设置"}</strong></div>
        <div class="budget-bar"><i style="width:${item.percent || 0}%;background:${item.color}"></i></div>
        <div class="category-budget-foot"><span>已支出 ${formatMoney(item.spent)}</span><span>${item.configured ? `${remaining >= 0 ? "剩余" : "超出"} ${formatMoney(Math.abs(remaining))}` : "点击设置预算"}</span></div>
      </article>`;
    }).join("")}</div>`;
}

function renderCategoryBudgetInputs() {
  return (state.summary.categoryBudgets || []).map(item => `<label class="category-budget-input"><span><i style="background:${item.color}"></i>${escapeHtml(item.name)}</span><div><b>¥</b><input type="number" min="0" step="0.01" placeholder="暂不设置" data-category-budget="${item.categoryId}" value="${item.configured ? item.budget : ""}" /></div></label>`).join("");
}

function renderBreakdown() {
  const breakdown = state.summary.breakdown || [];
  const total = breakdown.reduce((sum, item) => sum + item.amount, 0);
  if (!total) return '<div class="empty-state">本月还没有支出数据。</div>';
  let cursor = 0;
  const segments = breakdown.map(item => {
    const start = cursor;
    cursor += (item.amount / total) * 100;
    return `${item.color} ${start.toFixed(1)}% ${cursor.toFixed(1)}%`;
  }).join(", ");
  return `<div class="donut-wrap"><div class="donut" data-label="${budgetRemaining() >= 0 ? `${100 - budgetPercent()}%\n预算剩余` : "预算\n已超出"}" style="background:conic-gradient(${segments})"></div></div><div class="legend">${breakdown.slice(0, 6).map(item => `<div><i style="background:${item.color}"></i><span>${escapeHtml(item.name)}</span><b>${Math.round((item.amount / total) * 100)}%</b></div>`).join("")}</div>`;
}

function kanbanColumn(title, cards) {
  return `<section class="kanban-column"><div class="kanban-head"><span>${title}</span><b>${cards.length}</b></div>${cards.length ? cards.map(card => `<article class="kanban-card"><span class="tag">${card.tag}</span><h4>${card.title}</h4><footer><span>${card.meta}</span><span>•••</span></footer></article>`).join("") : '<div class="empty-state kanban-empty">这里还是空的</div>'}</section>`;
}

function renderProjectColumn(title, status) {
  const projects = state.projects.filter(project => project.status === status);
  return `<section class="kanban-column"><div class="kanban-head"><span>${title}</span><b>${projects.length}</b></div>${projects.length ? projects.map(project => `
    <button type="button" class="kanban-card project-card" data-edit-project="${project.id}">
      <span class="tag">${status === "todo" ? "待开始" : status === "doing" ? "进行中" : "待确认"}</span>
      <h4>${escapeHtml(project.title)}</h4>
      <p>${escapeHtml(project.description || "点击补充项目说明")}</p>
      <footer><span>本地项目</span><span>编辑 →</span></footer>
    </button>`).join("") : '<div class="empty-state kanban-empty">这里还是空的</div>'}</section>`;
}

function renderProjectSnapshot() {
  const items = [...state.projects].sort((a, b) => ({ doing: 0, todo: 1, review: 2 }[a.status] - ({ doing: 0, todo: 1, review: 2 }[b.status]))).slice(0, 3);
  if (!items.length) return '<div class="project-stack empty-stack"><div class="empty-state">还没有项目，去项目页创建第一个。</div></div>';
  const labels = { todo: "待开始", doing: "进行中", review: "待确认" };
  return `<div class="project-stack">${items.map(item => `<button class="project-slip" data-go="projects"><i></i><span>${escapeHtml(item.title)}</span><b>${labels[item.status]}</b></button>`).join("")}</div>`;
}

function renderContentSnapshot() {
  const item = state.contentItems.find(entry => entry.status === "ready") || state.contentItems.find(entry => entry.status === "creating") || state.contentItems[0];
  if (!item) return '<div class="content-feature empty-feature"><div class="empty-state">还没有待发布内容。灵感来了就先扔进收件箱。</div></div>';
  const labels = { idea: "灵感池", creating: "制作中", ready: "待发布", published: "已发布" };
  return `<button class="content-feature content-snapshot" data-go="content"><span class="content-paper"></span><span class="content-paper yellow"></span><span class="content-meta"><strong>${escapeHtml(item.title)}</strong><span>${labels[item.status]}</span></span></button>`;
}

function renderContentColumn(title, status) {
  const items = state.contentItems.filter(item => item.status === status);
  const labels = { idea: "灵感", creating: "制作中", ready: "待发布", published: "已发布" };
  return `<section class="kanban-column"><div class="kanban-head"><span>${title}</span><b>${items.length}</b></div>${items.length ? items.map(item => `
    <button type="button" class="kanban-card project-card" data-edit-content="${item.id}">
      <span class="tag">${labels[status]}</span><h4>${escapeHtml(item.title)}</h4>
      <p>${escapeHtml(item.description || "点击补充内容说明")}</p>
      <footer><span>内容管线</span><span>编辑 →</span></footer>
    </button>`).join("") : '<div class="empty-state kanban-empty">这里还是空的</div>'}</section>`;
}

function currentMonthExercise() {
  const month = todayIso.slice(0, 7);
  return state.exerciseCheckins.filter(item => item.date.startsWith(month));
}

function exerciseStreak() {
  const dates = new Set(state.exerciseCheckins.map(item => item.date));
  let cursor = new Date(`${todayIso}T12:00:00`);
  if (!dates.has(todayIso)) cursor.setDate(cursor.getDate() - 1);
  let streak = 0;
  while (dates.has(localIsoDate(cursor))) {
    streak += 1;
    cursor.setDate(cursor.getDate() - 1);
  }
  return streak;
}

function renderExerciseDashboard() {
  const monthItems = currentMonthExercise();
  const monthMap = new Map(monthItems.map(item => [item.date, item]));
  const now = new Date(`${todayIso}T12:00:00`);
  const year = now.getFullYear();
  const monthIndex = now.getMonth();
  const days = new Date(year, monthIndex + 1, 0).getDate();
  const leading = (new Date(year, monthIndex, 1).getDay() + 6) % 7;
  const cells = Array.from({ length: leading }, () => '<span class="exercise-day is-blank"></span>');
  for (let day = 1; day <= days; day += 1) {
    const dateKey = `${year}-${String(monthIndex + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const item = monthMap.get(dateKey);
    cells.push(`<button class="exercise-day ${item ? "is-checked" : ""} ${dateKey === todayIso ? "is-today" : ""}" data-exercise-date="${dateKey}" ${dateKey > todayIso ? "disabled" : ""}><span>${day}</span>${item ? `<i>✓</i><small>${escapeHtml(item.activity)}</small>` : ""}</button>`);
  }
  const minutes = monthItems.reduce((sum, item) => sum + Number(item.durationMinutes || 0), 0);
  const recent = state.exerciseCheckins.slice(0, 6);
  return `<section class="exercise-hero card"><div class="exercise-hero-copy"><span class="micro-label">${year} / ${String(monthIndex + 1).padStart(2, "0")} MONTHLY BOARD</span><h2>本月运动打卡看板</h2><p>点日历中的日期就能打卡或修改当天记录。</p><div class="exercise-stats"><div><strong>${monthItems.length}</strong><span>本月打卡</span></div><div><strong>${minutes}</strong><span>运动分钟</span></div><div><strong>${exerciseStreak()}</strong><span>连续天数</span></div></div></div><div class="exercise-cat-wrap"><span class="exercise-sun"></span><img src="assets/cats/exercise-cat.png" alt="黑猫运动插画" /></div></section>
    <div class="exercise-layout"><article class="card section-card exercise-calendar-card"><div class="mini-card-head"><div><span class="micro-label">CHECK-IN CALENDAR</span><h3>${year} 年 ${monthIndex + 1} 月</h3></div><span class="exercise-count">${monthItems.length} DAYS</span></div><div class="exercise-weekdays">${["一", "二", "三", "四", "五", "六", "日"].map(day => `<span>${day}</span>`).join("")}</div><div class="exercise-calendar">${cells.join("")}</div></article>
    <article class="card section-card exercise-recent"><div class="mini-card-head"><div><span class="micro-label">RECENT MOVES</span><h3>最近运动</h3></div></div>${recent.length ? recent.map(item => `<button class="exercise-record" data-edit-exercise="${item.id}"><time>${item.date.slice(5).replace("-", ".")}</time><div><strong>${escapeHtml(item.activity)}</strong><small>${item.durationMinutes ? `${item.durationMinutes} 分钟` : "已完成打卡"}${item.note ? ` · ${escapeHtml(item.note)}` : ""}</small></div><span>编辑 →</span></button>`).join("") : '<div class="empty-state">还没有运动记录，今天从轻轻动一下开始。</div>'}</article></div>`;
}

function renderNotes() {
  if (!state.notes.length) return '<div class="empty-state inbox-empty">还没有归档笔记。</div>';
  return `<div class="note-grid">${state.notes.map(note => `<article class="note-card"><span>NOTE</span><h4>${escapeHtml(note.title)}</h4><p>${escapeHtml(note.body)}</p><time>${escapeHtml(note.createdAt?.slice(0, 10) || "")}</time></article>`).join("")}</div>`;
}

function renderInbox() {
  const items = activeInboxItems();
  if (!items.length) return '<div class="empty-state inbox-empty">收件箱已经整理干净。新的想法、账目或待办，可以继续从“快速记录”放进来。</div>';
  const typeLabels = { task: "今日任务", transaction: "财务记录", content: "内容灵感", project: "项目事项", note: "普通笔记" };
  return items.map(item => {
    const analysis = item.analysis || {};
    const ready = item.status === "review" && analysis.type;
    const suggestion = ready
      ? `DeepSeek 建议：${typeLabels[analysis.type] || "普通笔记"}${analysis.title ? ` · ${escapeHtml(analysis.title)}` : ""}${analysis.dueDate ? ` · ${escapeHtml(analysis.dueDate)}` : ""}`
      : "已保存到本地 · 等待 AI 分析";
    const primaryAction = analysis.type === "transaction"
      ? `<button class="confirm-inbox" data-complete-transaction="${item.id}">补充并入账</button>`
      : `<button class="confirm-inbox" data-confirm-inbox="${item.id}">确认分类</button>`;
    const actions = ready
      ? `${primaryAction}<button class="manual-inbox" data-manual-inbox="${item.id}">修改分类</button>`
      : `<button class="confirm-inbox" data-classify-inbox="${item.id}">AI 分析</button><button class="manual-inbox" data-manual-inbox="${item.id}">手动整理</button>`;
    return `<div class="inbox-row"><span class="inbox-type">${ready ? "AI" : "✦"}</span><div><h4>${escapeHtml(item.rawText)}</h4><p>${suggestion}</p></div><div class="inbox-actions">${actions}</div></div>`;
  }).join("");
}

function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach(node => { node.innerHTML = icons[node.dataset.icon] || ""; });
}

function render(view = state.view, { syncHistory = true } = {}) {
  const allowedViews = new Set(Object.keys(views));
  view = allowedViews.has(view) ? view : "today";
  state.view = view;
  if (syncHistory && window.location.hash !== `#${view}`) history.pushState({ view }, "", `#${view}`);
  const root = document.querySelector("#viewRoot");
  root.innerHTML = (views[view] || views.today)();
  root.classList.remove("view-root");
  void root.offsetWidth;
  root.classList.add("view-root");
  document.querySelectorAll("[data-view]").forEach(button => button.classList.toggle("active", button.dataset.view === view));
  bindViewEvents();
}

function bindViewEvents() {
  document.querySelectorAll("[data-go]").forEach(button => button.addEventListener("click", () => render(button.dataset.go)));
  document.querySelectorAll("[data-cat-action]").forEach(button => button.addEventListener("click", () => {
    const actions = {
      capture: openCapture,
      reading: () => render("content"),
      focus: openTask,
      receipt: openReceipt,
    };
    actions[button.dataset.catAction]?.();
  }));
  document.querySelectorAll(".task-check").forEach(button => button.addEventListener("click", async () => {
    const id = Number(button.closest("[data-task]").dataset.task);
    const task = state.tasks.find(item => item.id === id);
    button.disabled = true;
    try {
      await api(`/api/tasks/${id}`, { method: "PUT", body: JSON.stringify({ done: !task.completedAt }) });
      await loadData({ quiet: true });
      showToast(task.completedAt ? "任务已恢复" : "任务完成，已经记入今日小票");
    } catch (error) {
      button.disabled = false;
      showToast(error.message, true);
    }
  }));
  document.querySelector("#addTask")?.addEventListener("click", openTask);
  document.querySelector("#addPlanTask")?.addEventListener("click", () => openTask(null, isoDateOffset(1)));
  document.querySelectorAll("[data-edit-task]").forEach(button => button.addEventListener("click", () => openTask(Number(button.dataset.editTask))));
  document.querySelector("#openReceipt")?.addEventListener("click", openReceipt);
  document.querySelector("#addProject")?.addEventListener("click", () => openProject());
  document.querySelectorAll("[data-edit-project]").forEach(button => button.addEventListener("click", () => openProject(Number(button.dataset.editProject))));
  document.querySelector("#addContent")?.addEventListener("click", () => openContent());
  document.querySelectorAll("[data-edit-content]").forEach(button => button.addEventListener("click", () => openContent(Number(button.dataset.editContent))));
  document.querySelector("#addIncome")?.addEventListener("click", () => openTransaction(null, null, "income"));
  document.querySelector("#addExpense")?.addEventListener("click", () => openTransaction(null, null, "expense"));
  document.querySelector("#editBudget")?.addEventListener("click", openBudget);
  document.querySelector("#editCategoryBudget")?.addEventListener("click", openBudget);
  document.querySelectorAll("[data-transaction-group]").forEach(button => button.addEventListener("click", () => {
    const key = button.dataset.transactionGroup;
    if (state.expandedTransactionGroups.has(key)) state.expandedTransactionGroups.delete(key);
    else state.expandedTransactionGroups.add(key);
    render("finance", { syncHistory: false });
  }));
  document.querySelector("#addExercise")?.addEventListener("click", () => openExercise());
  document.querySelectorAll("[data-edit-exercise]").forEach(button => button.addEventListener("click", () => openExercise(Number(button.dataset.editExercise))));
  document.querySelectorAll("[data-exercise-date]").forEach(button => button.addEventListener("click", () => {
    const item = state.exerciseCheckins.find(entry => entry.date === button.dataset.exerciseDate);
    openExercise(item?.id || null, button.dataset.exerciseDate);
  }));
  document.querySelector("#importTransactions")?.addEventListener("click", () => document.querySelector("#importDialog").showModal());
  document.querySelector("#inboxCapture")?.addEventListener("click", openCapture);
  document.querySelector("#openMobileAccess")?.addEventListener("click", openMobileAccess);
  document.querySelectorAll("[data-edit-transaction]").forEach(button => button.addEventListener("click", () => openTransaction(Number(button.dataset.editTransaction))));
  document.querySelectorAll("[data-complete-transaction]").forEach(button => button.addEventListener("click", () => {
    const item = state.inbox.find(entry => entry.id === Number(button.dataset.completeTransaction));
    if (item) openTransaction(null, item);
  }));
  document.querySelectorAll("[data-manual-inbox]").forEach(button => button.addEventListener("click", () => openManualInbox(Number(button.dataset.manualInbox))));
  document.querySelectorAll("[data-confirm-inbox]").forEach(button => button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "正在归档…";
    try {
      const result = await api(`/api/inbox/${button.dataset.confirmInbox}/confirm`, { method: "POST", body: "{}" });
      await loadData({ quiet: true });
      const messages = { task: "已加入任务列表，收件箱同步清除", transaction: "已归类为财务记录", content: "已归类为内容灵感", project: "已归类为项目事项", note: "已整理为普通笔记" };
      showToast(messages[result.destination] || "收件箱记录已整理");
    } catch (error) {
      button.disabled = false;
      button.textContent = "确认分类";
      showToast(error.message, true);
    }
  }));
  document.querySelectorAll("[data-classify-inbox]").forEach(button => button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "AI 分析中…";
    try {
      await api(`/api/inbox/${button.dataset.classifyInbox}/classify`, { method: "POST", body: "{}" });
      await loadData({ quiet: true });
      showToast("DeepSeek 已给出分类建议");
    } catch (error) {
      button.disabled = false;
      button.textContent = "重新分析";
      showToast(error.message, true);
    }
  }));
}

function openManualInbox(id) {
  const item = state.inbox.find(entry => entry.id === id);
  if (!item) return;
  const analysis = item.analysis || {};
  state.pendingManualInboxId = id;
  document.querySelector("#manualInboxType").value = analysis.type || "task";
  document.querySelector("#manualInboxTitle").value = analysis.title || item.rawText;
  document.querySelector("#manualInboxDate").value = analysis.dueDate || todayIso;
  document.querySelector("#manualInboxDialog").showModal();
}

function openProject(id = null) {
  if (!state.apiReady) return showToast("请先启动本地数据服务", true);
  const project = id ? state.projects.find(item => item.id === id) : null;
  document.querySelector("#projectForm").reset();
  document.querySelector("#projectId").value = project?.id || "";
  document.querySelector("#projectDialogTitle").textContent = project ? "编辑项目" : "添加项目";
  document.querySelector("#projectTitle").value = project?.title || "";
  document.querySelector("#projectDescription").value = project?.description || "";
  document.querySelector("#projectStatus").value = project?.status || "todo";
  document.querySelector("#deleteProject").hidden = !project;
  document.querySelector("#projectDialog").showModal();
  setTimeout(() => document.querySelector("#projectTitle").focus(), 60);
}

function openContent(id = null) {
  if (!state.apiReady) return showToast("请先启动本地数据服务", true);
  const item = id ? state.contentItems.find(entry => entry.id === id) : null;
  document.querySelector("#contentForm").reset();
  document.querySelector("#contentId").value = item?.id || "";
  document.querySelector("#contentDialogTitle").textContent = item ? "编辑内容" : "添加内容";
  document.querySelector("#contentTitle").value = item?.title || "";
  document.querySelector("#contentDescription").value = item?.description || "";
  document.querySelector("#contentStatus").value = item?.status || "idea";
  document.querySelector("#deleteContent").hidden = !item;
  document.querySelector("#contentDialog").showModal();
  setTimeout(() => document.querySelector("#contentTitle").focus(), 60);
}

function openTask(id = null, preferredDate = todayIso) {
  if (!state.apiReady) return showToast("请先启动本地数据服务", true);
  const task = id ? state.tasks.find(item => item.id === id) : null;
  document.querySelector("#taskForm").reset();
  document.querySelector("#taskId").value = task?.id || "";
  document.querySelector("#taskDialogTitle").textContent = task ? "编辑任务" : preferredDate === todayIso ? "添加今日任务" : "添加未来计划";
  document.querySelector("#taskTitle").value = task?.title || "";
  document.querySelector("#taskDate").value = task?.dueDate || preferredDate;
  document.querySelector("#deleteTask").hidden = !task;
  document.querySelector("#taskDialog").showModal();
  setTimeout(() => document.querySelector("#taskTitle").focus(), 60);
}

function openBudget() {
  if (!state.apiReady) return showToast("请先启动本地数据服务", true);
  document.querySelector("#budgetMonth").value = state.summary.month || todayIso.slice(0, 7);
  document.querySelector("#budgetAmount").value = state.summary.budget;
  document.querySelector("#categoryBudgetFields").innerHTML = renderCategoryBudgetInputs();
  document.querySelector("#budgetDialog").showModal();
  setTimeout(() => document.querySelector("#budgetAmount").select(), 60);
}

function openExercise(id = null, preferredDate = todayIso) {
  if (!state.apiReady) return showToast("请先启动本地数据服务", true);
  const item = id ? state.exerciseCheckins.find(entry => entry.id === id) : null;
  document.querySelector("#exerciseForm").reset();
  document.querySelector("#exerciseId").value = item?.id || "";
  document.querySelector("#exerciseDialogTitle").textContent = item ? "修改运动打卡" : preferredDate === todayIso ? "今日运动打卡" : "补记运动打卡";
  document.querySelector("#exerciseDate").value = item?.date || preferredDate;
  document.querySelector("#exerciseActivity").value = item?.activity || "";
  document.querySelector("#exerciseDuration").value = item?.durationMinutes ?? "";
  document.querySelector("#exerciseNote").value = item?.note || "";
  document.querySelector("#deleteExercise").hidden = !item;
  document.querySelector("#exerciseDialog").showModal();
  setTimeout(() => document.querySelector("#exerciseActivity").focus(), 60);
}

function receiptData() {
  const completed = completedTodayTasks().sort((a, b) => a.completedAt.localeCompare(b.completedAt));
  const transactions = state.transactions.filter(item => item.date === todayIso);
  const income = transactions.filter(item => item.kind === "income").reduce((sum, item) => sum + Number(item.amount), 0);
  const expense = transactions.filter(item => item.kind === "expense").reduce((sum, item) => sum + Number(item.amount), 0);
  const captured = state.inbox.filter(item => item.createdAt?.slice(0, 10) === todayIso).length;
  const quotes = [
    "今天不是没有成果，只是还没有按下完成键。",
    "小步也算前进，今天留下了清楚的痕迹。",
    "做完比做满更重要，今天的节奏刚刚好。",
    "高产的一天，也别忘了给自己留一点空白。",
  ];
  const quote = completed.length === 0 ? quotes[0] : completed.length <= 2 ? quotes[1] : completed.length <= 5 ? quotes[2] : quotes[3];
  return {
    completed,
    first: formatClock(completed[0]?.completedAt),
    last: formatClock(completed.at(-1)?.completedAt),
    income,
    expense,
    captured,
    quote,
  };
}

function renderReceipt() {
  const data = receiptData();
  const dateLabel = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", weekday: "long" }).format(new Date(`${todayIso}T12:00:00`));
  document.querySelector("#dailyReceipt").innerHTML = `
    <header class="receipt-brand"><img src="assets/cats/coffee-cat.png" alt=""><h2>序 · 每日小票</h2><p>DAILY WORK RECEIPT</p></header>
    <div class="receipt-rule"></div>
    <div class="receipt-meta"><span>日期 DATE</span><strong>${escapeHtml(dateLabel)}</strong></div>
    <div class="receipt-meta"><span>首项 FIRST</span><strong>${data.first}</strong></div>
    <div class="receipt-meta"><span>末项 LAST</span><strong>${data.last}</strong></div>
    <div class="receipt-stat-grid">
      <div class="receipt-stat"><strong>${data.completed.length}</strong><span>完成任务 DONE</span></div>
      <div class="receipt-stat"><strong>${data.captured}</strong><span>捕捉灵感 CAPTURED</span></div>
    </div>
    <h3 class="receipt-section-title">TODAY'S COMPLETED ITEMS</h3>
    <div class="receipt-items">${data.completed.length ? data.completed.map(task => `<div class="receipt-item"><i>✓</i><span>${escapeHtml(task.title)}</span><time>${formatClock(task.completedAt)}</time></div>`).join("") : '<div class="receipt-empty">今天还没有已完成的任务</div>'}</div>
    <div class="receipt-rule"></div>
    <div class="receipt-total"><span>今日收入 INCOME</span><strong>${formatMoney(data.income)}</strong></div>
    <div class="receipt-total"><span>今日支出 EXPENSE</span><strong>${formatMoney(data.expense)}</strong></div>
    <p class="receipt-quote">“${escapeHtml(data.quote)}”</p>
    <footer class="receipt-code"><div class="receipt-bars"></div><small>XU-${todayIso.replaceAll("-", "")}-${String(data.completed.length).padStart(2, "0")}</small></footer>`;
}

function openReceipt() {
  renderReceipt();
  document.querySelector("#receiptDialog").showModal();
}

function wrapCanvasText(context, text, maxWidth) {
  const lines = [];
  let line = "";
  for (const character of text) {
    if (context.measureText(line + character).width > maxWidth && line) {
      lines.push(line);
      line = character;
    } else {
      line += character;
    }
  }
  if (line) lines.push(line);
  return lines;
}

async function downloadReceiptPng() {
  const data = receiptData();
  const itemLines = data.completed.flatMap(task => wrapCanvasTextForTask(task.title));
  const width = 720;
  const height = Math.max(1120, 930 + itemLines.length * 38);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  context.fillStyle = "#fffef8";
  context.fillRect(0, 0, width, height);
  context.fillStyle = "#111";
  context.textAlign = "center";
  context.font = '700 38px "PingFang SC", sans-serif';
  context.fillText("序 · 每日小票", width / 2, 80);
  context.font = '16px Menlo, monospace';
  context.fillText("DAILY WORK RECEIPT", width / 2, 115);
  context.textAlign = "left";
  context.font = '18px Menlo, "PingFang SC", monospace';
  let y = 165;
  const rule = () => { context.fillRect(55, y, width - 110, 2); y += 32; };
  const pair = (label, value) => { context.fillText(label, 55, y); context.textAlign = "right"; context.fillText(value, width - 55, y); context.textAlign = "left"; y += 36; };
  rule();
  pair("DATE", todayIso);
  pair("FIRST", data.first);
  pair("LAST", data.last);
  pair("COMPLETED", String(data.completed.length));
  pair("CAPTURED", String(data.captured));
  rule();
  context.font = '700 18px Menlo, "PingFang SC", monospace';
  context.fillText("TODAY'S COMPLETED ITEMS", 55, y);
  y += 42;
  context.font = '18px Menlo, "PingFang SC", monospace';
  if (!data.completed.length) {
    context.fillStyle = "#666";
    context.fillText("今天还没有已完成的任务", 55, y);
    context.fillStyle = "#111";
    y += 45;
  } else {
    data.completed.forEach(task => {
      const lines = wrapCanvasText(context, `✓ ${task.title}`, 490);
      lines.forEach((line, index) => {
        context.fillText(line, 55, y);
        if (index === 0) { context.textAlign = "right"; context.fillText(formatClock(task.completedAt), width - 55, y); context.textAlign = "left"; }
        y += 34;
      });
      y += 8;
    });
  }
  rule();
  pair("今日收入 INCOME", formatMoney(data.income));
  pair("今日支出 EXPENSE", formatMoney(data.expense));
  y += 10;
  context.textAlign = "center";
  context.font = '20px "PingFang SC", sans-serif';
  const quoteLines = wrapCanvasText(context, `“${data.quote}”`, width - 150);
  quoteLines.forEach(line => { context.fillText(line, width / 2, y); y += 34; });
  y += 34;
  for (let x = 110; x < width - 110; x += 10) context.fillRect(x, y, x % 30 === 0 ? 5 : 2, 58);
  context.font = '14px Menlo, monospace';
  context.fillText(`XU-${todayIso.replaceAll("-", "")}-${String(data.completed.length).padStart(2, "0")}`, width / 2, y + 88);
  const link = document.createElement("a");
  link.download = `序-每日小票-${todayIso}.png`;
  link.href = canvas.toDataURL("image/png");
  link.click();
  showToast("每日小票 PNG 已下载");

  function wrapCanvasTextForTask(title) {
    return String(title).match(/.{1,22}/g) || [""];
  }
}

function openCapture() {
  document.querySelector("#captureDialog").showModal();
  setTimeout(() => document.querySelector("#captureInput").focus(), 60);
}

function categoryOptions(kind, selectedId) {
  return state.categories.filter(category => category.kind === kind).map(category => `<option value="${category.id}" ${Number(selectedId) === category.id ? "selected" : ""}>${escapeHtml(category.name)}</option>`).join("");
}

function syncCategoryOptions(selectedId) {
  const kind = document.querySelector('input[name="kind"]:checked').value;
  document.querySelector("#transactionCategory").innerHTML = categoryOptions(kind, selectedId);
}

function openTransaction(id = null, inboxItem = null, defaultKind = "expense") {
  if (!state.apiReady) return showToast("请先启动本地数据服务", true);
  const transaction = id ? state.transactions.find(item => item.id === id) : null;
  state.pendingInboxTransactionId = inboxItem?.id || null;
  const suggestion = inboxItem?.analysis || {};
  document.querySelector("#transactionForm").reset();
  document.querySelector("#transactionId").value = transaction?.id || "";
  document.querySelector("#transactionTitle").textContent = transaction ? "编辑流水" : inboxItem ? "补充财务信息" : defaultKind === "income" ? "记录收入" : "记录支出";
  document.querySelector(`input[name="kind"][value="${transaction?.kind || suggestion.transactionKind || defaultKind}"]`).checked = true;
  syncCategoryOptions(transaction?.categoryId);
  document.querySelector("#transactionAmount").value = transaction?.amount || suggestion.amount || "";
  document.querySelector("#transactionDate").value = transaction?.date || suggestion.dueDate || todayIso;
  document.querySelector("#transactionAccount").innerHTML = state.accounts.map(account => `<option value="${account.id}" ${transaction?.accountId === account.id ? "selected" : ""}>${escapeHtml(account.name)}</option>`).join("");
  document.querySelector("#transactionProject").value = transaction?.project || "";
  document.querySelector("#transactionCounterparty").value = transaction?.counterparty || suggestion.counterparty || "";
  document.querySelector("#transactionNote").value = transaction?.note || inboxItem?.rawText || "";
  document.querySelector("#deleteTransaction").hidden = !transaction;
  document.querySelector("#transactionDialog").showModal();
  setTimeout(() => document.querySelector("#transactionAmount").focus(), 60);
}

function showToast(message, isError = false) {
  const toast = document.querySelector("#toast");
  toast.querySelector("span").textContent = isError ? "!" : "✓";
  toast.querySelector("p").textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 3000);
}

document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => render(button.dataset.view)));
window.addEventListener("popstate", () => render(window.location.hash.slice(1) || "today", { syncHistory: false }));
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") syncLinkedDevices(); });
window.setInterval(syncLinkedDevices, 8000);
document.querySelector("#openCapture").addEventListener("click", openCapture);
document.querySelector("#mobileCapture").addEventListener("click", openCapture);
document.querySelector("#openPhoneAccess").addEventListener("click", openMobileAccess);
document.querySelector("#editProfile").addEventListener("click", openProfile);
document.querySelector("#copyMobileUrl").addEventListener("click", () => copyText(document.querySelector("#mobileAccessUrl").value));
document.querySelector("#mobileLoginDialog").addEventListener("cancel", event => event.preventDefault());
document.querySelector("#mobileLoginCode").addEventListener("input", event => {
  const digits = event.target.value.replace(/\D/g, "").slice(0, 6);
  event.target.value = digits.length > 3 ? `${digits.slice(0, 3)} ${digits.slice(3)}` : digits;
});
document.querySelector("#mobileLoginForm").addEventListener("submit", async event => {
  event.preventDefault();
  const input = document.querySelector("#mobileLoginCode");
  try {
    await api("/api/mobile-login", { method: "POST", body: JSON.stringify({ code: input.value }) });
    document.querySelector("#mobileLoginDialog").close();
    input.value = "";
    await loadData();
    showToast("手机已连接到你的工作台");
  } catch (error) {
    showToast(error.message, true);
    input.select();
  }
});
document.querySelector(".search-trigger").addEventListener("click", () => document.querySelector("#searchDialog").showModal());
document.querySelectorAll("[data-close]").forEach(button => button.addEventListener("click", () => document.querySelector(`#${button.dataset.close}`).close()));
document.querySelectorAll("[data-example]").forEach(button => button.addEventListener("click", () => { document.querySelector("#captureInput").value = button.dataset.example; }));
document.querySelectorAll('input[name="kind"]').forEach(input => input.addEventListener("change", () => syncCategoryOptions()));

document.addEventListener("keydown", event => {
  if (event.key === "Escape" && state.view === "content" && !document.querySelector("dialog[open]")) render("today");
});

document.querySelector("#profileDisplayName").addEventListener("input", event => {
  const name = event.target.value.trim() || "序";
  document.querySelector("#profilePreviewName").textContent = name;
  document.querySelector("#profilePreviewAvatar").textContent = profileInitial(name);
});

document.querySelector("#profileForm").addEventListener("submit", async event => {
  event.preventDefault();
  const displayName = document.querySelector("#profileDisplayName").value.trim();
  const workspaceName = document.querySelector("#profileWorkspaceName").value.trim();
  try {
    await api("/api/profile", { method: "PUT", body: JSON.stringify({ displayName, workspaceName }) });
    state.profile = { displayName, workspaceName };
    updateProfileUi();
    document.querySelector("#profileDialog").close();
    showToast("个人资料已更新，问候语同步完成");
  } catch (error) {
    showToast(error.message, true);
  }
});

document.querySelector("#manualInboxForm").addEventListener("submit", async event => {
  event.preventDefault();
  const id = state.pendingManualInboxId;
  const item = state.inbox.find(entry => entry.id === id);
  if (!item) return;
  const type = document.querySelector("#manualInboxType").value;
  const title = document.querySelector("#manualInboxTitle").value.trim();
  const dueDate = document.querySelector("#manualInboxDate").value;
  document.querySelector("#manualInboxDialog").close();
  if (type === "transaction") {
    openTransaction(null, { ...item, analysis: { ...item.analysis, type, title, dueDate } });
    return;
  }
  try {
    await api(`/api/inbox/${id}/confirm`, { method: "POST", body: JSON.stringify({ type, title, dueDate }) });
    state.pendingManualInboxId = null;
    await loadData({ quiet: true });
    showToast("已按你的选择完成整理");
  } catch (error) {
    showToast(error.message, true);
  }
});

document.querySelector("#budgetForm").addEventListener("submit", async event => {
  event.preventDefault();
  const month = document.querySelector("#budgetMonth").value;
  const amount = Number(document.querySelector("#budgetAmount").value);
  const categoryBudgets = [...document.querySelectorAll("[data-category-budget]")].map(input => ({
    categoryId: Number(input.dataset.categoryBudget),
    amount: input.value === "" ? null : Number(input.value),
  }));
  try {
    await api("/api/budget", { method: "PUT", body: JSON.stringify({ month, amount, categoryBudgets }) });
    document.querySelector("#budgetDialog").close();
    await loadData({ quiet: true });
    showToast("总预算和分类预算已保存，剩余额度已重新计算");
  } catch (error) {
    showToast(error.message, true);
  }
});

document.querySelector("#exerciseForm").addEventListener("submit", async event => {
  event.preventDefault();
  const id = document.querySelector("#exerciseId").value;
  const payload = {
    date: document.querySelector("#exerciseDate").value,
    activity: document.querySelector("#exerciseActivity").value.trim(),
    durationMinutes: document.querySelector("#exerciseDuration").value,
    note: document.querySelector("#exerciseNote").value.trim(),
  };
  try {
    await api(id ? `/api/exercise/${id}` : "/api/exercise", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
    document.querySelector("#exerciseDialog").close();
    await loadData({ quiet: true });
    showToast(id ? "运动打卡已更新" : "运动打卡成功，月度看板亮了一格");
  } catch (error) {
    showToast(error.message, true);
  }
});

document.querySelector("#deleteExercise").addEventListener("click", async () => {
  const id = document.querySelector("#exerciseId").value;
  if (!id || !window.confirm("确定删除这次运动打卡吗？删除后无法恢复。")) return;
  try {
    await api(`/api/exercise/${id}`, { method: "DELETE" });
    document.querySelector("#exerciseDialog").close();
    await loadData({ quiet: true });
    showToast("运动打卡已删除");
  } catch (error) {
    showToast(error.message, true);
  }
});

document.querySelector("#projectForm").addEventListener("submit", async event => {
  event.preventDefault();
  const id = document.querySelector("#projectId").value;
  const payload = {
    title: document.querySelector("#projectTitle").value.trim(),
    description: document.querySelector("#projectDescription").value.trim(),
    status: document.querySelector("#projectStatus").value,
  };
  try {
    await api(id ? `/api/projects/${id}` : "/api/projects", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
    document.querySelector("#projectDialog").close();
    await loadData({ quiet: true });
    showToast(id ? "项目已更新" : "项目已添加到项目看板");
  } catch (error) {
    showToast(error.message, true);
  }
});

document.querySelector("#contentForm").addEventListener("submit", async event => {
  event.preventDefault();
  const id = document.querySelector("#contentId").value;
  const payload = {
    title: document.querySelector("#contentTitle").value.trim(),
    description: document.querySelector("#contentDescription").value.trim(),
    status: document.querySelector("#contentStatus").value,
  };
  try {
    await api(id ? `/api/content/${id}` : "/api/content", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
    document.querySelector("#contentDialog").close();
    await loadData({ quiet: true });
    showToast(id ? "内容已更新" : "内容已加入灵感池");
  } catch (error) {
    showToast(error.message, true);
  }
});

function requestEntityDelete(type, id, title, sourceDialog) {
  state.pendingDeleteEntity = { type, id: Number(id), title };
  document.querySelector(`#${sourceDialog}`).close();
  const labels = { task: "任务", project: "项目", content: "内容" };
  document.querySelector("#entityDeleteTitle").textContent = `要删除这个${labels[type]}吗？`;
  document.querySelector("#entityDeleteDescription").textContent = `“${title}”删除后无法恢复。`;
  document.querySelector("#entityDeleteDialog").showModal();
}

document.querySelector("#deleteTask").addEventListener("click", () => {
  const id = document.querySelector("#taskId").value;
  if (id) requestEntityDelete("task", id, document.querySelector("#taskTitle").value, "taskDialog");
});

document.querySelector("#deleteProject").addEventListener("click", () => {
  const id = document.querySelector("#projectId").value;
  if (id) requestEntityDelete("project", id, document.querySelector("#projectTitle").value, "projectDialog");
});

document.querySelector("#deleteContent").addEventListener("click", () => {
  const id = document.querySelector("#contentId").value;
  if (id) requestEntityDelete("content", id, document.querySelector("#contentTitle").value, "contentDialog");
});

document.querySelector("#confirmDeleteEntity").addEventListener("click", async () => {
  const entity = state.pendingDeleteEntity;
  if (!entity) return;
  const endpoints = { task: "tasks", project: "projects", content: "content" };
  try {
    await api(`/api/${endpoints[entity.type]}/${entity.id}`, { method: "DELETE" });
    document.querySelector("#entityDeleteDialog").close();
    state.pendingDeleteEntity = null;
    await loadData({ quiet: true });
    showToast("已删除");
  } catch (error) {
    showToast(error.message, true);
  }
});

document.querySelector("#taskForm").addEventListener("submit", async event => {
  event.preventDefault();
  const title = document.querySelector("#taskTitle").value.trim();
  const dueDate = document.querySelector("#taskDate").value;
  const id = document.querySelector("#taskId").value;
  if (!title || !dueDate) return;
  try {
    await api(id ? `/api/tasks/${id}` : "/api/tasks", { method: id ? "PUT" : "POST", body: JSON.stringify({ title, dueDate }) });
    document.querySelector("#taskDialog").close();
    await loadData({ quiet: true });
    showToast(id ? "任务已更新" : dueDate === todayIso ? "任务已加入今日焦点" : "任务已保存到计划日期");
  } catch (error) {
    showToast(error.message, true);
  }
});

document.querySelector("#printReceipt").addEventListener("click", () => window.print());
document.querySelector("#downloadReceipt").addEventListener("click", downloadReceiptPng);

document.querySelector("#captureForm").addEventListener("submit", async event => {
  event.preventDefault();
  const value = document.querySelector("#captureInput").value.trim();
  if (!value) return;
  try {
    const result = await api("/api/inbox", { method: "POST", body: JSON.stringify({ text: value }) });
    document.querySelector("#captureDialog").close();
    document.querySelector("#captureInput").value = "";
    await loadData({ quiet: true });
    showToast(result.warning ? `记录已保存；${result.warning}` : "记录成功，DeepSeek 已生成分类建议");
  } catch (error) {
    showToast(error.message, true);
  }
});

document.querySelector("#transactionForm").addEventListener("submit", async event => {
  event.preventDefault();
  const id = document.querySelector("#transactionId").value;
  const payload = {
    kind: document.querySelector('input[name="kind"]:checked').value,
    amount: Number(document.querySelector("#transactionAmount").value),
    date: document.querySelector("#transactionDate").value,
    categoryId: Number(document.querySelector("#transactionCategory").value),
    accountId: Number(document.querySelector("#transactionAccount").value),
    project: document.querySelector("#transactionProject").value,
    counterparty: document.querySelector("#transactionCounterparty").value,
    note: document.querySelector("#transactionNote").value,
  };
  try {
    const result = await api(id ? `/api/transactions/${id}` : "/api/transactions", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
    if (state.pendingInboxTransactionId && !id) {
      await api(`/api/inbox/${state.pendingInboxTransactionId}/confirm`, { method: "POST", body: JSON.stringify({ type: "transaction", destinationId: result.id }) });
      state.pendingInboxTransactionId = null;
    }
    document.querySelector("#transactionDialog").close();
    await loadData({ quiet: true });
    showToast(id ? "流水已更新" : "流水已保存，财务数据同步更新");
  } catch (error) {
    showToast(error.message, true);
  }
});

document.querySelector("#deleteTransaction").addEventListener("click", async () => {
  const id = document.querySelector("#transactionId").value;
  if (!id) return;
  state.pendingDeleteId = Number(id);
  document.querySelector("#transactionDialog").close();
  document.querySelector("#deleteDialog").showModal();
});

document.querySelector("#confirmDeleteTransaction").addEventListener("click", async () => {
  const id = state.pendingDeleteId;
  if (!id) return;
  try {
    await api(`/api/transactions/${id}`, { method: "DELETE" });
    document.querySelector("#deleteDialog").close();
    state.pendingDeleteId = null;
    await loadData({ quiet: true });
    showToast("流水已删除");
  } catch (error) {
    showToast(error.message, true);
  }
});

document.querySelector("#csvFile").addEventListener("change", event => {
  const file = event.target.files[0];
  const drop = document.querySelector("#fileDrop");
  drop.classList.toggle("has-file", Boolean(file));
  if (file) drop.querySelector("strong").textContent = file.name;
});

document.querySelector("#importForm").addEventListener("submit", async event => {
  event.preventDefault();
  const file = document.querySelector("#csvFile").files[0];
  if (!file) return showToast("请先选择 CSV 文件", true);
  try {
    const csvText = await file.text();
    const result = await api("/api/import", { method: "POST", body: JSON.stringify({ csv: csvText }) });
    document.querySelector("#importDialog").close();
    document.querySelector("#importForm").reset();
    document.querySelector("#fileDrop").classList.remove("has-file");
    document.querySelector("#fileDrop strong").textContent = "选择一个 CSV 文件";
    await loadData({ quiet: true });
    showToast(`已导入 ${result.imported} 笔流水${result.errors.length ? `，${result.errors.length} 行需要检查` : ""}`);
  } catch (error) {
    showToast(error.message, true);
  }
});

const now = new Date();
const weekday = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"][now.getDay()];
const months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
document.querySelector("#eyebrowDate").textContent = `${weekday} · ${String(now.getDate()).padStart(2, "0")} ${months[now.getMonth()]}`;
updateProfileUi();

hydrateIcons();
state.view = window.location.hash.slice(1) || "today";
render(state.view, { syncHistory: false });
loadData();
