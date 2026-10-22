// Presentation-only localization. Patient IDs, raw readings, rules and API keys stay unchanged.
// Source messages are the catalog keys; add new UI messages here when extending the demo.
export const LANGUAGE_STORAGE_KEY = 'carelink-language';
let language = 'zh';
try { if (globalThis.localStorage?.getItem(LANGUAGE_STORAGE_KEY) === 'en') language = 'en'; } catch { /* Storage may be disabled. */ }
export function getLanguage() { return language; }
export function setLanguage(value) {
  language = value === 'en' ? 'en' : 'zh';
  try { globalThis.localStorage?.setItem(LANGUAGE_STORAGE_KEY, language); } catch { /* In-memory switching still works. */ }
  return language;
}

export const EN = Object.freeze({
  '安护 CareLink': 'CareLink', '安护': 'CareLink',
  '跳转至主要内容': 'Skip to main content',
  '安心照护中心': 'CareLink Care Center', '演示工作空间': 'Demo workspace',
  '工作台': 'Workspace', '主要导航': 'Main navigation',
  '患者总览': 'Patient overview', '关注与警报': 'Attention & alerts',
  '设备小屏': 'Device display', '演示规则': 'Demo rules',
  '先体验，再一起完善。': 'Try it. Then make it yours.',
  '切换演示场景': 'Demo scenarios', '演示医护人员': 'Demo clinician',
  'Pro 工作台': 'Pro workspace', '退出演示': 'Exit demo',
  '患者监测': 'Patient monitoring', '虚构数据': 'Mock data',
  '医护 Pro': 'Clinician Pro', '家属端': 'Family view',
  '打开演示控制台': 'Open demo controls', '关闭演示控制台': 'Close demo controls',
  '重试': 'Retry', '每一次关注，': 'Every moment of care',
  '都让安心更近一步。': 'brings peace of mind closer.',
  '连接每一份健康数据，': 'Keep health information connected.',
  '让专业照护与家人的牵挂，时刻相伴。': 'Bring professional care and family support together.',
  '安心守护': 'Care, connected', '跌倒与日常状态监测': 'Fall and daily activity monitoring',
  '心率': 'Heart rate', '血氧': 'SpO₂', '温度': 'Temperature',
  '模拟数据 · 仅作界面展示': 'Mock data · UI demonstration only',
  '专业视角，温暖连接': 'Professional care. A human connection.',
  'UI 原型体验': 'Interactive UI demo', '欢迎来到安护': 'WELCOME TO CARELINK',
  '把关心，连接起来': 'Keep care connected',
  '选择你的视角，开始体验健康监测工作台。': 'Choose your view to explore the monitoring workspace.',
  '选择演示身份': 'Choose a demo role', '医护人员': 'Clinician',
  '多患者 · 详细数据': 'Multiple patients · Detailed data',
  '患者 / 家属': 'Patient / family', '简单直观 · 安心查看': 'Clear, simple health updates',
  '演示账号': 'Demo account', '演示密码': 'Demo password',
  '固定演示表单，不验证身份。请勿输入真实账号或密码。': 'Demo form only; no identity verification. Do not enter real credentials.',
  '进入医护工作台': 'Enter clinician workspace', '进入家属端': 'Enter family view',
  '所有档案、读数均为虚构；未连接设备或 AI。': 'All profiles and readings are fictional. No devices or AI are connected.',
  '当前登录仅演示流程，正式使用需接入身份验证。': 'This sign-in demonstrates the flow only. Real use requires authentication.',
  '小组课程项目': 'Group coursework project', '用设计，照顾每一种需要。': 'Designed for every kind of care.',
  '优先查看': 'Review urgently', '需要关注': 'Needs attention', '数据平稳': 'Stable readings',
  '跌倒或严重数值异常': 'Fall or severe reading deviation',
  '轻度异常 · 无跌倒事件': 'Mild deviation · No fall event',
  '未见演示异常': 'No demo alerts', '当前没有优先警报': 'No urgent demo alerts',
  '请核实跌倒事件或异常读数，演示数据不代表真实健康状况。': 'Check the fall event or unusual reading. Mock data does not describe real health.',
  '持续关注数据质量，缺失数据不判为平稳。': 'Check data quality. Missing readings are never treated as stable.',
  '查看警报': 'View alerts', '部分数据待确认': 'Some data unverified',
  '未检测到跌倒事件': 'No fall detected', '模拟更新': 'Mock update',
  '最后采集': 'Last sample', '等待数据': 'Waiting for data',
  '查看详情': 'View details', '患者': 'Patient', '床位': 'Bed', '状态': 'Status',
  '详情': 'Details', '查看': 'View',
  '没有找到匹配的患者': 'No matching patients',
  '试试其他姓名、床位，或清除筛选。': 'Try another name or bed number, or clear the filters.',
  '清除筛选': 'Clear filters',
  '每一份数据背后，都有一位需要被关心的人。': 'Behind every reading is a person who matters.',
  '模拟更新 · 每 5 秒': 'Mock updates · Every 5 seconds',
  '模拟更新已暂停': 'Mock updates paused', '刷新数据': 'Refresh readings',
  '全部患者': 'All patients', '按关注优先级排序': 'Sorted by review priority',
  '搜索姓名、床位或编号': 'Search name, bed or ID', '搜索患者': 'Search patients',
  '按状态筛选': 'Filter by status', '全部': 'All', '优先': 'Urgent',
  '关注': 'Attention', '平稳': 'Stable', '待确认': 'Unknown',
  '卡片视图': 'Card view', '列表视图': 'List view', '模拟数据': 'Mock data',
  '跌倒监测': 'Fall monitoring', '检测到跌倒': 'Fall detected',
  '未检测到': 'Not detected', '暂不可用': 'Unavailable', '待人工核实': 'Needs human review',
  '最近 10 分钟趋势': 'Last 10 minutes: trends',
  '每 30 秒一条模拟记录 · 无效读数不连线': 'Mock samples every 30 seconds · Gaps indicate invalid readings',
  '当前没有可用的趋势数据': 'No usable trend data',
  '请检查设备连接与数据质量': 'Check the device connection and data quality',
  '最近 10 分钟数据': 'Last 10 minutes: readings',
  '上海时间 UTC+8 · 最新在前': 'Shanghai time (UTC+8) · Newest first',
  '导出 CSV': 'Export CSV', '采集时间': 'Sample time',
  '表面温度': 'Surface temperature', '跌倒事件': 'Fall event',
  '数据质量 / 时效': 'Quality / freshness', '待核实': 'Unverified',
  '无事件': 'No event', '设备离线（历史）': 'Device offline (historical)',
  '过期采集记录': 'Stale sample', '部分信号无效': 'Some signals invalid',
  '有效历史采样': 'Valid historical sample', '尚无历史数据': 'No history yet',
  '历史记录按采集时间展示；历史数值不代表当前状态。': 'History uses the original sample time. Past readings do not indicate current status.',
  '原始传感器数据': 'Raw sensor data', '模拟快照': 'Mock snapshot',
  '等待读数': 'Waiting for readings', '未做临床解释': 'No clinical interpretation',
  '离线 / 过期快照': 'Offline / stale snapshot',
  '加速度 m/s² · 角速度 °/s · 红光/红外为模拟原始计数。': 'Acceleration: m/s² · Angular velocity: °/s · Red/IR values are mock raw counts.',
  'AI 预测': 'AI predictions', '接口占位，未运行预测模型': 'Integration placeholder; no prediction model is running',
  '待接入': 'Not connected', '等待组员提供模型输出': 'Waiting for the team’s model output',
  '结果、置信度、模型版本及预测时间': 'Results, confidence, model version and prediction time',
  '接入后在此显示。': 'will appear here after integration.',
  '当前没有 AI 结论': 'No AI result available', '未找到患者': 'Patient not found',
  '返回总览': 'Back to overview', '返回患者总览': 'Back to patient overview',
  '虚构档案': 'Fictional profile', '仅按演示规则计算': 'Based on demo rules only',
  '详情内容': 'Patient detail sections', '监测概览': 'Monitoring overview',
  '历史记录': 'History', '原始数据与 AI': 'Raw data & AI',
  '尚无数据': 'No data yet', '设备待关联': 'Device not linked',
  '个人档案': 'Patient profile', '姓名 / 年龄': 'Name / age',
  '性别 / 床位': 'Sex / bed', '入住日期': 'Admission date',
  '过敏记录': 'Allergies', '既往病史 / 病例摘要': 'Medical history / case summary',
  '以上档案均为虚构': 'All profile information is fictional',
  '温度为 MLX90614 表面测温演示值，未转换为核心体温。AI 尚未接入，可在“原始数据与 AI”中查看预留结构。': 'Temperature is a mock MLX90614 surface reading, not core body temperature. AI is not connected; see Raw data & AI for the planned structure.',
  '异常读数、跌倒事件与数据质量，集中查看。': 'Review unusual readings, fall events and data quality in one place.',
  '刷新': 'Refresh',
  '标记“已查看”仅保存本次演示的查看记录，不清除跌倒事件，也不改变分级。': 'Marking an alert as viewed records this demo session only. It does not clear a fall event or change its priority.',
  '模拟事件': 'Mock event', '本地已查看': 'Viewed locally', '标记已查看': 'Mark as viewed',
  '当前没有待关注项目': 'No items need attention', '切换医护端': 'Clinician view',
  '把牵挂，放在身边': 'CARE THAT FEELS CLOSE', '今天，也在好好守护。': 'Here for your family, every day.',
  '查看家人的最新状态，让关心多一份安心。': 'See your family’s latest updates for a little more peace of mind.',
  '的健康小站': 'Health overview', '演示家人': 'Demo family member',
  '查看家人': 'Family member', '（虚构）': ' (fictional)',
  '目前数据平稳': 'Readings are currently stable',
  '有一项数据需要关注': 'A reading needs attention',
  '请尽快查看家人情况': 'Please check on your family member',
  '暂时无法确认完整状态': 'Some information is unavailable',
  '目前未检测到跌倒，三项数据处于演示平稳范围。': 'No fall detected. The three readings are within the demo’s stable ranges.',
  '设备提示可能跌倒，请查看本人情况并联系照护人员。': 'The device indicates a possible fall. Check on the person and contact their care team.',
  '有读数超出演示范围，请核实本人情况并联系照护人员。': 'A reading is outside the demo range. Check on the person and contact their care team.',
  '有读数超出演示平稳范围，建议告知照护人员并核实。': 'A reading is outside the demo’s stable range. Let the care team know and check the reading.',
  '部分数据无法读取，请检查设备连接或重新采集。': 'Some readings cannot be retrieved. Check the connection or collect a new sample.',
  '同时存在数据缺失，请检查设备。': 'Some readings are also missing. Please check the device.',
  '处于演示平稳范围': 'Within the demo’s stable range', '需要核实一下': 'Please check this reading',
  '表面测温 · 待校准': 'Surface reading · Calibration pending', '表面测温': 'Surface reading',
  '模拟读数': 'Mock reading', '可能跌倒': 'Possible fall',
  '请尽快查看本人情况': 'Please check on the person',
  '关注日常活动状态': 'Keeping track of daily activity',
  '设备提示需人工核实': 'Device alerts need human review',
  '最近一次数据更新': 'Last reading update', '还没有收到数据': 'No readings received yet',
  '模拟连接正常': 'Mock connection active', '当前状态待确认': 'Current status unverified',
  '刷新状态': 'Refresh status',
  '这是课程演示，所有人物与读数均为虚构。页面状态仅用于展示交互，不用于判断真实健康情况。温度为表面测温演示值。': 'Coursework demo: all people and readings are fictional. Statuses demonstrate interactions only and do not assess real health. Temperature is a mock surface reading.',
  '体验不同演示场景': 'Try demo scenarios', '小屏上的安心': 'Care on the small screen',
  'LCD 1602A 概念预览 · 16 列 × 2 行 · 英文缩写': 'LCD 1602A concept · 16 columns × 2 rows · English abbreviations',
  'LCD 第一行：': 'LCD row 1: ', '；第二行：': '; row 2: ',
  '暂停轮播': 'Pause rotation', '自动轮播': 'Auto-rotate', '下一页': 'Next page',
  '与网页共享同一份演示数据': 'Uses the same mock data as the web interface',
  '正在预览': 'Previewing', '适合两行屏幕的信息层级': 'Information for a two-line display',
  '默认轮播': 'Default rotation',
  'HR / O2 / SURF T 与跌倒状态页交替显示。SURF T 表示表面温度。': 'Alternate HR / O2 / SURF T with fall status. SURF T means surface temperature.',
  '警报优先': 'Alerts take priority',
  '跌倒事件锁定警报页；严重数值异常优先显示 VALUE ALERT。人工确认机制由后端与固件接入。': 'Fall events keep the alert page visible. Severe reading deviations prioritize VALUE ALERT. Acknowledgement requires backend and firmware integration.',
  '缺失就是缺失': 'Missing means missing',
  '无法采集时用 ---，离线或过期单独显示，避免旧数值看起来仍然有效。': 'Use --- for unavailable readings. Show offline and stale states explicitly so old values do not look current.',
  'KY-005 仅保留红外发射功能，不提供心率/血氧读数。此处为显示逻辑概念，尚未写入 ESP32。': 'KY-005 is retained for IR transmission and provides no HR/SpO₂ readings. This is a display concept, not ESP32 firmware.',
  '预览患者': 'Preview patient',
  '调整范围，观察三种状态颜色如何变化。': 'Adjust the ranges to explore how status colors change.',
  '仅本次会话生效': 'This session only',
  '以下数值只是可编辑的课堂交互示例，没有经过医学验证。温度字段是表面测温演示值。正式接入前需由项目负责人确定规则。': 'These editable values are classroom interaction examples, not medically validated thresholds. Temperature is a mock surface reading. The project lead must confirm rules before real integration.',
  '数值分级': 'Reading classification',
  '低于 / 高于边界时触发对应分级；等于边界时进入较低一级。': 'Readings below or above a boundary trigger that level. At the exact boundary, the lower severity applies.',
  '严重低值边界': 'Severe low boundary', '平稳范围下限': 'Stable range: lower limit',
  '平稳范围上限': 'Stable range: upper limit', '严重高值边界': 'Severe high boundary',
  '数据失效时间（秒）': 'Reading timeout (seconds)',
  '保存演示规则': 'Save demo rules', '恢复默认范围': 'Restore default ranges',
  '未处理跌倒事件，或有效读数严重异常。': 'An unresolved fall event, or a severe deviation in a valid reading.',
  '无跌倒，但有效读数轻度异常。': 'No fall event, but a mild deviation in a valid reading.',
  '全部有效且新鲜，没有触发演示异常。': 'All channels are valid and fresh; no demo alerts triggered.',
  '数据缺失、信号不稳、离线或过期；已知红/黄异常仍优先保留。': 'Missing, unreliable, offline or stale data. Known red/yellow alerts remain visible.',
  '演示控制台': 'Demo controls',
  '切换一位虚构患者的情况，观察医护端、家属端和小屏同步变化。': 'Change a fictional patient’s scenario and see it reflected in clinician, family and device views.',
  '演示患者': 'Demo patient',
  'KY-005 模式会停用心率与血氧，不会生成替代测量值。': 'KY-005 mode makes HR and SpO₂ unavailable. It does not generate replacement measurements.',
  '暂停模拟更新（可测试过期状态）': 'Pause updates (test stale data)',
  '恢复每 5 秒模拟更新': 'Resume updates every 5 seconds',
  '重置所有演示数据': 'Reset all demo data',
  '本控制台仅改变本页内存中的虚构数据，刷新页面恢复默认。': 'Changes affect this page’s mock data only. Reloading restores the defaults.',
  '数据加载失败，请重试。': 'Unable to load readings. Please retry.',
  '数据未能加载，请点击重试。': 'Readings could not be loaded. Select Retry.',
  '数据更新失败，已有读数可能过期。': 'Update failed. Existing readings may be stale.',
  '已导出最近十分钟模拟记录（包含质量字段）': 'Exported the last 10 minutes of mock data, including quality fields.',
  '已在本次演示中标记查看，警报分级仍保留': 'Marked as viewed for this session. Alert priority is unchanged.',
  '已切换为：': 'Scenario changed to: ', '模拟数据已刷新': 'Mock readings refreshed',
  '已恢复默认虚构数据': 'Default mock data restored',
  '已恢复默认演示规则': 'Default demo rules restored',
  '已进入演示，未进行身份验证': 'Demo opened. No identity verification was performed.',
  '请检查边界顺序：严重低值 < 平稳下限 < 平稳上限 < 严重高值；血氧范围须在 0–100 之间。': 'Check the order: severe low < stable lower < stable upper < severe high. SpO₂ limits must be between 0 and 100.',
  '演示规则已更新，仅本次会话有效': 'Demo rules updated for this session only.',
  '数据待确认': 'Data unverified', '尚无读数': 'No readings yet',
  '跌倒监测暂不可用': 'Fall monitoring unavailable',
  '检测到跌倒事件 · 待人工核实': 'Fall event detected · Needs human review',
  '数据已过期': 'Reading is stale', '设备离线': 'Device offline',
  '信号不稳 · 请重新采集': 'Unreliable signal · Collect a new sample',
  '信号不稳': 'Unreliable signal', '超出演示严重范围': ' outside the severe demo range',
  '超出演示平稳范围': ' outside the stable demo range',
  '各项数据处于演示平稳范围': 'All readings are within the demo’s stable ranges',
  '轻度异常': 'Mild deviation', '严重异常': 'Severe deviation',
  '跌倒警报': 'Fall alert', 'MAX 信号不稳': 'MAX signal unreliable',
  'KY-005 备用模式': 'KY-005 fallback mode', '数据过期': 'Stale readings',
  '高血压病史；定期随访。': 'History of hypertension; regular follow-up.',
  '慢性呼吸系统疾病史；需关注日常活动。': 'History of chronic respiratory disease; monitor daily activity.',
  '术后康复期；步行时使用辅助器具。': 'Postoperative rehabilitation; uses a walking aid.',
  '无特殊既往史（演示档案）。': 'No notable medical history (fictional profile).',
  '高血压病史；规律复诊。': 'History of hypertension; routine follow-up visits.',
  '糖尿病病史；日常随访中。': 'History of diabetes; ongoing routine follow-up.',
  '关节活动受限；日常活动需陪同。': 'Limited joint mobility; needs support with daily activities.',
  '未记录（演示）': 'Not recorded (demo)',
  '林知秋': 'Lin Zhiqiu', '周远山': 'Zhou Yuanshan', '陈静禾': 'Chen Jinghe',
  '许望舒': 'Xu Wangshu', '沈怀川': 'Shen Huaichuan', '陆青禾': 'Lu Qinghe',
  '顾云舟': 'Gu Yunzhou', '苏晚晴': 'Su Wanqing',
  '女': 'Female', '男': 'Male', '林': 'L', '周': 'Z', '陈': 'C',
  '许': 'X', '沈': 'S', '陆': 'L', '顾': 'G', '苏': 'S', '演': 'D',
  '位': 'patients', '无': 'None',
  '课程项目演示 v1.0': 'Coursework demo v1.0',
  '所有人物与读数均为虚构 · 规则仅用于演示交互': 'All people and readings are fictional · Rules demonstrate interactions only',
  '切换至中文': 'Switch to Chinese',
  'Pro 医护端':'Pro', 'Basic 家属端':'Basic', 'Pro 医护人员':'Pro · Clinician', 'Basic 患者 / 家属':'Basic · Patient / family', '切换 Pro 模式':'Switch to Pro'
});
const escapeRegExp = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const catalogPattern = new RegExp(Object.keys(EN).sort((a,b)=>b.length-a.length).map(escapeRegExp).join('|'), 'gu');

