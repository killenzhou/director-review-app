const state = {
  zip: null,
  zipFiles: new Map(),
  project: null,
  packages: [],
  packageIds: new Set(),
  entries: [],
  filteredRows: [],
  currentRow: -1,
  detailRow: -1,
  currentShotKey: "",
  shotGroups: new Map(),
  selectedRows: new Set(),
  expandedEpisodes: new Set(),
  expandedScenes: new Set(),
  objectUrls: new Map(),
  revDir: "",
  tempDirName: "",
  mode: "review",
};

const REVIEWHUB_FORMAT = "director-reviewhub";
const REVIEWHUB_VERSION = 1;
const LOCAL_DB_NAME = "director_review_web_viewer";
const LOCAL_DB_VERSION = 1;
const LOCAL_PROJECT_KEY = "latest";
const MAX_PROJECT_FILE_BYTES = 2 * 1024 * 1024 * 1024;
const TABLE_COLUMN_WIDTHS = [48, 132, 92, 92, 116, 160, 190, 300, 240, 160, 110, 130, 130];
const MIN_TABLE_COLUMN_WIDTH = 64;

const els = {
  fileInput: document.getElementById("fileInput"),
  projectInput: document.getElementById("projectInput"),
  clearButton: document.getElementById("clearButton"),
  restoreLocalButton: document.getElementById("restoreLocalButton"),
  saveLocalButton: document.getElementById("saveLocalButton"),
  exportRevpackButton: document.getElementById("exportRevpackButton"),
  exportProjectButton: document.getElementById("exportProjectButton"),
  exportTableButton: document.getElementById("exportTableButton"),
  exportSelectedProjectButton: document.getElementById("exportSelectedProjectButton"),
  cgtwPreviewButton: document.getElementById("cgtwPreviewButton"),
  cgtwSyncButton: document.getElementById("cgtwSyncButton"),
  selectAllRowsCheckbox: document.getElementById("selectAllRowsCheckbox"),
  reviewModeButton: document.getElementById("reviewModeButton"),
  tableModeButton: document.getElementById("tableModeButton"),
  historyModeButton: document.getElementById("historyModeButton"),
  reviewView: document.getElementById("reviewView"),
  tableView: document.getElementById("tableView"),
  historyView: document.getElementById("historyView"),
  focusReviewButton: document.getElementById("focusReviewButton"),
  openHistoryInReviewButton: document.getElementById("openHistoryInReviewButton"),
  reviewTable: document.querySelector(".review-table"),
  reviewTableBody: document.getElementById("reviewTableBody"),
  tableCount: document.getElementById("tableCount"),
  historyCount: document.getElementById("historyCount"),
  shotGroupList: document.getElementById("shotGroupList"),
  historyShotTitle: document.getElementById("historyShotTitle"),
  historyShotMeta: document.getElementById("historyShotMeta"),
  versionHistory: document.getElementById("versionHistory"),
  dropZone: document.getElementById("dropZone"),
  projectMeta: document.getElementById("projectMeta"),
  searchInput: document.getElementById("searchInput"),
  episodeFilter: document.getElementById("episodeFilter"),
  sceneFilter: document.getElementById("sceneFilter"),
  departmentFilter: document.getElementById("departmentFilter"),
  statusFilter: document.getElementById("statusFilter"),
  timeline: document.getElementById("timeline"),
  mediaStage: document.getElementById("mediaStage"),
  playerTitle: document.getElementById("playerTitle"),
  playerSubtitle: document.getElementById("playerSubtitle"),
  prevButton: document.getElementById("prevButton"),
  playButton: document.getElementById("playButton"),
  pauseButton: document.getElementById("pauseButton"),
  nextButton: document.getElementById("nextButton"),
  detailShot: document.getElementById("detailShot"),
  detailDept: document.getElementById("detailDept"),
  detailMetaLine: document.getElementById("detailMetaLine"),
  approveShotButton: document.getElementById("approveShotButton"),
  detailVersionSelect: document.getElementById("detailVersionSelect"),
  detailSourceInfo: document.getElementById("detailSourceInfo"),
  fullReview: document.getElementById("fullReview"),
  simpleReview: document.getElementById("simpleReview"),
  referencePreview: document.getElementById("referencePreview"),
  referenceList: document.getElementById("referenceList"),
};

function normalizePath(path) {
  return String(path || "").replace(/\\/g, "/").replace(/^\/+/, "");
}

function dirname(path) {
  const normalized = normalizePath(path);
  const index = normalized.lastIndexOf("/");
  return index >= 0 ? normalized.slice(0, index) : "";
}

function localDirname(path) {
  const raw = String(path || "").trim();
  if (!raw) return "";
  const normalized = raw.replace(/\\/g, "/");
  const index = normalized.lastIndexOf("/");
  return index >= 0 ? normalized.slice(0, index) : "";
}

function basename(path) {
  const normalized = normalizePath(path);
  return normalized.split("/").filter(Boolean).pop() || normalized;
}