export function translate(source, locale = language) {
  const text = String(source ?? '');
  if (locale !== 'en') return text;
  // Dynamic messages use explicit patterns, before catalog fragments are resolved.
  let value = text
    .replace(/^(心率|血氧|温度)(信号不稳|暂不可用|超出演示严重范围|超出演示平稳范围)$/, (_, metric, quality) => `${translate(metric,'en')}: ${translate(quality,'en').trim()}`)
    .replace(/^查看(.+)详情，(.+)$/, (_, name, status) => `View ${translate(name,'en')}: ${translate(status,'en')}`)
    .replace(/^(.+)的虚构头像$/, (_, name) => `Fictional avatar for ${translate(name,'en')}`)
    .replace(/^(.+)最近十分钟模拟趋势，最低 ([\d.]+)，最高 ([\d.]+) (.+)$/, (_, metric, min, max, unit) => `Mock ${translate(metric,'en')} trend over 10 minutes; minimum ${min}, maximum ${max} ${unit}`)
    .replace(/(\d+) 位患者需要优先查看/g, (_, count) => `${count} ${count==='1'?'patient needs':'patients need'} urgent review`)
    .replace(/(\d+) 位数据待确认/g, (_, count) => `${count} ${count==='1'?'patient':'patients'} with unverified data`)
    .replace(/(\d+) 条模拟采样/g, '$1 mock samples')
    .replace(/(\d+)\s*岁/g, '$1 years')
    .replace(/([\d-]+) 床/g, 'Bed $1')
    .replace(/(\d+) 位/g, (_, count) => `${count} ${count==='1'?'patient':'patients'}`)
    .replace(/第 (\d+) \/ (\d+) 页 · 每 3 秒/g, 'Page $1 / $2 · Every 3 seconds');
  value = value.replace(catalogPattern, match => EN[match]);
  return value.replace(/’/g, "'");
}