function sanitizeZipName(name) {
  return String(name || "review.revpack").replace(/[\\/:*?"<>|]+/g, "_");
}

function fileStem(name) {
  const base = basename(name);
  const index = base.lastIndexOf(".");
  return index > 0 ? base.slice(0, index) : base;
}

function naturalPart(value) {
  return String(value || "").trim() || "未分配";
}

function firstEntryValue(entry, keys) {
  for (const key of keys) {
    const value = entry?.[key];
    if (value !== undefined && value !== null && String(value).trim()) return String(value).trim();
  }
  return "";
}

function normalizeEpisode(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const number = raw.match(/\d+/);
  return number ? `EP${String(Number(number[0])).padStart(2, "0")}` : raw;
}

function normalizeScene(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const number = raw.match(/[A-Za-z]*\d+[A-Za-z]*/);
  if (!number) return raw;
  const digits = number[0].match(/\d+/)?.[0] || number[0];
  return `SC${String(Number(digits)).padStart(3, "0")}`;
}

function parseEpisodeSceneFromText(text) {
  const raw = String(text || "");
  if (!raw) return { episode: "", scene: "" };

  const patterns = [
    /(?:^|[^a-z0-9])e(?:p)?[\s_-]*0*(\d{1,3}).*?(?:sc|scene|s)[\s_-]*0*([a-z0-9]{1,6})/i,
    /(?:^|[^a-z0-9])第?\s*0*(\d{1,3})\s*集.*?第?\s*0*([a-z0-9]{1,6})\s*场/i,
    /(?:^|[^a-z0-9])0*(\d{1,3})\s*集.*?0*([a-z0-9]{1,6})\s*场/i,
  ];

  for (const pattern of patterns) {
    const match = raw.match(pattern);
    if (match) {
      return {
        episode: normalizeEpisode(match[1]),
        scene: normalizeScene(match[2]),
      };
    }
  }
  return { episode: "", scene: "" };
}

function productionInfo(entry) {
  const explicitEpisode = firstEntryValue(entry, ["episode", "episode_number", "episode_id", "集号", "集数"]);
  const explicitScene = firstEntryValue(entry, ["scene", "scene_number", "scene_id", "场号", "场次"]);
  if (explicitEpisode || explicitScene) {
    return {
      episode: normalizeEpisode(explicitEpisode),
      scene: normalizeScene(explicitScene),
    };
  }

  const sources = [
    entry?.shot_number,
    entry?.screenshot_path,
    entry?.original_screenshot_path,
    entry?.__sourceFile,
    entry?.__projectName,
  ];
  for (const source of sources) {
    const parsed = parseEpisodeSceneFromText(source);
    if (parsed.episode || parsed.scene) return parsed;
  }
  return { episode: "", scene: "" };
}

function displayEpisode(entry) {
  return entry?.__episode || "未分集";
}

function displayScene(entry) {
  return entry?.__scene || "未分场";
}

function shotKey(entry) {
  const shot = String(entry?.shot_number || "").trim() || `__row_${entry?.__packageIndex || 0}_${entry?.__entryIndex || 0}`;
  return [displayEpisode(entry), displayScene(entry), shot].join("|");
}

function displayShotOnly(group) {
  const shot = String(group?.shot || "").trim();
  if (!shot) return "未识别";
  const escapedEpisode = String(group?.episode || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const escapedScene = String(group?.scene || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  if (escapedEpisode && escapedScene) {
    const scopedPattern = new RegExp(`^${escapedEpisode}[\\s_-]+${escapedScene}[\\s_-]+(.+)$`, "i");
    const scopedMatch = shot.match(scopedPattern);
    if (scopedMatch?.[1]) return scopedMatch[1].trim();
  }
  const genericMatch = shot.match(/^EP\d+[\s_-]+SC\w+[\s_-]+(.+)$/i);
  return genericMatch?.[1]?.trim() || shot;
}

function packageFor(entryOrIndex) {
  if (typeof entryOrIndex === "number") return state.packages[entryOrIndex] || null;
  if (entryOrIndex && Number.isInteger(entryOrIndex.__packageIndex)) {
    return state.packages[entryOrIndex.__packageIndex] || null;
  }
  const current = state.entries[state.currentRow];
  if (current && Number.isInteger(current.__packageIndex)) return state.packages[current.__packageIndex] || null;
  return state.packages[0] || null;
}

function extname(path) {
  const name = basename(path).toLowerCase();
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index + 1) : "";
}

function isImage(path) {
  return ["png", "jpg", "jpeg", "bmp", "webp", "gif"].includes(extname(path));
}

function isVideo(path) {
  return ["mp4", "mov", "mkv", "avi", "webm"].includes(extname(path));
}

function isAudio(path) {
  return ["wav", "mp3", "m4a", "aac", "ogg", "flac"].includes(extname(path));
}

function mimeType(path) {
  const ext = extname(path);
  const map = {
    png: "image/png",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    webp: "image/webp",
    gif: "image/gif",
    bmp: "image/bmp",
    mp4: "video/mp4",
    webm: "video/webm",
    mov: "video/quicktime",
    mp3: "audio/mpeg",
    wav: "audio/wav",
    m4a: "audio/mp4",
    ogg: "audio/ogg",
  };
  return map[ext] || "application/octet-stream";
}

function inferStatus(entry) {
  if (isEntryApproved(entry)) return "approved";
  if (!entry.full_review) return "pending";
  if (!entry.simplified_review || !entry.department || entry.department === "未分类") return "pending";
  return "done";
}

function isEntryApproved(entry) {
  return Boolean(
    entry?.approved ||
    entry?.review_outcome === "approved" ||
    entry?.review_status === "approved"
  );
}

function reviewText(entry) {
  return [
    entry?.full_review,
    entry?.simplified_review,
    Array.isArray(entry?.keywords) ? entry.keywords.join(" ") : entry?.keywords,
  ].join(" ").trim();
}

function inferReviewOutcome(entry) {
  if (isEntryApproved(entry)) return "pass";
  const text = reviewText(entry);
  if (!text) return "pending";
  const passPatterns = [
    /审核?通过/,
    /审片通过/,
    /可以通过/,
    /确认通过/,
    /通过[，,、。\s]*无需/,
    /无需修改/,
    /无需调整/,
    /无修改/,
    /无须修改/,
    /无须调整/,
  ];
  if (passPatterns.some((pattern) => pattern.test(text))) return "pass";
  return "revision";
}

function outcomeClass(entry) {
  return `is-${inferReviewOutcome(entry)}`;
}

function visibleEntries() {
  const query = els.searchInput.value.trim().toLowerCase();
  const episode = els.episodeFilter.value;
  const scene = els.sceneFilter.value;
  const dept = els.departmentFilter.value;
  const status = els.statusFilter.value;
  return state.entries
    .map((entry, row) => ({ entry, row }))
    .filter(({ entry }) => entry.entry_type !== "long_video_full")
    .filter(({ entry }) => !episode || displayEpisode(entry) === episode)
    .filter(({ entry }) => !scene || displayScene(entry) === scene)
    .filter(({ entry }) => !dept || entry.department === dept)
    .filter(({ entry }) => !status || inferStatus(entry) === status)
    .filter(({ entry }) => {
      if (!query) return true;
      const haystack = [
        displayEpisode(entry),
        displayScene(entry),
        entry.shot_number,
        entry.timestamp,
        entry.full_review,
        entry.simplified_review,
        entry.department,
        entry.__versionLabel,
        entry.__sourceFile,
        ...(entry.keywords || []),
      ].join(" ").toLowerCase();
      return haystack.includes(query);
    })
    .sort((a, b) => {
      const ea = a.entry;
      const eb = b.entry;
      return [
        displayEpisode(ea).localeCompare(displayEpisode(eb), "zh-CN", { numeric: true }),
        displayScene(ea).localeCompare(displayScene(eb), "zh-CN", { numeric: true }),
        String(ea.shot_number || "").localeCompare(String(eb.shot_number || ""), "zh-CN", { numeric: true }),
        (ea.__packageIndex || 0) - (eb.__packageIndex || 0),
        (ea.__entryIndex || 0) - (eb.__entryIndex || 0),
      ].find((value) => value !== 0) || 0;
    });
}

function resetObjectUrls() {
  for (const url of state.objectUrls.values()) URL.revokeObjectURL(url);
  state.objectUrls.clear();
}

function clearViewer() {
  resetObjectUrls();
  state.zip = null;
  state.zipFiles.clear();
  state.project = null;
  state.packages = [];
  state.packageIds = new Set();
  state.entries = [];
  state.filteredRows = [];
  state.currentRow = -1;
  state.detailRow = -1;
  state.currentShotKey = "";
  state.shotGroups = new Map();
  state.expandedEpisodes = new Set();
  state.expandedScenes = new Set();
  state.revDir = "";
  state.tempDirName = "";
  state.mode = "review";
  els.projectMeta.textContent = "拖入 .revpack 或 .reviewhub 查看返修";
  els.timeline.innerHTML = "";
  els.reviewTableBody.innerHTML = "";
  els.tableCount.textContent = "0 条记录";
  els.shotGroupList.innerHTML = "";
  els.versionHistory.innerHTML = "";
  els.historyCount.textContent = "0 个镜头";
  els.historyShotTitle.textContent = "未选择镜头";
  els.historyShotMeta.textContent = "加载多个 .revpack 后自动形成版本历史";
  els.mediaStage.innerHTML = '<div class="empty-state">暂无媒体</div>';
  state.selectedRows.clear();
  updateSelectAllRowsCheckbox();
  setMode("review");
  renderFilters();
  renderDetail(null, -1);
}

function indexZipFiles(zip) {
  const zipFiles = new Map();
  for (const [name, file] of Object.entries(zip.files)) {
    if (!file.dir) zipFiles.set(normalizePath(name), file);
  }
  return zipFiles;
}

function findZipFile(relPath, entryOrPackageIndex) {
  const path = normalizePath(relPath);
  if (!path) return null;
  const pkg = packageFor(entryOrPackageIndex);
  const zipFiles = pkg?.zipFiles || state.zipFiles;
  const tempDirName = pkg?.tempDirName || state.tempDirName;
  const revDir = pkg?.revDir || state.revDir;
  const candidates = [
    path,
    tempDirName ? `${tempDirName}/${path}` : "",
    revDir ? `${revDir}/${path}` : "",
    revDir && tempDirName ? `${revDir}/${tempDirName}/${path}` : "",
  ].filter(Boolean);
  for (const candidate of candidates) {
    const normalized = normalizePath(candidate);
    if (pkg?.addedFiles?.has(normalized)) return pkg.addedFiles.get(normalized);
    if (zipFiles.has(normalized)) return zipFiles.get(normalized);
  }
  const lower = path.toLowerCase();
  for (const [name, file] of pkg?.addedFiles || []) {
    if (name.toLowerCase().endsWith(`/${lower}`) || name.toLowerCase() === lower) return file;
  }
  for (const [name, file] of zipFiles.entries()) {
    if (name.toLowerCase().endsWith(`/${lower}`)) return file;
  }
  return null;
}

async function assetUrl(relPath, entryOrPackageIndex) {
  const path = normalizePath(relPath);
  if (!path) return "";
  const pkg = packageFor(entryOrPackageIndex);
  const packageIndex = pkg?.index ?? 0;
  const cacheKey = `${packageIndex}:${path}`;
  if (state.objectUrls.has(cacheKey)) return state.objectUrls.get(cacheKey);
  const file = findZipFile(path, entryOrPackageIndex);
  if (!file) return "";
  const blob = file.async ? await file.async("blob") : file;
  const typed = new Blob([blob], { type: mimeType(path) });
  const url = URL.createObjectURL(typed);
  state.objectUrls.set(cacheKey, url);
  return url;
}

async function assetDataUrl(relPath, entryOrPackageIndex) {
  const path = normalizePath(relPath);
  if (!path) return "";
  const file = findZipFile(path, entryOrPackageIndex);
  if (!file) return "";
  const base64 = file.async
    ? await file.async("base64")
    : await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || "").split(",")[1] || "");
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  return `data:${mimeType(path)};base64,${base64}`;
}

function createEl(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function packageIdentity(fileName, sourceBuffer) {
  return `${fileName}:${sourceBuffer?.byteLength || 0}`;
}

function formatBytes(bytes) {
  const value = Number(bytes) || 0;
  if (value >= 1024 * 1024 * 1024) return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} B`;
}

function oversizedFiles(files) {
  return Array.from(files || []).filter((file) => file && file.size > MAX_PROJECT_FILE_BYTES);
}

function explainOversizedFiles(files) {
  const lines = oversizedFiles(files).map((file) => `- ${file.name}: ${formatBytes(file.size)}`);
  if (!lines.length) return "";
  return [
    "以下工程超过 2GB，网页版已停止加载：",
    ...lines,
    "",
    "原因：浏览器读取 zip/reviewhub 时需要把索引和大量内容放进内存，超过 2GB 容易卡死或崩溃。",
    "建议：在桌面程序里按镜头或集场拆成多个 revpack，再在网页版一次选择多个小包导入。网页版不能可靠地把超大 zip 自动拆分后再打开。",
  ].join("\n");
}

function guardProjectFileSize(files) {
  const message = explainOversizedFiles(files);
  if (!message) return true;
  els.projectMeta.textContent = "工程超过 2GB，已停止加载";
  alert(message);
  return false;
}

async function parseRevpackBuffer(fileName, sourceBuffer, packageIndex) {
  const zip = await JSZip.loadAsync(sourceBuffer);
  const zipFiles = indexZipFiles(zip);

  const revName = Object.keys(zip.files).find((name) => !zip.files[name].dir && name.toLowerCase().endsWith(".rev"));
  if (!revName) throw new Error("压缩包中没有找到 .rev 项目文件。");
  const revDir = dirname(revName);
  const projectText = await zip.files[revName].async("string");
  const project = JSON.parse(projectText);
  const settings = project.settings || {};
  const versionLabel = `${packageIndex + 1}. ${settings.project_name || basename(fileName)}`;
  return {
    index: packageIndex,
    fileName,
    sourceBuffer,
    importId: packageIdentity(fileName, sourceBuffer),
    zip,
    zipFiles,
    project,
    settings,
    revName,
    revDir,
    tempDirName: normalizePath(project.temp_dir_name || ""),
    versionLabel,
    addedFiles: new Map(),
    entries: Array.isArray(project.reviews) ? project.reviews : [],
  };
}

async function parseRevpack(file, packageIndex) {
  const pkg = await parseRevpackBuffer(file.name, await file.arrayBuffer(), packageIndex);
  pkg.sourcePath = file.path || file.webkitRelativePath || file.name;
  return pkg;
}

function enrichEntry(entry, pkg, entryIndex) {
  const base = {
    ...entry,
    __packageIndex: pkg.index,
    __entryIndex: entryIndex,
    __versionLabel: pkg.versionLabel,
    __sourceFile: pkg.fileName,
    __projectName: pkg.settings.project_name || fileStem(pkg.fileName),
  };
  const info = productionInfo(base);
  base.__episode = info.episode;
  base.__scene = info.scene;
  return base;
}

function sourceEntryFor(entry) {
  const pkg = packageFor(entry);
  if (!pkg || !Number.isInteger(entry?.__entryIndex)) return null;
  return pkg.entries[entry.__entryIndex] || null;
}

function syncEntryProductionInfo(entry) {
  const info = productionInfo(entry);
  entry.__episode = info.episode;
  entry.__scene = info.scene;
}

function sanitizeShotNumber(value) {
  return String(value || "")
    .replace(/[\r\n\t]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function parseKeywords(value) {
  return String(value || "")
    .split(/[,，、\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function displayFileName(entry) {
  return entry?.__sourceFile || "";
}

function setEntryField(row, field, rawValue) {
  const entry = state.entries[row];
  if (!entry) return;
  let value = rawValue;
  if (field === "episode") value = normalizeEpisode(rawValue);
  if (field === "scene") value = normalizeScene(rawValue);
  if (field === "shot_number") value = sanitizeShotNumber(rawValue);
  if (field === "keywords") value = parseKeywords(rawValue);
  entry[field] = value;
  const sourceEntry = sourceEntryFor(entry);
  if (sourceEntry) sourceEntry[field] = value;
  if (sourceEntry && field === "episode") sourceEntry.episode = value;
  if (sourceEntry && field === "scene") sourceEntry.scene = value;
  if (field === "episode") entry.__episode = value;
  if (field === "scene") entry.__scene = value;
  if (!["episode", "scene"].includes(field)) syncEntryProductionInfo(entry);
}

function editableText(entry, field) {
  if (field === "episode") return entry?.episode || entry?.__episode || "";
  if (field === "scene") return entry?.scene || entry?.__scene || "";
  const value = entry?.[field];
  if (field === "keywords" && Array.isArray(value)) return value.join(", ");
  return value || "";
}

async function commitTableEdit(row, field, element) {
  const value = element.innerText.trim();
  setEntryField(row, field, value);
  buildShotGroups();
  renderDetail(state.entries[row], row);
  highlightTableRow();
  await renderTimeline();
  await saveLocalProject({ silent: true });
}

function setEntryApproved(row, approved) {
  const entry = state.entries[row];
  if (!entry) return;
  const nextValue = Boolean(approved);
  const stamp = nextValue ? new Date().toISOString() : "";
  entry.approved = nextValue;
  entry.review_outcome = nextValue ? "approved" : "";
  entry.review_status = nextValue ? "approved" : "";
  entry.approved_at = stamp;
  const sourceEntry = sourceEntryFor(entry);
  if (sourceEntry) {
    sourceEntry.approved = nextValue;
    sourceEntry.review_outcome = entry.review_outcome;
    sourceEntry.review_status = entry.review_status;
    sourceEntry.approved_at = stamp;
  }
}

function updateApprovalButton(entry) {
  if (!els.approveShotButton) return;
  if (!entry) {
    els.approveShotButton.disabled = true;
    els.approveShotButton.textContent = "通过当前镜头";
    els.approveShotButton.classList.remove("is-approved");
    return;
  }
  const approved = isEntryApproved(entry);
  els.approveShotButton.disabled = false;
  els.approveShotButton.textContent = approved ? "取消通过" : "通过当前镜头";
  els.approveShotButton.classList.toggle("is-approved", approved);
}

async function toggleCurrentApproval() {
  const row = state.detailRow;
  const entry = state.entries[row];
  if (!entry) return;
  setEntryApproved(row, !isEntryApproved(entry));
  state.currentRow = row;
  state.currentShotKey = shotKey(entry);
  renderDetail(state.entries[row], row);
  highlightTableRow();
  await renderTimeline();
  if (state.mode === "history") await renderHistory();
  await saveLocalProject({ silent: true });
}

function appendPackage(pkg) {
  state.packages.push(pkg);
  state.packageIds.add(pkg.importId);
  if (!state.project) state.project = pkg.project;
  if (!state.zip) {
    state.zip = pkg.zip;
    state.zipFiles = pkg.zipFiles;
    state.revDir = pkg.revDir;
    state.tempDirName = pkg.tempDirName;
  }
  for (const [entryIndex, entry] of pkg.entries.entries()) {
    state.entries.push(enrichEntry(entry, pkg, entryIndex));
  }
}

async function loadRevpack(file) {
  await loadFiles([file], { replace: false });
}

async function loadFiles(files, options = {}) {
  const list = Array.from(files || []).filter(Boolean);
  if (!list.length) return;
  if (!guardProjectFileSize(list)) return;
  if (options.replace) clearViewer();
  els.projectMeta.textContent = `正在导入 ${list.length} 个审阅包...`;
  let added = 0;
  let skipped = 0;
  for (const file of list) {
    const pkg = await parseRevpack(file, state.packages.length);
    if (state.packageIds.has(pkg.importId)) {
      skipped += 1;
      continue;
    }
    appendPackage(pkg);
    added += 1;
  }
  await finalizeLoadedProject(skipped ? `已导入 ${added} 个新包，跳过 ${skipped} 个重复包` : "");
  await saveLocalProject({ silent: true });
}

async function finalizeLoadedProject(message = "") {
  buildShotGroups();
  const total = state.entries.length;
  const packageNames = state.packages.map((pkg) => pkg.settings.project_name || basename(pkg.fileName));
  const prefix = message ? `${message} · ` : "";
  els.projectMeta.textContent = `${prefix}${state.packages.length} 个审阅包 · ${total} 条返修 · ${packageNames.join(" / ")}`;
  renderFilters();
  await renderTimeline();
  await renderHistory();
}

function buildReviewHubManifest() {
  return {
    format: REVIEWHUB_FORMAT,
    version: REVIEWHUB_VERSION,
    exportedAt: new Date().toISOString(),
    currentRow: state.currentRow,
    mode: state.mode,
    packages: state.packages.map((pkg, index) => {
      const path = `packages/${String(index + 1).padStart(3, "0")}_${sanitizeZipName(pkg.fileName)}`;
      return {
        fileName: pkg.fileName,
        projectName: pkg.settings.project_name || "",
        versionLabel: pkg.versionLabel,
        byteLength: pkg.sourceBuffer?.byteLength || 0,
        path,
      };
    }),
  };
}

function serializableProject(pkg) {
  return {
    ...(pkg.project || {}),
    settings: pkg.settings || pkg.project?.settings || {},
    reviews: Array.isArray(pkg.entries) ? pkg.entries : [],
  };
}

async function updatedRevpackBlob(pkg) {
  const zip = await JSZip.loadAsync(pkg.sourceBuffer);
  for (const [path, file] of pkg.addedFiles || []) zip.file(path, file);
  zip.file(pkg.revName, JSON.stringify(serializableProject(pkg), null, 2));
  try {
    return await zip.generateAsync({ type: "blob", compression: "DEFLATE", compressionOptions: { level: 6 } });
  } catch (error) {
    const buffer = await zip.generateAsync({ type: "arraybuffer", compression: "DEFLATE", compressionOptions: { level: 6 } });
    return new Blob([buffer], { type: "application/zip" });
  }
}

async function buildReviewHubZip() {
  if (!state.packages.length) throw new Error("当前没有可保存的审阅包。");
  const zip = new JSZip();
  const manifest = buildReviewHubManifest();
  zip.file("reviewhub.json", JSON.stringify(manifest, null, 2));
  for (const [index, pkg] of state.packages.entries()) {
    zip.file(manifest.packages[index].path, await updatedRevpackBlob(pkg));
  }
  const options = { compression: "DEFLATE", compressionOptions: { level: 6 } };
  try {
    return await zip.generateAsync({ ...options, type: "blob" });
  } catch (error) {
    const buffer = await zip.generateAsync({ ...options, type: "arraybuffer" });
    return new Blob([buffer], { type: "application/zip" });
  }
}

function downloadBlob(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function exportReviewHub() {
  try {
    const blob = await buildReviewHubZip();
    const baseName = state.project?.settings?.project_name || state.packages[0]?.settings?.project_name || "返修审阅工程";
    downloadBlob(blob, `${sanitizeZipName(baseName)}.reviewhub`);
    els.projectMeta.textContent = `已导出工程 · ${state.packages.length} 个审阅包`;
  } catch (error) {
    console.error(error);
    alert(`无法导出工程：${error.message || error}`);
  }
}

async function exportUpdatedRevpacks() {
  try {
    if (!state.packages.length) throw new Error("当前没有可导出的审阅包。");
    if (state.packages.length === 1) {
      const pkg = state.packages[0];
      const blob = await updatedRevpackBlob(pkg);
      downloadBlob(blob, sanitizeZipName(pkg.fileName || "updated.revpack"));
      els.projectMeta.textContent = `已导出更新后的 ${pkg.fileName}`;
      return;
    }
    const zip = new JSZip();
    for (const pkg of state.packages) {
      zip.file(sanitizeZipName(pkg.fileName || "updated.revpack"), await updatedRevpackBlob(pkg));
    }
    const blob = await zip.generateAsync({ type: "blob", compression: "DEFLATE", compressionOptions: { level: 6 } });
    downloadBlob(blob, "updated_revpacks.zip");
    els.projectMeta.textContent = `已导出 ${state.packages.length} 个更新后的 revpack`;
  } catch (error) {
    console.error(error);
    alert(`无法导出 revpack：${error.message || error}`);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function exportRows() {
  const selected = selectedRowIndexes();
  return selected.length ? selected : visibleRowIndexes();
}

function cgtwExportEntries() {
  return exportRows()
    .map((row) => state.entries[row])
    .filter(Boolean)
    .map((entry) => ({
      shot_number: entry.shot_number || "",
      timestamp: entry.timestamp || "",
      full_review: entry.full_review || "",
      simplified_review: entry.simplified_review || "",
      keywords: Array.isArray(entry.keywords) ? entry.keywords : [],
      department: entry.department || "",
      screenshot_path: entry.screenshot_path || "",
      reference_files: Array.isArray(entry.reference_files) ? entry.reference_files : [],
      media_files: Array.isArray(entry.media_files) ? entry.media_files : [],
      audio_path: entry.audio_path || "",
    }));
}

async function requestCgtwSync(dryRun) {
  const entries = cgtwExportEntries();
  if (!entries.length) {
    alert("没有可同步的记录。");
    return;
  }
  if (!dryRun) {
    const ok = confirm(`将把 ${entries.length} 条反馈写入 CGTeamWork Note。请确认已经预检过匹配结果，是否继续？`);
    if (!ok) return;
  }
  const button = dryRun ? els.cgtwPreviewButton : els.cgtwSyncButton;
  const oldText = button?.textContent || "";
  if (button) {
    button.disabled = true;
    button.textContent = dryRun ? "预检中..." : "同步中...";
  }
  try {
      let successCount = 0;
      let failCount = 0;
      let skipCount = 0;
      const resultsLog = [];
      
      for (let i = 0; i < entries.length; i++) {
        if (button) {
          button.textContent = ${dryRun ? "预检中" : "同步中"} (/)...;
        }
        
        const response = await fetch("http://127.0.0.1:8787/cgtw/sync", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ entries: [entries[i]], dry_run: dryRun }),
        });
        const data = await response.json();
        const result = data.result || {};
        const itemResult = (result.results || [])[0];
        
        if (itemResult) {
            if (itemResult.error) {
                failCount++;
                resultsLog.push([] 失败: );
            } else if (itemResult.skipped) {
                skipCount++;
                resultsLog.push([] 跳过: );
            } else {
                successCount++;
                resultsLog.push([] 成功);
            }
        }
      }
      
      const lines = [
        CGTeamWork 完成！,
        成功:   失败:   跳过: ,
        "",
        ...resultsLog.slice(0, 20)
      ];
      if (resultsLog.length > 20) lines.push("...");
      alert(lines.join("
"));
    } catch (error) {
      alert(通信失败：);
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = oldText;
      }
    }
}

async function exportTable() {
  try {
    const rows = exportRows().filter((row) => state.entries[row]);
    if (!rows.length) throw new Error("当前没有可导出的表格记录。");
    const headers = ["状态", "集号", "场号", "时间码", "镜头号", "revpack地址", "完整意见", "简化意见", "关键词", "部门", "参考数量", "媒体数量"];
    const bodyRows = [];
    for (const row of rows) {
      const entry = state.entries[row];
      const refs = Array.isArray(entry.reference_files) ? entry.reference_files.filter(Boolean) : [];
      const media = Array.isArray(entry.media_files) ? entry.media_files.filter(Boolean) : [];
      const approved = isEntryApproved(entry);
      const statusLabel = approved ? "已通过" : inferStatus(entry) === "done" ? "已完成" : "待处理";
      const cells = [
        `<span class="status-pill ${approved ? "status-approved" : ""}">${escapeHtml(statusLabel)}</span>`,
        escapeHtml(displayEpisode(entry)),
        escapeHtml(displayScene(entry)),
        escapeHtml(entry.timestamp || ""),
        escapeHtml(entry.shot_number || ""),
        escapeHtml(displayFileName(entry)),
        escapeHtml(entry.full_review || ""),
        escapeHtml(entry.simplified_review || ""),
        escapeHtml(Array.isArray(entry.keywords) ? entry.keywords.join(", ") : (entry.keywords || "")),
        escapeHtml(entry.department || ""),
        escapeHtml(refs.length),
        escapeHtml(media.length),
      ];
      bodyRows.push(`<tr class="${approved ? "is-approved" : ""}">${cells.map((cell) => `<td>${cell}</td>`).join("")}</tr>`);
    }
    const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    body {
      margin: 18px;
      background: #f4f7fb;
      color: #17202a;
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
    }
    .export-title {
      margin: 0 0 12px;
      font-size: 18px;
      font-weight: 800;
      color: #111827;
    }
    .export-meta {
      margin: 0 0 16px;
      color: #64748b;
      font-size: 12px;
    }
    table {
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      table-layout: fixed;
      background: #ffffff;
      border: 1px solid #d9e2ec;
      border-radius: 8px;
      overflow: hidden;
      font-size: 12px;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
    }
    th, td {
      border-right: 1px solid #e2e8f0;
      border-bottom: 1px solid #e2e8f0;
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      word-break: break-word;
      line-height: 1.45;
    }
    th {
      background: #1f2937;
      color: #e5e7eb;
      font-weight: 700;
    }
    tbody tr:nth-child(even) td { background: #f8fafc; }
    tbody tr.is-approved td { background: #ecfdf3; }
    tbody tr.is-approved td:first-child { box-shadow: inset 4px 0 0 #22c55e; }
    .status-pill {
      display: inline-block;
      min-width: 54px;
      padding: 3px 8px;
      border-radius: 999px;
      background: #eef2f7;
      color: #475569;
      font-weight: 700;
      text-align: center;
    }
    .status-approved {
      background: #dcfce7;
      color: #15803d;
    }
    th:nth-child(1), td:nth-child(1) { width: 72px; }
    th:nth-child(2), td:nth-child(2) { width: 76px; }
    th:nth-child(3), td:nth-child(3) { width: 76px; }
    th:nth-child(4), td:nth-child(4) { width: 96px; }
    th:nth-child(5), td:nth-child(5) { width: 128px; }
    th:nth-child(6), td:nth-child(6) { width: 170px; }
    th:nth-child(7), td:nth-child(7) { width: 300px; }
    th:nth-child(8), td:nth-child(8) { width: 240px; }
    th:nth-child(9), td:nth-child(9) { width: 140px; }
    th:nth-child(10), td:nth-child(10) { width: 92px; }
    th:nth-child(11), td:nth-child(11),
    th:nth-child(12), td:nth-child(12) { width: 72px; text-align: center; }
  </style>
</head>
<body>
  <h1 class="export-title">返修意见表</h1>
  <p class="export-meta">${escapeHtml(new Date().toLocaleString())} · ${rows.length} 条记录 · 不导出图片</p>
  <table>
    <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
    <tbody>${bodyRows.join("")}</tbody>
  </table>
</body>
</html>`;
    const blob = new Blob(["\ufeff", html], { type: "application/vnd.ms-excel;charset=utf-8" });
    const suffix = selectedRowIndexes().length ? "选中" : "当前筛选";
    downloadBlob(blob, `返修意见表_${suffix}_${new Date().toISOString().slice(0, 10)}.xls`);
    els.projectMeta.textContent = `已导出表格 · ${rows.length} 条记录`;
  } catch (error) {
    console.error(error);
    alert(`无法导出表格：${error.message || error}`);
  }
}

async function filteredRevpackBlob(pkg, entryIndexes) {
  const zip = await JSZip.loadAsync(pkg.sourceBuffer);
  for (const [path, file] of pkg.addedFiles || []) zip.file(path, file);
  const filteredProject = {
    ...(pkg.project || {}),
    settings: pkg.settings || pkg.project?.settings || {},
    reviews: entryIndexes.map((index) => pkg.entries[index]).filter(Boolean),
  };
  zip.file(pkg.revName, JSON.stringify(filteredProject, null, 2));
  try {
    return await zip.generateAsync({ type: "blob", compression: "DEFLATE", compressionOptions: { level: 6 } });
  } catch (error) {
    const buffer = await zip.generateAsync({ type: "arraybuffer", compression: "DEFLATE", compressionOptions: { level: 6 } });
    return new Blob([buffer], { type: "application/zip" });
  }
}

async function exportSelectedProject() {
  try {
    const rows = selectedRowIndexes();
    if (!rows.length) throw new Error("请先在表格里勾选要单独导出的镜头。");
    const rowsByPackage = new Map();
    for (const row of rows) {
      const entry = state.entries[row];
      if (!entry) continue;
      if (!rowsByPackage.has(entry.__packageIndex)) rowsByPackage.set(entry.__packageIndex, []);
      rowsByPackage.get(entry.__packageIndex).push(entry.__entryIndex);
    }
    const zip = new JSZip();
    const packages = [];
    let exportIndex = 0;
    for (const [packageIndex, entryIndexes] of rowsByPackage.entries()) {
      const pkg = state.packages[packageIndex];
      if (!pkg) continue;
      exportIndex += 1;
      const fileName = sanitizeZipName(pkg.fileName || `selected_${exportIndex}.revpack`);
      const path = `packages/${String(exportIndex).padStart(3, "0")}_${fileName}`;
      packages.push({
        fileName,
        projectName: pkg.settings.project_name || "",
        versionLabel: pkg.versionLabel,
        byteLength: pkg.sourceBuffer?.byteLength || 0,
        path,
      });
      zip.file(path, await filteredRevpackBlob(pkg, entryIndexes));
    }
    if (!packages.length) throw new Error("没有找到可导出的选中镜头。");
    zip.file("reviewhub.json", JSON.stringify({
      format: REVIEWHUB_FORMAT,
      version: REVIEWHUB_VERSION,
      exportedAt: new Date().toISOString(),
      currentRow: 0,
      mode: "review",
      packages,
    }, null, 2));
    const blob = await zip.generateAsync({ type: "blob", compression: "DEFLATE", compressionOptions: { level: 6 } });
    const baseName = state.project?.settings?.project_name || "选中镜头工程";
    downloadBlob(blob, `${sanitizeZipName(baseName)}_选中${rows.length}镜头.reviewhub`);
    els.projectMeta.textContent = `已导出选中工程 · ${rows.length} 个镜头`;
  } catch (error) {
    console.error(error);
    alert(`无法导出选中工程：${error.message || error}`);
  }
}