export function languageButton() {
  const english = language === 'en';
  return `<button type="button" class="language-switch" data-action="language" aria-label="${english?'Switch to Chinese':'Switch to English'}" lang="${english?'zh-CN':'en'}">${english?'中文':'English'}</button>`;
}

// Translate text and human-readable attributes only. Never rewrite HTML, values,
// data attributes, raw JSON, LCD character cells, IDs or any business state.
export function localizeDom(root, locale = language) {
  if (locale !== 'en') return;
  const doc = root.ownerDocument;
  const walker = doc.createTreeWalker(root, 4); // SHOW_TEXT
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    if (node.parentElement?.closest('pre, script, style, .lcd-line, .language-switch')) continue;
    node.textContent = translate(node.textContent, locale);
  }
  for (const el of [root, ...root.querySelectorAll('*')]) {
    for (const attr of ['aria-label', 'placeholder', 'title', 'alt']) {
      if (el.hasAttribute(attr)) el.setAttribute(attr, translate(el.getAttribute(attr), locale));
    }
  }
}

export function localizePageChrome() {
  document.documentElement.lang = language === 'en' ? 'en' : 'zh-CN';
  document.title = language === 'en' ? 'CareLink · Health monitoring demo' : '安护 CareLink · 健康监测演示';
  const skip = document.querySelector('.skip');
  if (skip) skip.textContent = translate('跳转至主要内容');
  document.querySelector('meta[name="description"]')?.setAttribute('content', language === 'en'
    ? 'Coursework UI demo with clinician, family and LCD 1602A views. All people and readings are fictional.'
    : '安护健康监测课程演示。医护端、家属端与 LCD 1602A，全部使用虚构数据。');
}