async function loadReviewHub(file) {
  if (!guardProjectFileSize([file])) return;
  const hubZip = await JSZip.loadAsync(await file.arrayBuffer());
  const manifestFile = hubZip.file("reviewhub.json");
  if (!manifestFile) throw new Error("工程文件中没有 reviewhub.json。");
  const manifest = JSON.parse(await manifestFile.async("string"));
  if (manifest.format !== REVIEWHUB_FORMAT) throw new Error("这不是协同审阅网页工程文件。");

  clearViewer();
  els.projectMeta.textContent = "正在打开网页工程...";
  for (const item of manifest.packages || []) {
    const packed = hubZip.file(item.path);
    if (!packed) continue;
    const sourceBuffer = await packed.async("arraybuffer");
    const pkg = await parseRevpackBuffer(item.fileName || basename(item.path), sourceBuffer, state.packages.length);
    if (!state.packageIds.has(pkg.importId)) appendPackage(pkg);
  }
  state.currentRow = Number.isInteger(manifest.currentRow) ? manifest.currentRow : state.currentRow;
  await finalizeLoadedProject(`已打开工程 ${basename(file.name)}`);
  await saveLocalProject({ silent: true });
}

function openLocalDb() {
  return new Promise((resolve, reject) => {
    const dbFactory = window.indexedDB || globalThis.indexedDB;
    if (!dbFactory) {
      reject(new Error("当前浏览器不支持 IndexedDB 本机保存。"));
      return;
    }
    const request = dbFactory.open(LOCAL_DB_NAME, LOCAL_DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("projects")) db.createObjectStore("projects", { keyPath: "key" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function saveLocalProject(options = {}) {
  if (!state.packages.length) return;
  try {
    const db = await openLocalDb();
    const savedPackages = await Promise.all(state.packages.map(async (pkg) => ({
      fileName: pkg.fileName,
      sourceBuffer: await (await updatedRevpackBlob(pkg)).arrayBuffer(),
    })));
    const record = {
      key: LOCAL_PROJECT_KEY,
      savedAt: new Date().toISOString(),
      currentRow: state.currentRow,
      mode: state.mode,
      packages: savedPackages,
    };
    await new Promise((resolve, reject) => {
      const tx = db.transaction("projects", "readwrite");
      tx.objectStore("projects").put(record);
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
    });
    db.close();
    if (!options.silent) els.projectMeta.textContent = `已保存到本机浏览器 · ${state.packages.length} 个审阅包`;
  } catch (error) {
    if (!options.silent) {
      console.error(error);
      alert(`无法保存到本机：${error.message || error}`);
    }
  }
}

async function restoreLocalProject() {
  try {
    const db = await openLocalDb();
    const record = await new Promise((resolve, reject) => {
      const tx = db.transaction("projects", "readonly");
      const request = tx.objectStore("projects").get(LOCAL_PROJECT_KEY);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    db.close();
    if (!record) {
      alert("本机浏览器里还没有保存过工程。");
      return;
    }
    clearViewer();
    els.projectMeta.textContent = "正在恢复本机工程...";
    for (const item of record.packages || []) {
      const pkg = await parseRevpackBuffer(item.fileName, item.sourceBuffer, state.packages.length);
      if (!state.packageIds.has(pkg.importId)) appendPackage(pkg);
    }
    state.currentRow = Number.isInteger(record.currentRow) ? record.currentRow : state.currentRow;
    state.mode = record.mode || state.mode;
    await finalizeLoadedProject(`已恢复本机工程 ${record.savedAt ? new Date(record.savedAt).toLocaleString() : ""}`);
    setMode(state.mode);
  } catch (error) {
    console.error(error);
    alert(`无法恢复本机工程：${error.message || error}`);
  }
}

function setSelectOptions(select, placeholder, values) {
  const previous = select.value;
  select.innerHTML = "";
  select.appendChild(new Option(placeholder, ""));
  for (const value of values) select.appendChild(new Option(value, value));
  if (values.includes(previous)) select.value = previous;
}

function renderFilters() {
  const episodes = Array.from(new Set(state.entries.map(displayEpisode).filter(Boolean))).sort();
  const scenes = Array.from(new Set(
    state.entries
      .filter((entry) => !els.episodeFilter.value || displayEpisode(entry) === els.episodeFilter.value)
      .map(displayScene)
      .filter(Boolean)
  )).sort();
  const departments = Array.from(new Set(state.entries.map((entry) => entry.department).filter(Boolean))).sort();
  setSelectOptions(els.episodeFilter, "全部集数", episodes);
  setSelectOptions(els.sceneFilter, "全部场次", scenes);
  setSelectOptions(els.departmentFilter, "全部部门", departments);
}

function buildShotGroups() {
  state.shotGroups = new Map();
  for (const [row, entry] of state.entries.entries()) {
    if (entry.entry_type === "long_video_full") continue;
    const key = shotKey(entry);
    if (!state.shotGroups.has(key)) {
      state.shotGroups.set(key, {
        key,
        episode: displayEpisode(entry),
        scene: displayScene(entry),
        shot: entry.shot_number || `未命名镜头 ${row + 1}`,
        rows: [],
      });
    }
    state.shotGroups.get(key).rows.push(row);
  }
  for (const group of state.shotGroups.values()) {
    group.rows.sort((a, b) => {
      const ea = state.entries[a];
      const eb = state.entries[b];
      return (ea.__packageIndex - eb.__packageIndex) || (ea.__entryIndex - eb.__entryIndex);
    });
  }
  state.shotGroups = new Map(Array.from(state.shotGroups.entries()).sort(([, a], [, b]) => {
    return `${a.episode}|${a.scene}|${a.shot}`.localeCompare(`${b.episode}|${b.scene}|${b.shot}`, "zh-CN", { numeric: true });
  }));
  if (!state.currentShotKey || !state.shotGroups.has(state.currentShotKey)) {
    state.currentShotKey = state.shotGroups.keys().next().value || "";
  }
}

function setMode(mode) {
  const nextMode = ["review", "table", "history"].includes(mode) ? mode : "review";
  if (state.mode === "review" && nextMode !== "review") pauseCurrent();
  state.mode = nextMode;
  els.reviewModeButton.classList.toggle("is-active", state.mode === "review");
  els.tableModeButton.classList.toggle("is-active", state.mode === "table");
  els.historyModeButton.classList.toggle("is-active", state.mode === "history");
  els.reviewView.classList.toggle("hidden", state.mode !== "review");
  els.tableView.classList.toggle("hidden", state.mode !== "table");
  els.historyView.classList.toggle("hidden", state.mode !== "history");
  if (state.mode === "table") renderTable();
  if (state.mode === "history") renderHistory();
}

async function renderTimeline() {
  els.timeline.innerHTML = "";
  state.filteredRows = visibleEntries().map(({ row }) => row);
  if (!state.filteredRows.length) {
    els.timeline.appendChild(createEl("div", "empty-state", "没有匹配的镜头"));
    renderTable();
    renderDetail(null, -1);
    els.mediaStage.innerHTML = '<div class="empty-state">暂无媒体</div>';
    return;
  }

  if (!state.filteredRows.includes(state.currentRow)) state.currentRow = state.filteredRows[0];

  for (const row of state.filteredRows) {
    const entry = state.entries[row];
    const clip = createEl("button", `clip ${row === state.currentRow ? "is-active" : ""} ${outcomeClass(entry)}`);
    clip.type = "button";
    clip.dataset.row = String(row);
    clip.addEventListener("click", () => selectRow(row));
    clip.addEventListener("contextmenu", (event) => showTimelineVersionMenu(event, row));

    const thumb = createEl("div", "clip-thumb", "无截图");
    const screenshot = entry.screenshot_path || entry.original_screenshot_path;
    const url = await assetUrl(screenshot, entry);
    if (url && isImage(screenshot)) {
      thumb.textContent = "";
      const img = document.createElement("img");
      img.src = url;
      img.alt = entry.shot_number || `第 ${row + 1} 行`;
      thumb.appendChild(img);
    }
    clip.appendChild(thumb);
    clip.appendChild(createEl("div", "clip-title", entry.shot_number || `第 ${row + 1} 行`));
    clip.appendChild(createEl("div", "clip-meta", `${displayEpisode(entry)} · ${displayScene(entry)}`));
    clip.appendChild(createEl("div", "clip-meta", `${entry.__versionLabel || ""} · ${entry.department || "未分类"}${entry.reference_files?.length ? " · 参考" : ""}`));
    els.timeline.appendChild(clip);
  }

  await selectRow(state.currentRow, false);
  await renderTable();
  if (state.mode === "history") await renderHistory();
}

function closeTimelineVersionMenu() {
  document.querySelector(".timeline-version-menu")?.remove();
  document.removeEventListener("click", closeTimelineVersionMenu, true);
  document.removeEventListener("scroll", closeTimelineVersionMenu, true);
  document.removeEventListener("keydown", handleTimelineMenuKeydown, true);
}

function handleTimelineMenuKeydown(event) {
  if (event.key === "Escape") closeTimelineVersionMenu();
}

function timelineVersionLabel(entry) {
  const source = entry.__sourceFile || entry.__versionLabel || `版本 ${entry.__packageIndex + 1}`;
  const time = entry.timestamp || "-";
  const dept = entry.department || "未分类";
  return { source, meta: `${time} · ${dept}` };
}

function showTimelineVersionMenu(event, row) {
  event.preventDefault();
  event.stopPropagation();
  const entry = state.entries[row];
  if (!entry) return;

  closeTimelineVersionMenu();
  const group = state.shotGroups.get(shotKey(entry));
  const rows = group?.rows?.length ? group.rows : [row];
  const menu = createEl("div", "timeline-version-menu");
  menu.setAttribute("role", "menu");
  menu.appendChild(createEl("div", "timeline-version-menu-title", "选择修改意见版本"));

  for (const versionRow of rows) {
    const versionEntry = state.entries[versionRow];
    if (!versionEntry) continue;
    const { source, meta } = timelineVersionLabel(versionEntry);
    const item = createEl("button", `timeline-version-item ${versionRow === state.detailRow ? "is-active" : ""}`);
    item.type = "button";
    item.setAttribute("role", "menuitem");
    item.appendChild(createEl("span", "timeline-version-name", source));
    item.appendChild(createEl("span", "timeline-version-meta", meta));
    item.addEventListener("click", async () => {
      closeTimelineVersionMenu();
      await selectRow(row, false);
      await selectDetailVersion(versionRow);
    });
    menu.appendChild(item);
  }

  document.body.appendChild(menu);
  const margin = 8;
  const rect = menu.getBoundingClientRect();
  const left = Math.min(event.clientX, window.innerWidth - rect.width - margin);
  const top = Math.min(event.clientY, window.innerHeight - rect.height - margin);
  menu.style.left = `${Math.max(margin, left)}px`;
  menu.style.top = `${Math.max(margin, top)}px`;

  setTimeout(() => {
    document.addEventListener("click", closeTimelineVersionMenu, true);
    document.addEventListener("scroll", closeTimelineVersionMenu, true);
    document.addEventListener("keydown", handleTimelineMenuKeydown, true);
  }, 0);
}

function highlightTimelineRow() {
  for (const clip of els.timeline.querySelectorAll(".clip")) {
    clip.classList.toggle("is-active", Number(clip.dataset.row) === state.currentRow);
  }
}

async function selectRow(row, rerenderTimeline = true) {
  if (!state.entries[row]) return;
  if (row !== state.currentRow) pauseCurrent();
  state.currentRow = row;
  state.currentShotKey = shotKey(state.entries[row]);
  renderDetail(state.entries[row], row);
  await renderMedia(state.entries[row]);
  highlightTableRow();
  highlightTimelineRow();
  if (rerenderTimeline) await renderTimeline();
}

async function renderTable() {
  els.reviewTableBody.innerHTML = "";
  const rows = state.filteredRows.length ? state.filteredRows : visibleEntries().map(({ row }) => row);
  els.tableCount.textContent = `${rows.length} 条记录`;
  updateSelectAllRowsCheckbox(rows);
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = TABLE_COLUMN_WIDTHS.length;
    td.textContent = "没有匹配的记录";
    td.className = "empty-state";
    tr.appendChild(td);
    els.reviewTableBody.appendChild(tr);
    return;
  }

  for (const row of rows) {
    const entry = state.entries[row];
    const tr = document.createElement("tr");
    tr.dataset.row = String(row);
    tr.classList.add(outcomeClass(entry));
    tr.classList.toggle("is-active", row === state.currentRow);
    tr.addEventListener("click", () => selectRow(row));

    const selectCell = document.createElement("td");
    selectCell.className = "select-cell";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.selectedRows.has(row);
    checkbox.setAttribute("aria-label", `选择 ${entry.shot_number || `第 ${row + 1} 行`}`);
    checkbox.addEventListener("click", (event) => event.stopPropagation());
    checkbox.addEventListener("change", () => {
      setRowSelected(row, checkbox.checked);
      updateSelectAllRowsCheckbox(rows);
    });
    selectCell.appendChild(checkbox);
    tr.appendChild(selectCell);

    const screenshot = entry.screenshot_path || entry.original_screenshot_path;
    const thumbCell = document.createElement("td");
    const thumb = createEl("div", "table-thumb", "无截图");
    const url = await assetUrl(screenshot, entry);
    if (url && isImage(screenshot)) {
      thumb.textContent = "";
      const img = document.createElement("img");
      img.src = url;
      img.alt = entry.shot_number || `第 ${row + 1} 行`;
      thumb.appendChild(img);
    }
    thumbCell.appendChild(thumb);
    tr.appendChild(thumbCell);

    appendEditableCell(tr, row, "episode", editableText(entry, "episode"), "", "未分集");
    appendEditableCell(tr, row, "scene", editableText(entry, "scene"), "", "未分场");
    appendEditableCell(tr, row, "timestamp", editableText(entry, "timestamp"));
    appendEditableCell(tr, row, "shot_number", editableText(entry, "shot_number"), "shot-number-cell", `第 ${row + 1} 行`);
    appendTextCell(tr, displayFileName(entry));
    appendEditableCell(tr, row, "full_review", editableText(entry, "full_review"), "table-text");
    appendEditableCell(tr, row, "simplified_review", editableText(entry, "simplified_review"), "table-text");
    appendEditableCell(tr, row, "keywords", editableText(entry, "keywords"));
    appendEditableCell(tr, row, "department", editableText(entry, "department") || "未分类");
    appendCountCell(tr, entry.reference_files, {
      title: "右键打开参考所在文件夹",
      onContextMenu: (event) => {
        event.preventDefault();
        event.stopPropagation();
        requestOpenSystemFolder(firstPathFromFiles(entry.reference_files), entry);
      },
    });
    const mediaFilesForCell = [
      ...(Array.isArray(entry.media_files) ? entry.media_files.filter(Boolean) : []),
      entry.audio_path,
    ].filter(Boolean);
    appendCountCell(tr, mediaFilesForCell, {
      title: "播放此行媒体",
      onClick: (event) => {
        event.stopPropagation();
        playTableMedia(row);
      },
      onContextMenu: (event) => {
        event.preventDefault();
        event.stopPropagation();
        requestOpenSystemFolder(firstPathFromFiles(mediaFilesForCell), entry);
      },
    });

    els.reviewTableBody.appendChild(tr);
  }
}

function appendTextCell(rowEl, text, className = "") {
  const td = document.createElement("td");
  const div = createEl("div", className, text || "-");
  td.appendChild(div);
  rowEl.appendChild(td);
}

function setRowSelected(row, selected) {
  if (!state.entries[row]) return;
  if (selected) state.selectedRows.add(row);
  else state.selectedRows.delete(row);
}

function visibleRowIndexes() {
  return state.filteredRows.length ? state.filteredRows : visibleEntries().map(({ row }) => row);
}

function selectedRowIndexes() {
  return Array.from(state.selectedRows)
    .filter((row) => state.entries[row])
    .sort((a, b) => a - b);
}

function updateSelectAllRowsCheckbox(rows = visibleRowIndexes()) {
  if (!els.selectAllRowsCheckbox) return;
  const selectableRows = rows.filter((row) => state.entries[row]);
  const selectedCount = selectableRows.filter((row) => state.selectedRows.has(row)).length;
  els.selectAllRowsCheckbox.checked = selectableRows.length > 0 && selectedCount === selectableRows.length;
  els.selectAllRowsCheckbox.indeterminate = selectedCount > 0 && selectedCount < selectableRows.length;
}

function appendEditableCell(rowEl, row, field, text, className = "", placeholder = "") {
  const td = document.createElement("td");
  const div = createEl("div", `editable-cell ${className}`.trim(), text || "");
  div.contentEditable = "true";
  div.spellcheck = false;
  div.dataset.field = field;
  div.dataset.original = text || "";
  if (placeholder) div.dataset.placeholder = placeholder;
  div.addEventListener("click", (event) => event.stopPropagation());
  div.addEventListener("focus", () => {
    div.dataset.original = div.innerText.trim();
  });
  div.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !(event.shiftKey && ["full_review", "simplified_review"].includes(field))) {
      event.preventDefault();
      div.blur();
    }
  });
  div.addEventListener("blur", () => {
    const nextValue = div.innerText.trim();
    if (nextValue === div.dataset.original) return;
    commitTableEdit(row, field, div).catch((error) => {
      console.error(error);
      alert(`无法保存表格修改：${error.message || error}`);
    });
  });
  td.appendChild(div);
  rowEl.appendChild(td);
}

function appendCountCell(rowEl, files, options = {}) {
  const td = document.createElement("td");
  const count = Array.isArray(files) ? files.filter(Boolean).length : 0;
  if (count && options.onContextMenu) {
    td.title = options.title || "右键打开所在文件夹";
    td.addEventListener("contextmenu", options.onContextMenu);
  }
  if (count && options.onClick) {
    const button = createEl("button", "file-count file-count-button", `${count} 个`);
    button.type = "button";
    button.title = options.title || "查看文件";
    button.addEventListener("click", options.onClick);
    td.appendChild(button);
  } else {
    const label = createEl("span", "file-count", count ? `${count} 个` : "无");
    td.appendChild(label);
  }
  rowEl.appendChild(td);
}

function initResizableTableColumns() {
  if (!els.reviewTable || els.reviewTable.dataset.resizableReady === "1") return;
  els.reviewTable.dataset.resizableReady = "1";
  const colgroup = document.createElement("colgroup");
  for (const width of TABLE_COLUMN_WIDTHS) {
    const col = document.createElement("col");
    col.style.width = `${width}px`;
    colgroup.appendChild(col);
  }
  els.reviewTable.prepend(colgroup);
  els.reviewTable.style.minWidth = `${TABLE_COLUMN_WIDTHS.reduce((sum, width) => sum + width, 0)}px`;

  const headers = Array.from(els.reviewTable.querySelectorAll("thead th"));
  headers.forEach((th, index) => {
    const grip = createEl("span", "column-resizer");
    grip.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const col = colgroup.children[index];
      const startX = event.clientX;
      const startWidth = parseFloat(col.style.width) || th.offsetWidth;
      grip.setPointerCapture?.(event.pointerId);
      const onMove = (moveEvent) => {
        const nextWidth = Math.max(MIN_TABLE_COLUMN_WIDTH, startWidth + moveEvent.clientX - startX);
        col.style.width = `${nextWidth}px`;
        const totalWidth = Array.from(colgroup.children).reduce((sum, item) => sum + (parseFloat(item.style.width) || MIN_TABLE_COLUMN_WIDTH), 0);
        els.reviewTable.style.minWidth = `${totalWidth}px`;
      };
      const onUp = () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    });
    th.appendChild(grip);
  });
}

async function playTableMedia(row) {
  await selectRow(row, false);
  setMode("review");
  const media = currentMediaElement();
  if (media) {
    const playPromise = media.play();
    if (playPromise?.catch) playPromise.catch(() => {});
  }
}

function highlightTableRow() {
  for (const rowEl of els.reviewTableBody.querySelectorAll("tr[data-row]")) {
    rowEl.classList.toggle("is-active", Number(rowEl.dataset.row) === state.currentRow);
  }
}

async function renderHistory() {
  els.shotGroupList.innerHTML = "";
  els.versionHistory.innerHTML = "";
  const visibleRows = new Set(visibleEntries().map((item) => item.row));
  const groups = Array.from(state.shotGroups.values()).filter((group) => group.rows.some((row) => visibleRows.has(row)));
  els.historyCount.textContent = `${groups.length} 个镜头`;

  if (!groups.length) {
    els.shotGroupList.appendChild(createEl("div", "empty-state", "没有匹配的镜头"));
    els.historyShotTitle.textContent = "未选择镜头";
    els.historyShotMeta.textContent = "没有匹配的版本历史";
    return;
  }

  if (!state.currentShotKey || !groups.some((group) => group.key === state.currentShotKey)) {
    state.currentShotKey = groups[0].key;
  }

  const activeGroup = state.shotGroups.get(state.currentShotKey);
  if (!activeGroup) return;
  ensureHistoryTreeExpanded(activeGroup);
  renderHistoryTree(groups);
  els.historyShotTitle.textContent = displayShotOnly(activeGroup);
  els.historyShotMeta.textContent = `${activeGroup.episode} / ${activeGroup.scene} · ${activeGroup.rows.length} 个版本 · ${activeGroup.rows.map((row) => state.entries[row].__versionLabel).join(" / ")}`;

  for (const row of activeGroup.rows) {
    const entry = state.entries[row];
    const card = createEl("article", `version-card ${row === state.currentRow ? "is-active" : ""} ${outcomeClass(entry)}`);
    const header = createEl("div", "version-card-header");
    const titleBlock = document.createElement("div");
    titleBlock.appendChild(createEl("div", "version-title", entry.__versionLabel || `版本 ${entry.__packageIndex + 1}`));
    titleBlock.appendChild(createEl("div", "version-meta", `${displayEpisode(entry)} · ${displayScene(entry)} · ${entry.timestamp || "-"} · ${entry.department || "未分类"} · ${entry.__sourceFile || ""}`));
    header.appendChild(titleBlock);
    const reviewButton = createEl("button", "", "审阅此版");
    reviewButton.type = "button";
    reviewButton.addEventListener("click", () => {
      selectRow(row);
      setMode("review");
    });
    header.appendChild(reviewButton);
    card.appendChild(header);

    const body = createEl("div", "version-body");
    const thumb = createEl("div", "version-thumb", "无截图");
    body.appendChild(thumb);
    fillHistoryThumb(thumb, entry);

    const copy = createEl("div", "version-copy");
    copy.appendChild(createEl("strong", "", "完整意见"));
    copy.appendChild(createEl("div", "", entry.full_review || "暂无完整意见"));
    copy.appendChild(createEl("strong", "", "整理结果"));
    copy.appendChild(createEl("div", "", entry.simplified_review || "暂无整理结果"));
    copy.appendChild(createEl("strong", "", "关键词"));
    copy.appendChild(createEl("div", "", Array.isArray(entry.keywords) && entry.keywords.length ? entry.keywords.join(", ") : "-"));
    body.appendChild(copy);
    card.appendChild(body);
    els.versionHistory.appendChild(card);
  }
}

function sceneTreeKey(episode, scene) {
  return `${episode}|${scene}`;
}

function ensureHistoryTreeExpanded(activeGroup) {
  if (!activeGroup) return;
  if (!state.expandedEpisodes.size) state.expandedEpisodes.add(activeGroup.episode);
  state.expandedEpisodes.add(activeGroup.episode);
  state.expandedScenes.add(sceneTreeKey(activeGroup.episode, activeGroup.scene));
}

function groupHistoryByEpisodeScene(groups) {
  const episodes = new Map();
  for (const group of groups) {
    if (!episodes.has(group.episode)) episodes.set(group.episode, new Map());
    const scenes = episodes.get(group.episode);
    if (!scenes.has(group.scene)) scenes.set(group.scene, []);
    scenes.get(group.scene).push(group);
  }
  return episodes;
}

function renderHistoryTree(groups) {
  const episodes = groupHistoryByEpisodeScene(groups);
  for (const [episode, scenes] of episodes.entries()) {
    const episodeRows = Array.from(scenes.values()).flat();
    const episodeOpen = state.expandedEpisodes.has(episode);
    const episodeButton = createEl("button", `history-tree-row history-episode ${episodeOpen ? "is-open" : ""}`);
    episodeButton.type = "button";
    episodeButton.addEventListener("click", () => {
      if (state.expandedEpisodes.has(episode)) state.expandedEpisodes.delete(episode);
      else state.expandedEpisodes.add(episode);
      renderHistory();
    });
    episodeButton.appendChild(createEl("span", "tree-caret", episodeOpen ? "▾" : "▸"));
    episodeButton.appendChild(createEl("span", "tree-title", episode));
    episodeButton.appendChild(createEl("span", "tree-count", `${episodeRows.length} 镜`));
    els.shotGroupList.appendChild(episodeButton);
    if (!episodeOpen) continue;

    for (const [scene, sceneGroups] of scenes.entries()) {
      const key = sceneTreeKey(episode, scene);
      const sceneOpen = state.expandedScenes.has(key);
      const sceneButton = createEl("button", `history-tree-row history-scene ${sceneOpen ? "is-open" : ""}`);
      sceneButton.type = "button";
      sceneButton.addEventListener("click", () => {
        if (state.expandedScenes.has(key)) state.expandedScenes.delete(key);
        else state.expandedScenes.add(key);
        renderHistory();
      });
      sceneButton.appendChild(createEl("span", "tree-caret", sceneOpen ? "▾" : "▸"));
      sceneButton.appendChild(createEl("span", "tree-title", scene));
      sceneButton.appendChild(createEl("span", "tree-count", `${sceneGroups.length} 镜`));
      els.shotGroupList.appendChild(sceneButton);
      if (!sceneOpen) continue;

      for (const group of sceneGroups) {
        const latestEntry = state.entries[group.rows[group.rows.length - 1]];
        const button = createEl("button", `shot-group ${group.key === state.currentShotKey ? "is-active" : ""} ${outcomeClass(latestEntry)}`);
        button.type = "button";
        button.addEventListener("click", () => {
          state.currentShotKey = group.key;
          const latestRow = group.rows[group.rows.length - 1];
          selectRow(latestRow, false);
          renderHistory();
        });
        button.appendChild(createEl("div", "shot-group-title", displayShotOnly(group)));
        const meta = createEl("div", "shot-group-meta");
        meta.appendChild(createEl("span", "", `${group.rows.length} 个版本`));
        meta.appendChild(createEl("span", "", group.rows.length > 1 ? "重复返修" : "单次出现"));
        button.appendChild(meta);
        els.shotGroupList.appendChild(button);
      }
    }
  }
}

async function fillHistoryThumb(container, entry) {
  const screenshot = entry.screenshot_path || entry.original_screenshot_path;
  const url = await assetUrl(screenshot, entry);
  if (!url || !isImage(screenshot)) return;
  container.textContent = "";
  const img = document.createElement("img");
  img.src = url;
  img.alt = entry.shot_number || "截图";
  container.appendChild(img);
}

function mediaCandidates(entry) {
  const media = Array.isArray(entry.media_files) ? entry.media_files.filter(Boolean) : [];
  if (entry.audio_path) media.push(entry.audio_path);
  if (!media.length && entry.screenshot_path) media.push(entry.screenshot_path);
  return media;
}

async function renderMedia(entry) {
  els.mediaStage.innerHTML = "";
  const candidates = mediaCandidates(entry);
  for (const relPath of candidates) {
    const url = await assetUrl(relPath, entry);
    if (!url) continue;
    if (isVideo(relPath)) {
      const video = document.createElement("video");
      video.src = url;
      video.controls = true;
      video.addEventListener("ended", playNext);
      els.mediaStage.appendChild(video);
      return;
    }
    if (isAudio(relPath)) {
      const audio = document.createElement("audio");
      audio.src = url;
      audio.controls = true;
      audio.addEventListener("ended", playNext);
      els.mediaStage.appendChild(audio);
      return;
    }
    if (isImage(relPath)) {
      const img = document.createElement("img");
      img.src = url;
      img.alt = entry.shot_number || "截图";
      els.mediaStage.appendChild(img);
      return;
    }
  }
  els.mediaStage.innerHTML = '<div class="empty-state">没有可预览媒体</div>';
}

async function copyText(text) {
  const value = String(text || "");
  if (!value) return;
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function isAbsoluteLocalPath(path) {
  const value = String(path || "").trim();
  return /^[a-zA-Z]:[\\/]/.test(value) || /^\\\\[^\\]+\\[^\\]+/.test(value) || value.startsWith("/");
}

function fileUrlForFolder(folder) {
  const normalized = String(folder || "").replace(/\\/g, "/");
  if (/^\/\//.test(normalized)) return `file:${normalized}`;
  if (/^[a-zA-Z]:\//.test(normalized)) return `file:///${encodeURI(normalized)}`;
  if (normalized.startsWith("/")) return `file://${encodeURI(normalized)}`;
  return "";
}

function packageSourcePath(entry) {
  const pkg = packageFor(entry);
  return pkg?.sourcePath || pkg?.fileName || entry?.__sourceFile || "";
}

function folderForAssetPath(path, entry) {
  const raw = String(path || "").trim();
  if (!raw) return "";
  if (isAbsoluteLocalPath(raw)) return localDirname(raw);
  const packagePath = packageSourcePath(entry);
  if (isAbsoluteLocalPath(packagePath)) {
    const packageFolder = localDirname(packagePath);
    const innerFolder = dirname(raw);
    return innerFolder ? `${packageFolder}/${innerFolder}` : packageFolder;
  }
  return dirname(raw);
}

async function openSystemFolderForPath(path, entry) {
  const folder = folderForAssetPath(path, entry);
  if (!folder) {
    els.projectMeta.textContent = "浏览器没有拿到可打开的本机文件夹路径";
    alert("当前浏览器没有提供这个文件的本机目录路径。");
    return;
  }
  await copyText(folder);
  const url = isAbsoluteLocalPath(folder) ? fileUrlForFolder(folder) : "";
  if (url) {
    window.open(url, "_blank");
    els.projectMeta.textContent = `已尝试打开文件夹，并复制路径: ${folder}`;
  } else {
    els.projectMeta.textContent = `已复制目录路径: ${folder}`;
    alert(`浏览器无法直接打开 revpack 内部目录，已复制目录路径：\n${folder}`);
  }
}

function requestOpenSystemFolder(path, entry) {
  openSystemFolderForPath(path, entry).catch((error) => {
    console.error(error);
    alert(`无法打开文件夹：${error.message || error}`);
  });
}

function firstPathFromFiles(files) {
  return Array.isArray(files) ? files.filter(Boolean)[0] || "" : "";
}

function sourcePathRows(entry) {
  if (!entry) return [];
  const rows = [];
  rows.push({ label: "revpack", value: packageSourcePath(entry) || "-", openable: true });
  const mediaFiles = Array.isArray(entry.media_files) ? entry.media_files.filter(Boolean) : [];
  for (const [index, relPath] of mediaFiles.entries()) {
    rows.push({ label: mediaFiles.length > 1 ? `媒体 ${index + 1}` : "媒体", value: relPath, openable: true });
  }
  if (entry.screenshot_path) rows.push({ label: "截图", value: entry.screenshot_path, openable: true });
  if (entry.original_screenshot_path && entry.original_screenshot_path !== entry.screenshot_path) {
    rows.push({ label: "原始截图", value: entry.original_screenshot_path, openable: true });
  }
  const refs = Array.isArray(entry.reference_files) ? entry.reference_files.filter(Boolean) : [];
  for (const [index, relPath] of refs.entries()) {
    rows.push({ label: refs.length > 1 ? `参考 ${index + 1}` : "参考", value: relPath, openable: true });
  }
  return rows.filter((item) => item.value);
}

function renderSourceInfo(entry) {
  els.detailSourceInfo.innerHTML = "";
  const rows = sourcePathRows(entry);
  if (!rows.length) {
    els.detailSourceInfo.textContent = "没有源文件路径";
    return;
  }
  for (const item of rows) {
    const row = createEl("div", "source-row");
    row.appendChild(createEl("span", "source-label", item.label));
    row.appendChild(createEl("code", "source-path", item.value));

    const actions = createEl("div", "source-actions");
    const copy = createEl("button", "", "复制");
    copy.type = "button";
    copy.addEventListener("click", async () => {
      await copyText(item.value);
      copy.textContent = "已复制";
      setTimeout(() => { copy.textContent = "复制"; }, 1200);
    });
    actions.appendChild(copy);

    if (item.openable) {
      const open = createEl("button", "", "打开文件夹");
      open.type = "button";
      open.addEventListener("click", () => requestOpenSystemFolder(item.value, entry));
      actions.appendChild(open);
    }
    if (item.openable) {
      row.title = "右键打开所在文件夹";
      row.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        requestOpenSystemFolder(item.value, entry);
      });
    }
    row.appendChild(actions);
    els.detailSourceInfo.appendChild(row);
  }
}

function renderDetail(entry, row) {
  if (!entry) {
    state.detailRow = -1;
    els.detailShot.textContent = "未选择镜头";
    els.detailDept.textContent = "";
    els.detailMetaLine.textContent = "-";
    els.detailVersionSelect.innerHTML = "";
    els.detailVersionSelect.disabled = true;
    els.detailSourceInfo.textContent = "未选择镜头";
    els.fullReview.textContent = "";
    els.simpleReview.textContent = "";
    updateApprovalButton(null);
    els.referencePreview.textContent = "无参考图片";
    els.referenceList.innerHTML = "";
    els.playerTitle.textContent = "审阅播放器";
    els.playerSubtitle.textContent = "选择一个镜头开始查看";
    return;
  }

  state.detailRow = row;
  const shot = entry.shot_number || `第 ${row + 1} 行`;
  els.detailShot.textContent = shot;
  els.detailDept.textContent = entry.department || "未分类";
  renderDetailVersionOptions(entry, row);
  const keywords = Array.isArray(entry.keywords) && entry.keywords.length ? entry.keywords.join(", ") : "-";
  const approvedLabel = isEntryApproved(entry) ? " · 已通过" : "";
  els.detailMetaLine.textContent = `${displayEpisode(entry)} · ${displayScene(entry)} · ${entry.timestamp || "-"} · ${keywords}${approvedLabel}`;
  els.fullReview.textContent = entry.full_review || "暂无完整意见";
  els.simpleReview.textContent = entry.simplified_review || "暂无整理结果";
  els.playerTitle.textContent = `审阅播放器 - ${shot}`;
  els.playerSubtitle.textContent = `${displayEpisode(entry)} · ${displayScene(entry)} · ${entry.__versionLabel || "当前版本"} · ${entry.timestamp || "-"} · ${entry.department || "未分类"}`;
  renderSourceInfo(entry);
  updateApprovalButton(entry);
  renderReferences(entry);
}

function renderDetailVersionOptions(entry, row) {
  const group = state.shotGroups.get(shotKey(entry));
  const rows = group?.rows?.length ? group.rows : [row];
  els.detailVersionSelect.innerHTML = "";
  els.detailVersionSelect.disabled = rows.length <= 1;
  for (const versionRow of rows) {
    const versionEntry = state.entries[versionRow];
    const option = new Option(
      `${versionEntry.__versionLabel || `版本 ${versionEntry.__packageIndex + 1}`} · ${versionEntry.timestamp || "-"}`,
      String(versionRow)
    );
    els.detailVersionSelect.appendChild(option);
  }
  els.detailVersionSelect.value = String(row);
}

async function selectDetailVersion(row) {
  const entry = state.entries[row];
  if (!entry) return;
  renderDetail(entry, row);
}

async function renderReferences(entry) {
  els.referencePreview.innerHTML = "";
  els.referenceList.innerHTML = "";
  const refs = Array.isArray(entry.reference_files) ? entry.reference_files.filter(Boolean) : [];
  renderAddReferenceControl(entry);

  if (!refs.length) {
    els.referencePreview.textContent = "暂无参考，可添加图片或视频";
    return;
  }

  await setReferencePreview(refs[0], entry);

  for (const relPath of refs) {
    const thumb = createEl("button", "reference-thumb");
    thumb.type = "button";
    thumb.title = basename(relPath);
    thumb.addEventListener("click", () => setReferencePreview(relPath, entry));
    const url = await assetUrl(relPath, entry);
    if (url && isImage(relPath)) {
      const img = document.createElement("img");
      img.src = url;
      img.alt = basename(relPath);
      img.addEventListener("dblclick", (event) => {
        event.stopPropagation();
        openMediaViewer(url, basename(relPath), "image");
      });
      thumb.appendChild(img);
    } else if (url && (isVideo(relPath) || isAudio(relPath))) {
      thumb.appendChild(createEl("span", "reference-media-badge", isVideo(relPath) ? "视频" : "音频"));
    } else {
      thumb.textContent = basename(relPath);
    }
    els.referenceList.appendChild(thumb);
  }
}

async function setReferencePreview(relPath, entry) {
  const url = await assetUrl(relPath, entry);
  els.referencePreview.innerHTML = "";
  if (!url) {
    els.referencePreview.textContent = "无法预览参考";
    return;
  }
  if (isVideo(relPath)) {
    const video = document.createElement("video");
    video.src = url;
    video.controls = true;
    video.addEventListener("dblclick", () => openMediaViewer(url, basename(relPath), "video"));
    els.referencePreview.appendChild(video);
    return;
  }
  if (isAudio(relPath)) {
    const audio = document.createElement("audio");
    audio.src = url;
    audio.controls = true;
    els.referencePreview.appendChild(audio);
    return;
  }
  if (!isImage(relPath)) {
    const open = createEl("button", "", "打开参考文件");
    open.type = "button";
    open.addEventListener("click", () => window.open(url, "_blank"));
    els.referencePreview.appendChild(open);
    return;
  }
  const img = document.createElement("img");
  img.src = url;
  img.alt = basename(relPath);
  img.title = "双击查看大图";
  img.addEventListener("dblclick", () => openMediaViewer(url, basename(relPath), "image"));
  els.referencePreview.appendChild(img);
}

function referenceAssetPath(entry, file) {
  const shot = sanitizeZipName(entry.shot_number || `row_${entry.__entryIndex + 1}`);
  const stamp = Date.now().toString(36);
  return `references/web_added/${shot}_${stamp}_${sanitizeZipName(file.name)}`;
}

async function addReferenceFiles(entry, files) {
  const pkg = packageFor(entry);
  const sourceEntry = sourceEntryFor(entry);
  if (!pkg || !sourceEntry) throw new Error("当前镜头没有可写入的源工程。");
  const list = Array.from(files || []).filter(Boolean);
  if (!list.length) return;
  if (!Array.isArray(entry.reference_files)) entry.reference_files = [];
  if (!Array.isArray(sourceEntry.reference_files)) sourceEntry.reference_files = [];
  for (const file of list) {
    const path = referenceAssetPath(entry, file);
    pkg.addedFiles.set(path, file);
    entry.reference_files.push(path);
    sourceEntry.reference_files.push(path);
  }
  renderSourceInfo(entry);
  await renderReferences(entry);
  await renderTimeline();
  await renderTable();
  await saveLocalProject({ silent: true });
  els.projectMeta.textContent = `已添加参考 · ${list.length} 个文件`;
}

function renderAddReferenceControl(entry) {
  const label = createEl("label", "reference-add-button", "添加参考");
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*,video/*";
  input.multiple = true;
  input.addEventListener("change", () => {
    addReferenceFiles(entry, input.files).catch((error) => {
      console.error(error);
      alert(`无法添加参考：${error.message || error}`);
    });
    input.value = "";
  });
  label.appendChild(input);
  els.referenceList.appendChild(label);
}

function closeImageViewer() {
  document.querySelector(".image-viewer-overlay")?.remove();
  document.removeEventListener("keydown", handleImageViewerKeydown, true);
}

function handleImageViewerKeydown(event) {
  if (event.key === "Escape") closeImageViewer();
}

function openImageViewer(url, title = "参考图片") {
  openMediaViewer(url, title, "image");
}

function openMediaViewer(url, title = "参考文件", kind = "image") {
  closeImageViewer();
  let scale = 1;
  const overlay = createEl("div", "image-viewer-overlay");
  const toolbar = createEl("div", "image-viewer-toolbar");
  toolbar.appendChild(createEl("span", "", title));
  if (kind === "image") {
    const zoomControls = createEl("div", "image-viewer-zoom");
    const zoomOut = createEl("button", "", "-");
    const zoomReset = createEl("button", "", "100%");
    const zoomIn = createEl("button", "", "+");
    zoomOut.type = zoomReset.type = zoomIn.type = "button";
    const applyScale = () => {
      const img = overlay.querySelector(".image-viewer-stage img");
      if (img) img.style.transform = `scale(${scale})`;
      zoomReset.textContent = `${Math.round(scale * 100)}%`;
    };
    zoomOut.addEventListener("click", () => {
      scale = Math.max(0.25, scale - 0.25);
      applyScale();
    });
    zoomReset.addEventListener("click", () => {
      scale = 1;
      applyScale();
    });
    zoomIn.addEventListener("click", () => {
      scale = Math.min(4, scale + 0.25);
      applyScale();
    });
    zoomControls.append(zoomOut, zoomReset, zoomIn);
    toolbar.appendChild(zoomControls);
  }
  const close = createEl("button", "", "关闭");
  close.type = "button";
  close.addEventListener("click", closeImageViewer);
  toolbar.appendChild(close);

  const stage = createEl("div", "image-viewer-stage");
  if (kind === "video") {
    const video = document.createElement("video");
    video.src = url;
    video.controls = true;
    video.autoplay = true;
    stage.appendChild(video);
  } else {
    const img = document.createElement("img");
    img.src = url;
    img.alt = title;
    stage.appendChild(img);
  }

  overlay.appendChild(toolbar);
  overlay.appendChild(stage);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay || event.target === stage) closeImageViewer();
  });
  document.body.appendChild(overlay);
  document.addEventListener("keydown", handleImageViewerKeydown, true);
}

function currentMediaElement() {
  return els.mediaStage.querySelector("video, audio");
}

function playCurrent() {
  const media = currentMediaElement();
  if (media) media.play();
}

function pauseCurrent() {
  const media = currentMediaElement();
  if (media) media.pause();
}

function playPrevious() {
  const index = state.filteredRows.indexOf(state.currentRow);
  if (index > 0) selectRow(state.filteredRows[index - 1]);
}

function playNext() {
  const index = state.filteredRows.indexOf(state.currentRow);
  if (index >= 0 && index < state.filteredRows.length - 1) {
    selectRow(state.filteredRows[index + 1]).then(playCurrent);
  }
}

function handleFiles(files) {
  const list = Array.from(files || []).filter(Boolean);
  if (!list.length) return;
  if (!guardProjectFileSize(list)) return;
  const projectFile = list.find((file) => file.name.toLowerCase().endsWith(".reviewhub"));
  if (projectFile) {
    loadReviewHub(projectFile).catch((error) => {
      console.error(error);
      els.projectMeta.textContent = "打开工程失败";
      alert(`无法打开网页工程：${error.message || error}`);
    });
    return;
  }
  loadFiles(list, { replace: false }).catch((error) => {
    console.error(error);
    els.projectMeta.textContent = "打开失败";
    alert(`无法打开审阅包：${error.message || error}`);
  });
}

els.fileInput.addEventListener("change", (event) => handleFiles(event.target.files));
els.projectInput.addEventListener("change", (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  loadReviewHub(file).catch((error) => {
    console.error(error);
    els.projectMeta.textContent = "打开工程失败";
    alert(`无法打开网页工程：${error.message || error}`);
  });
});
els.clearButton.addEventListener("click", clearViewer);
els.restoreLocalButton.addEventListener("click", restoreLocalProject);
els.saveLocalButton.addEventListener("click", () => saveLocalProject({ silent: false }));
els.exportRevpackButton.addEventListener("click", exportUpdatedRevpacks);
els.exportProjectButton.addEventListener("click", exportReviewHub);
els.exportTableButton.addEventListener("click", exportTable);
els.exportSelectedProjectButton.addEventListener("click", exportSelectedProject);
els.cgtwPreviewButton?.addEventListener("click", () => requestCgtwSync(true));
els.cgtwSyncButton?.addEventListener("click", () => requestCgtwSync(false));
els.selectAllRowsCheckbox.addEventListener("click", (event) => event.stopPropagation());
els.selectAllRowsCheckbox.addEventListener("change", () => {
  const rows = visibleRowIndexes();
  for (const row of rows) setRowSelected(row, els.selectAllRowsCheckbox.checked);
  renderTable().catch((error) => {
    console.error(error);
    alert(`无法更新选择状态：${error.message || error}`);
  });
});
els.reviewModeButton.addEventListener("click", () => setMode("review"));
els.tableModeButton.addEventListener("click", () => setMode("table"));
els.historyModeButton.addEventListener("click", () => setMode("history"));
els.focusReviewButton.addEventListener("click", () => setMode("review"));
els.openHistoryInReviewButton.addEventListener("click", () => setMode("review"));
els.approveShotButton?.addEventListener("click", () => {
  toggleCurrentApproval().catch((error) => {
    console.error(error);
    alert(`无法更新通过标记：${error.message || error}`);
  });
});
els.detailVersionSelect.addEventListener("change", (event) => {
  selectDetailVersion(Number(event.target.value)).catch((error) => {
    console.error(error);
    alert(`无法切换意见版本：${error.message || error}`);
  });
});
els.searchInput.addEventListener("input", renderTimeline);
els.episodeFilter.addEventListener("change", () => {
  renderFilters();
  renderTimeline();
});
els.sceneFilter.addEventListener("change", renderTimeline);
els.departmentFilter.addEventListener("change", renderTimeline);
els.statusFilter.addEventListener("change", renderTimeline);
els.prevButton.addEventListener("click", playPrevious);
els.playButton.addEventListener("click", playCurrent);
els.pauseButton.addEventListener("click", pauseCurrent);
els.nextButton.addEventListener("click", playNext);

for (const eventName of ["dragenter", "dragover"]) {
  els.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    els.dropZone.classList.add("is-over");
  });
}

for (const eventName of ["dragleave", "drop"]) {
  els.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    els.dropZone.classList.remove("is-over");
  });
}

els.dropZone.addEventListener("drop", (event) => {
  handleFiles(event.dataTransfer.files);
});

initResizableTableColumns();
clearViewer();

// Start Heartbeat to keep the local CGT Bridge server alive
setInterval(() => {
  fetch("http://127.0.0.1:8787/cgtw/heartbeat")
    .catch(() => {}); // Ignore errors if server is down
}, 5000);
