# CareLink 第二阶段安全修复报告

日期：2026-10-30（Asia/Shanghai）。**最终结论：NO-GO。**

第1–8节保留上一轮记录；当前修复及重新运行的证据以第9节为准。

工作树：`/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic`；分支 `fix/nonce-atomic-freeze-20261029`。上一轮报告 [CARELINK-FINAL-SECURITY-AUDIT-20261030.md](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/CARELINK-FINAL-SECURITY-AUDIT-20261030.md) 保留，以下为本轮实际实现与重新执行的结果，不把历史数量当成本轮证据。

## 1. 执行摘要

- iOS Core 的原始差异已经修复：JS 把“界面展示哪些指标”误用于“检查哪些有效指标”，漏掉 SpO₂；本轮加强 JS 对有效低血氧的演示检查，没有把 Swift 红色告警改成绿色。缺少可选 SpO₂ 的实际后端记录可正确解码，null 心率保持 null。
- 新增实际可调用的 Keychain 存储、独立临时 URLSession、严格 TLS、原生登录/恢复/轮换/注销与 UI 接线。仍使用后端现有 Cookie Session、CSRF/Origin 和 `/api/*` 契约，不引入新认证协议。
- 补上在途响应与共享凭据更换约束；退出/失效清空本机身份与内存Token，旧响应不能复活身份或删除另一客户端刚替换的凭据。
- 后端增强数据库/侧文件/控制目录的路径隔离，覆盖切换后的 active/candidate/previous 和最初源；运行时不静默创建丢失读数库。
- 新安装工具拒绝遗留 `.control`，即使主库和 marker 都已丢失也不能因此当作新安装。新增冻结后完整备份验证命令，逐条比较全部历史字段，不能只比条数。
- 真实写入者覆盖、真实备份可信性、真实恢复/回滚仍为 **NOT VERIFIED**。本轮没有访问真实服务、账本、账号库、生产凭据或证书，没有刷写/连接硬件，没有提交、推送、合并。
- Android 工程/APK不在允许工作树中；不凭空搭建另一套客户端来假装已加固。完整 Xcode/iOS SDK/模拟器和真机不可用，iPhone Keychain 持久化与 SwiftUI 完整构建尚未验收。

上一轮 accepted 证据结果（P2 复核前）：Python **230/230**（失败0、错误0、跳过0）；Node **20**、React **32**；Swift Core **118**、原生认证/存储接口 **81**、原生 TLS/实际隔离后端 **19**。数字分别属于不同套件，不能相加为覆盖率。命令及退出码见第6节。

## 2. 基线、失败证据与修复记录

### R1. 原始 iOS Core 失败与指标兼容

修改前不可变源快照重放退出SIGTRAP（原生-5，shell等效133），确切断言 `JS/Swift status parity: spo2-89.9`：[immutable-baseline-core.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/immutable-baseline-core.log)、[immutable-baseline-core.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/immutable-baseline-core.json)。与上一轮保存的失败一致。早期名为 `core-baseline.log` 的运行与编辑并行、读取了更新后的共享向量，不作为干净前态证据；前态以保存的源散列和不可变快照重放为准。

根因及修复：

1. `dist/rules.js` 的UI指标列表只含心率/温度，却用于所有演示分级。新增独立逻辑：存在且没有显式标记不可用的可选SpO₂也要检查。保留原阈值；新增独立严重值断言，然后重新生成黄金向量。没有删除原向量或放宽阈值。
2. 实际Python/TS契约允许SpO₂缺席，Swift却要求必填。Swift对缺席值构造不可用指标，不生成0；有字段但类型错误仍拒绝。共享schema/契约文档同步实际API，线上的API格式未变。
3. Core测试从已确认的共享配置读取 `apiConfirmed=true`，却拿它测试“未确认必须拒绝”；现显式设置false。历史query断言硬编码10分钟，但配置为1440，现验证实际配置的query，同时保留客户端十分钟过滤断言。这两处是夹具漂移，不是关闭安全断言。
4. 新增“有效严重SpO₂仍为red”和“明确不存在的可选传感器不制造必填要求”的独立Swift检查。一次开发用例误取自带异常的患者夹具，失败日志保留；改用明确normal夹具，未改期望结果。

证据：[rules-before.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/rules-before.log)、[rules-after.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/rules-after.log)、[core-contract-corrected.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/core-contract-corrected.log)（开发夹具失败）、[accepted-ios-core.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/accepted-ios-core.log)。当前完整Core 118项通过。真实数据模式仍以服务端assessment为准，不把演示规则冒充临床判断。

### R2. 原生认证、Keychain、TLS和真实调用链

原树只有读取现成Session，未实现登录、Keychain和远端注销，还允许HTTP。现链路为：

```text
LoginView SecureField
 → DemoStore.signIn
 → LiveApiService.authenticate
 → HTTPS /api/login + JSON + Origin + X-CareLink-CSRF
 → 验证Set-Cookie的Secure/HttpOnly/SameSite/Path/Max-Age与Token格式
 → KeychainSessionStore（WhenUnlockedThisDeviceOnly、不同源分开、不云同步）
 → 每个请求显式Cookie，禁用共享Cookie/磁盘缓存
 → 服务器返回角色/患者范围 → 客户端检查范围 → 页面显示
```

- 原生API请求只允许HTTPS origin；拒绝重定向，不把凭据转发到另一主机。最低TLS1.2；默认系统信任，或显式公开DER根。自定义信任仍用SSL主机策略、受限根和 `SecTrustEvaluateWithError`，检查链及有效期；没有信任所有证书或HTTP回退。
- 重建客户端时先读取安全存储，再向实际Session接口验证；本地到期/格式错误会删除，不根据缓存角色直接恢复。401撤销本地身份。会话轮换使用现有 `/api/session/rotate` 并保留服务端绝对到期限制。
- 退出先清理页面，再请求服务端撤销并清理Keychain；网络失败明确报告服务器撤销未确认。离线无法保证远程即时撤销，不能误报成功。存储完全不可用时也会明确失败，禁止明文fallback。
- 以请求generation阻断退出/切换后的迟到响应；内存身份绑定所用Token，Keychain凭据变化后不能继续使用旧角色；旧401不删除另一个客户端替换后的凭据。
- UI接入账号密码，密码只在输入与请求内存中使用；不保存在Store、配置、UserDefaults或日志。UserDefaults仅语言偏好。修复DemoStore残留的无效Scenario分支，补充本地网络用途说明。
- Xcode sources实际包含新安全文件；资源改为明确的、本地被忽略的iOS配置，提供无凭据模板，避免直接打包Web的相对URL配置。

自动化边界：81项认证/存储接口测试使用 **MemorySessionStore测试替身**，不证明OS Keychain持久化。实际Keychain代码调用SecItem系列API并在macOS编译；早期未注入测试存储的无签名CLI运行得到 `credentialStorage`，没有保存足以确认底层OSStatus的证据，也没有当成Keychain成功验收。之后测试均显式使用测试替身，未读取/写入正式Keychain条目。iPhone签名、锁定/解锁、卸载/重装、备份迁移及实际凭据持久化继续 **NOT VERIFIED**。

实际原生网络测试用临时CA和临时FastAPI，验收登录、受保护患者API、客户端对象重建后重新验证、Token轮换、旧Token401、退出后复制Token401、缺凭据401、错误主机、过期证书和未信任根拒绝，以及缺可选指标/null心率。结果：[accepted-ios-tls.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/accepted-ios-tls.log)。不是ESP32、真实网关或真机验收。首轮合成CA扩展不完整造成严格链验证失败，日志保留；补齐CA/KU/SKI/AKI后通过，没有放宽SSL验证设置。

### R3. 数据库隔离与运行时丢库保护

原先AuthStore只检查环境中旧nonce路径，没有覆盖控制器已切换的新账本；readings初始化也缺少交叉存储检查。新增 `storage_paths.validate_storage_paths`，先于SQLite连接/建表核查：

- auth/readings彼此独立，不能硬链接或路径别名；
- 不能选择当前、候选、前一代、最初inventory源及配置旧账本的主文件、WAL/SHM/journal、marker/intent/control；
- auth/readings不能落在控制目录内，不能把控制状态当数据库；
- 控制配置失效不忽略、不回退；
- 运行时readings连接使用 `mode=rw`，文件丢失不新建。首次初始化仍是受gate约束的显式启动步骤，新文件0600；没有修改已有真实数据库权限。

测试覆盖切换后旧配置、跨多次切换原源、侧文件、控制状态、auth/readings/ledger互相混选，以及运行时缺库。冻结时设备与告警503，独立账号库仍可限流、创建/撤销Session，nonce和读数零增量。明确把两种存储域分开，未声称认证库被nonce gate冻结。

### R4. 首次初始化误接管遗留管理环境

`initialize_new_ledger` 的原artifact列表没有 `.control`，主库和marker丢失后即使仍有控制绑定，人工“新安装”也可能建空库。确定性用例修复前失败：[orphan-binding-before.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/orphan-binding-before.log)。现在把 `.control` 也作为拒绝条件，原文件原样保留、不建DB/marker/intent。修复后nonce recovery 51项通过：[orphan-binding-fixed.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/orphan-binding-fixed.log)。整套本地证据都丢失时仍不能证明新安装，操作手册禁止将初始化当恢复。

### R5. 完整备份校验、旧工具边界与回归夹具

- 新增 `Controller.verify_backup` / CLI `verify-backup`：要求FROZEN且checkpoint非null，持admin/exclusive gate与源writer事务，核对v2格式和marker，再逐条比较四列完整历史。拒绝过期、内容不同但条数相同、坏marker、权限不符和源缺失；不恢复、不切换、不resume。当前权威源不存在时，不假设备份可信。
- CLI在合成完整备份返回0；相同条数但改过历史字段返回1，状态保持FROZEN。原有迁移中断、并发切换、进程退出及最新完整快照的恢复模拟也重新执行。
- 旧readiness工具无参数就读取私有路径且含真实端口探测。现在先要求绝对config-root与显式检查确认，网络选项直接拒绝；本轮只对临时目录测试拒绝行为，没有用它读取真实材料。
- 新路径保护暴露旧 `test_api` 在模块导入时修改全局环境、删除临时目录后不恢复的问题：第一轮完整回归229项中190通过、39错误，伴随临时目录清理警告。保留 [final-python.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/final-python.log)，未弱化路径检查。修复为测试类范围环境和DATABASE_PATH补丁、addClassCleanup；三个账号单元夹具也在任何可能失败步骤前注册清理并隔离CARELINK环境。顺序回归86项通过：[fixture-order-fixed.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/fixture-order-fixed.json)。
- 完整安全测试入口改自动发现，不再因新模块加入而遗漏；开启资源警告并将捕获到的警告计入失败，不打印可能包含秘密的异常值。私有审计快照目录已Git忽略，旧证据未删除。

## 3. 写入者覆盖矩阵

下表配置来源由实际源码核对；**不是实际生产路径确认**。真实服务禁止访问，因此所有“真实覆盖”均NOT VERIFIED。

定义：`D=CARELINK_DATABASE_PATH`，源码fallback为本树`backend/carelink.db`；`A=CARELINK_AUTH_DATABASE_PATH`，fallback为本树`.secrets/web-auth.sqlite3`；`L=Controller(state.active)`；旧`CARELINK_DEVICE_NONCE_DB`只作为额外保护/历史配置，不能覆盖gate权威选择；`C=CARELINK_LEDGER_CONTROL_ROOT`。认证、读数与nonce路径现在动态核验独立。

|入口/写入者|目标/配置来源|写操作|冻结或事务控制|旁路/边界|隔离状态与证据|真实覆盖|
|---|---|---|---|---|---|---|
|三种`/sensor-data`接收入口|L、D|nonce INSERT+计数；读数/告警INSERT/UPDATE|同一UnifiedWriteGate共享租约，FULL nonce提交后receipt准入|旧代码必须更新，不能只停新入口|PASS；atomic分阶段及新旧入口测试|NOT VERIFIED|
|直接receive_sensor_data|D|读数/告警写入|guarded_write、一次receipt、受控连接/游标|普通dict/其他账本receipt拒绝|PASS|NOT VERIFIED|
|`GET /api/alerts`连接告警更新|D|告警INSERT/UPDATE|HTTP gate + guarded_write|GET也可能写，不是只读API|PASS；冻结503与零增量|NOT VERIFIED|
|告警确认POST|D|UPDATE|gate、服务端Session/clinician/scope、租约|客户端角色不能授权|PASS|NOT VERIFIED|
|startup readings/alerts建表|D|CREATE TABLE/INDEX、PRAGMA|guarded_write，路径隔离；新文件0600|FROZEN启动可能失败，不得放开|PASS|NOT VERIFIED|
|NonceStore.reserve/绑定连接|L|唯一nonce INSERT、metadata计数|受控绑定、BEGIN IMMEDIATE、FULL、唯一键、租约|未绑定新安装原语不是生产写入通道|PASS；2/32/64/双进程32|NOT VERIFIED|
|用户限流|A|INSERT/UPDATE/到期桶DELETE|独立BEGIN IMMEDIATE，有界桶|明确不受设备gate；必须与L/D分离|PASS；冻结时仍生效|NOT VERIFIED|
|登录/渐进密码迁移|A|用户hash CAS、Session INSERT/旧Token撤销|独立事务、服务端凭据校验|不重置ttj/wyn；不能在nonce迁移中回滚A|PASS|NOT VERIFIED|
|Session轮换/退出/过期查询|A|新摘要INSERT、UPDATE revoked/replacement；SELECT|独立原子事务及到期校验|旧A备份可能复活撤销状态，需独立恢复方案|PASS；Python与原生TLS|NOT VERIFIED|
|密码更新/账号准备工具|A，由CLI显式路径指定|DDL、hash替换、Session撤销|交互式getpass、授权确认、认证库事务|无生产操作；无自动密码轮换|PASS；原有合成测试保留|NOT VERIFIED|
|controller enroll/freeze/prepare/switch/recover/resume|C、L、独立generation|控制文件原子发布、DDL/完整历史复制|admin锁、gate EX、源SQLite writer事务、checkpoint|inventory是真实人工核验输入，不是自动进程证明|PASS；合成中断/重复/并发演练|NOT VERIFIED|
|verify-backup|C、权威L、显式备份|校验及无数据更改事务|FROZEN+已排空checkpoint+全历史相等|不证明源已丢失后的外部最新性|PASS；CLI 0/1|NOT VERIFIED|
|新安装initialize工具|显式新L|新schema/marker/intent|授权短语、O_EXCL、全部遗留artifact拒绝|不能用于既有环境恢复|PASS；新增.control回归|NOT VERIFIED|
|旧readiness检查工具|显式config-root中的只读路径|只读查询；旧默认入口被限制|明确批准且拒绝网络mode|不是运行版本或所有写入者证明|PASS；拒绝测试|NOT VERIFIED|
|旧启动脚本、Node模拟器|配置入口指向app或HTTP发送|实际写入最终由接收端处理|更新app会要求TLS/HMAC/gate|脚本仍是历史开发启动器，不是安全发布包|PARTIAL；未执行启动|NOT VERIFIED|
|测试脚本/临时服务|新建合成目录|完整夹具/随机loopback服务|TempDirectory、显式环境、独立进程清理|不属于真实写入者|PASS|NOT VERIFIED|
|未知进程、外部直接SQLite程序、监督器旧版本|未知|未知SQL|不能从源码强迫其遵守gate|部署阻塞，须逐项OS现场取证|NOT VERIFIED|NOT VERIFIED|

## 4. 冻结、备份与恢复演练

原有37项迁移控制与51项nonce recovery连同新增18项范围/备份/工具策略测试都纳入最终发现；它们是完整Python套件的子集，不能再相加。用户要求的并发认证结果、nonce提交、HTTP、业务调用和读数增量分别断言，详见 [accepted-python.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/accepted-python.json) 的 `concurrency` 与 `recovery`。

|合成场景|原状态/操作|预期|本轮验证方式|
|---|---|---|---|
|合法完整迁移|非空v1→FROZEN→COPYING→VERIFIED→SWITCHED→ACTIVE|全部四列完全相等，原源保留|原有完整迁移用例重跑|
|在途未排空|共享租约仍持有，freeze超时|FROZEN/null，prepare/verify禁止|gate与备份测试|
|完整冻结备份|当前完整v2及准确marker|verify成功，无history变化|CLI实际0，phase保持FROZEN|
|同条数内容改变|备份改signed_at/accepted_at，仍保持schema及计数|拒绝，不能仅比count|CLI实际1及直接函数拒绝|
|备份落后|备份后消费新nonce，再冻结|旧备份拒绝|verify和prepare都拒绝|
|权威源缺失|存在备份，但source消失|不重建、不从备份猜恢复|路径保持缺失；备份保留|
|坏marker/权限|ID错配或文件0400|拒绝、不chmod|FROZEN保持|
|部分替换/中断/进程崩溃|COPYING/VERIFIED/SWITCHED中断|不自动ACTIVE，权威历史保持|原有异常退出及recover-frozen测试|
|两个管理进程|一方持admin锁|另一方verify拒绝；释放后可验证|新进程竞争测试|
|最新完整快照恢复模拟|冻结、验证、独立generation恢复、切换|逐条历史相等，旧nonce409|新恢复模拟及原有最新快照用例|
|遗留control但无ledger|误调用新安装|503拒绝，不生成空账本|新增确定性回归|

只有当前权威源还完整，工具才能证明备份与冻结历史一致；没有独立外部最新证据时，整套旧文件一起回滚仍无法由本地自洽识别。真实备份、真实恢复、真实回滚能力没有被本轮测试证明。

## 5. 更新后的安全控制矩阵

对应上一轮C编号。“实现/自动化通过”与“部署及真机通过”严格分开。

|控制|本轮源码/隔离状态|真实部署或设备状态|总体|剩余风险/证据|
|---|---|---|---|---|
|C01 独立分支与工作区|PASS|NOT VERIFIED|PARTIAL|保留全部原源和未提交修改；没有最小生产发布包|
|C02–C03 Argon2id及原密码渐进迁移|PASS|NOT VERIFIED|PARTIAL|原密码保留；正式账号库未读、未部署|
|C04–C05 Session随机、摘要、撤销、过期/重启|PASS|NOT VERIFIED|PARTIAL|Python完整回归与原生TLS正反向；认证库回滚需独立最新撤销证据|
|C06–C09 Cookie/CSRF/CORS/限速/权限|PASS|NOT VERIFIED|PARTIAL|原生正确Cookie与Origin接入；实际生产配置未读取|
|C10–C13 HMAC、时间窗、nonce原子占用、receipt|PASS|NOT VERIFIED|PARTIAL|独立计数，不只最终行数；未对9443攻击|
|C14 fail-closed初始化/恢复|PASS|NOT VERIFIED|PARTIAL|新增遗留.control拒绝；不可把历史丢失当新安装|
|C15 统一冻结/在途排空|PASS|NOT VERIFIED|PARTIAL|源码域内覆盖，未知/旧实际写入者未核验|
|C16 连接/游标与数据库归属|PASS|NOT VERIFIED|PARTIAL|租约保留，补齐动态路径别名/丢库保护|
|C17–C19 转换、完整备份、恢复/回滚|PASS（合成技术验证）|NOT VERIFIED|PARTIAL|外部可信最新性、真实备份和真正回滚仍阻塞|
|C20 TLS链/主机/有效期|PASS（临时CA及原生网络）|NOT VERIFIED|PARTIAL|真实证书、SAN、当前网络及入口版本未查|
|C21 Web回归|PASS|NOT VERIFIED|PARTIAL|同轮Node/React/构建，无真实Web数据验收|
|C22 Android Keystore/构建|NOT VERIFIED|NOT VERIFIED|NOT VERIFIED|本树无Android工程/APK，默认SDK目录无可用平台/构建工具证据；未安装或改环境|
|C23 iOS安全链|PASS（实现、编译、接口/网络测试）|NOT VERIFIED|PARTIAL|Keychain设备持久化、完整SwiftUI构建与真机仍缺证据；离线退出远端撤销不能保证|
|C24 iOS Core规则|PASS|NOT VERIFIED|PARTIAL|Core 118通过；完整Xcode/iOS SDK不可用，不能等同App构建|
|C25 秘密、日志、产物、业务|PARTIAL|NOT VERIFIED|PARTIAL|本轮测试无真实秘密；历史公开校验值风险保留；真实数据/日志/APK没读|

## 6. 上一轮 accepted 完整回归（保留历史证据）

|命令|退出码|实际结果|警告行数|完整日志|
|---|---:|---|---:|---|
|`./.venv/bin/python -W always::ResourceWarning scripts/audit-regression.py remediation-evidence-20261030/accepted-python.json`|0|230/230；失败0、错误0、跳过0；已捕获子进程资源警告0|0|[accepted-python.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/accepted-python.log)|
|`npm test`|0|Node 20/20；React/Vitest 32/32，0失败、0跳过|1（ExperimentalWarning）|[accepted-web.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/accepted-web.log)|
|`npm run build`|0|TypeScript --noEmit + Vite build（构建不是测试计数）|0|[accepted-build.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/accepted-build.log)|
|`sh ios/test-core.sh`|0|118项Core检查通过（不是iOS UI构建）|0|[accepted-ios-core.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/accepted-ios-core.log)|
|`sh ios/test-security.sh`|0|81项认证/存储接口检查，内存测试存储|0|[accepted-ios-security.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/accepted-ios-security.log)|
|`sh ios/test-tls.sh`|0|19项原生TLS/实际隔离FastAPI检查，非真机|0|[accepted-ios-tls.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/accepted-ios-tls.log)|
|`swiftc -frontend -parse /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/AlertViews.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/CareLinkApp.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/DemoStore.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/DesignSystem.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/DesignTokens.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/DetailViews.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/InteractionModels.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/LiveApiService.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/Models.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/Monitoring.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/SecureTransport.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/Services.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/SessionCredentials.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/SettingsViews.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/Views.swift`|0|15个App Swift源语法解析；非完整类型检查/链接|0|[accepted-swift-syntax.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/accepted-swift-syntax.log)|
|`plutil -lint ios/CareLink.xcodeproj/project.pbxproj`|0|Xcode project plutil结构校验|0|[accepted-project.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/accepted-project.log)|

最终命令环境：本树`.venv`，`PYTHONDONTWRITEBYTECODE=1`、`PYTHONTRACEMALLOC=10`；Python父进程开启ResourceWarning，测试子进程显式开启并检查。最终日志ResourceWarning文本总数 **0**。stdout/stderr完整日志保留，未跳过失败项。

Python当前发现230项，对比上轮211，新增19项、移除0项；全部原测试名称保留，清单 [accepted-inventory.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/accepted-inventory.json)。复现轮、18项专项、86项顺序回归、旧229项失败轮都不加入当前覆盖数。

失败证据保留：原始Core快照重放、JS漏检独立断言失败、开发Core误取异常夹具、测试存储未注入的credentialStorage失败、合成CA首轮链失败、Swift测试局部变量重复编译错误、孤立.control初始化回归失败，以及229项/39错误完整轮。最终结果仅由上表这一轮产生，不选取多个轮次中的最好结果拼接。

底层环境重新核查 [environment.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/environment.json)：CommandLineTools可编译macOS Foundation/Security；完整Xcode及iPhone simulator SDK不可用。Android目录/APK缺失，默认SDK目录存在但未发现平台/构建工具；不假设有可完整构建的环境。没有自动安装SDK、修改developer directory或枚举真实设备。

## 7. 修改文件及证据保护

修改前快照 [baseline.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/baseline.json)、脱敏差异 [baseline.diff.redacted](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/baseline.diff.redacted)；本轮原116份公开源文件全部保留，原Git分支/HEAD不变。以下为相对本轮前态确实变化的文件，避免把之前未提交修复冒充本轮新增：

- [backend/web_auth.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/web_auth.py)
- [backend/ledger_control.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/ledger_control.py)
- [backend/nonce_ledger.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/nonce_ledger.py)
- [backend/test_web_auth.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_web_auth.py)
- [backend/test_nonce_recovery.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_nonce_recovery.py)
- [backend/app.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/app.py)
- [backend/test_password_preservation.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_password_preservation.py)
- [backend/test_api.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_api.py)
- [backend/test_auth_hardening.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_auth_hardening.py)
- [scripts/test-atomic-freeze.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/scripts/test-atomic-freeze.py)
- [scripts/generate-ios-project.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/scripts/generate-ios-project.py)
- [scripts/check-device-migration.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/scripts/check-device-migration.py)
- [scripts/manage-nonce-migration.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/scripts/manage-nonce-migration.py)
- [scripts/audit-regression.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/scripts/audit-regression.py)
- [ios/test-core.sh](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/test-core.sh)
- [ios/CareLink.xcodeproj/project.pbxproj](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink.xcodeproj/project.pbxproj)
- [ios/CoreTests/CoreChecks.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CoreTests/CoreChecks.swift)
- [ios/CareLink/Services.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/Services.swift)
- [ios/CareLink/SettingsViews.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/SettingsViews.swift)
- [ios/CareLink/Models.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/Models.swift)
- [ios/CareLink/Monitoring.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/Monitoring.swift)
- [ios/CareLink/Views.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/Views.swift)
- [ios/CareLink/LiveApiService.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/LiveApiService.swift)
- [ios/CareLink/DemoStore.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/DemoStore.swift)
- [tests/rules.test.mjs](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/tests/rules.test.mjs)
- [shared/schema.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/shared/schema.json)
- [shared/triage-vectors.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/shared/triage-vectors.json)
- [dist/rules.js](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/dist/rules.js)

本轮新增实现、测试及工具：

- [backend/storage_paths.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/storage_paths.py)
- [backend/test_remediation_controls.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_remediation_controls.py)
- [scripts/test-ios-tls.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/scripts/test-ios-tls.py)
- [ios/test-security.sh](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/test-security.sh)
- [ios/carelink-config.example.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/carelink-config.example.json)
- [ios/test-tls.sh](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/test-tls.sh)
- [ios/CoreTests/MemorySessionStore.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CoreTests/MemorySessionStore.swift)
- [ios/CoreTests/SecurityChecks.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CoreTests/SecurityChecks.swift)
- [ios/CareLink/SecureTransport.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/SecureTransport.swift)
- [ios/CareLink/SessionCredentials.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/SessionCredentials.swift)
- [ios/TLSChecks/TLSChecks.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/TLSChecks/TLSChecks.swift)

另修改根目录 [package.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/package.json)（测试脚本）、[API_CONTRACT.md](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/API_CONTRACT.md)（明确可选指标）、[.gitignore](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/.gitignore)（私有证据目录）；新增本报告与 [AUTHORIZED-GATEWAY-VALIDATION-RUNBOOK-20261030.md](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/AUTHORIZED-GATEWAY-VALIDATION-RUNBOOK-20261030.md)。运行配置仅提供无凭据模板，未创建生产配置、复制生产证书或改动设备密钥。

上一轮局部源码散列 [release-snapshot.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/remediation-evidence-20261030/release-snapshot.json) 记录上一轮125个文件，未包含全部可复现输入，不能称为完整不可变发布清单；P2修改后的散列与测试证据见第9节。旧快照、审计目录、失败日志和源备份未删除。

## 8. 剩余阻塞及解除条件

|阻塞|分类|本轮结论/解除条件|
|---|---|---|
|真实写入者覆盖|需要真实环境授权|逐项核对PID/worker/父进程/代码路径、启动管理器/自动拉起及全部SQL入口；未知项未排除就禁止迁移|
|真实备份可信性与完整历史|需要真实备份和独立证据|授权取得冻结边界一致性材料与独立最新checkpoint，不能凭文件存在/行数/hash自洽批准|
|真实恢复/回滚|需要授权副本及现场维护演练|证明完整历史与失败停机策略；权威源丢失时不能猜；A库需独立Session撤销最新性方案|
|iPhone实际Keychain与完整构建|SDK/签名/真机限制|完整Xcode/iOS SDK、当地配置、签名和设备验证；内存测试替身不能替代|
|Android安全实现归属|缺少允许范围内实际工程|另行授权定位实际Android/Capacitor源码与构建设置；再实现/验证Keystore及APK对应，不能发布虚构工程|
|移动端连接实际后端|生产部署未授权|本轮只证明阶段1源码的隔离契约；不得假定当前8443已部署cl_s1认证代码|
|真实TLS/网络/服务版本|需要只读现场授权|重连预期热点后重新检查实际IP/SAN/监听/证书及运行版本，不沿用历史地址|
|最小发布包与启动管理|代码/配置发布审核|工作树含大量未提交变化和历史HTTP启动脚本，禁止整树直接运行当安全发布|
|真实密码与历史公开校验值对应关系|用户安全决策|未读取正式库；保持ttj/wyn原密码、没有自动轮换，但历史校验值的离线猜解风险不能由换哈希算法撤回|
|离线退出/存储故障及容量|更多故障与设备测试|离线远端撤销未确认、Keychain完全不可用时的清理/重启、真实锁屏和容量/ACL/断电需验证；失败不误报成功|

后续执行步骤、权限范围、所有需备份文件、冻结排空确认、校验/转换接口、恢复/回滚判定见 [AUTHORIZED-GATEWAY-VALIDATION-RUNBOOK-20261030.md](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/AUTHORIZED-GATEWAY-VALIDATION-RUNBOOK-20261030.md)。本轮未申请或执行真实服务停机/冻结、账本复制、迁移或回滚。

**独立复核发现两项代码P2，不能将前轮NO-GO仅归因为验收证据不足。P2后续修复与重新运行结果见第9节；真实部署阻塞仍未解除，维持NO-GO。**

## 9. 独立复核 P2 修复与完整重跑（2026-10-30）

**当前部署结论仍为 NO-GO。两项代码P2已修复；真实环境证据仍未验证。**

### 9.1 本轮变化与确定性测试

1. iOS：增加按请求原Token比较后清理的 `removeCredential(matching:)`，覆盖轮换、退出及切换旧账号的注销错误。比较与删除在 MainActor 上同步完成，中间无 await；不会清理同进程另一客户端已写入的新Token。匿名登录失败没有属于它的既有Token可删，因此不再无条件删除；`send` 也对匿名请求检查等待期间的凭据变化，防止迟到成功登录覆盖新凭据。保留 generation 与身份失效保护，不把网络失败冒充远端撤销成功。
2. SecurityChecks 使用 continuation 明确暂停 A，随后通过存储接口写入 B 的新凭据，再释放 A。覆盖轮换、退出、切换账号的旧注销阶段、首次登录、切换账号的新登录阶段，共5种操作 × 成功/401/500/网络错误/畸形响应5种结果。检查原请求Token、新Token保留、无额外登录请求、无旧身份授权。81项原检查保留，当前206项；仍使用 MemorySessionStore，不证明真机Keychain，也不声称跨进程Keychain操作原子性。
3. `verify_backup` 在 admin/gate 锁内检查冻结已排空，SQLite打开前先以严格解析后的路径和 `os.path.samefile`（st_dev/st_ino）拒绝自备份；解析/元数据失败拒绝。没有为了文件身份检查打开或关闭DB描述符，避免影响已有POSIX锁。后续原有私有普通文件、无最终符号链接/单硬链接、marker、v2及四列历史逐项比较保持不变。新增合成测试覆盖原路径、规范化路径、目录符号链接别名、文件符号链接、硬链接，mock断言在 SQLite 打开前拒绝；检查源字节及冻结状态未变，解除合成硬链接后独立备份仍通过。独立文件身份并不证明外部最新性，不能代替可信检查点或防止维护范围外的恶意路径替换。
4. Web预览生成器与对应测试改为本树 `work/carelink-iphone-review.html`，避免 npm pretest 写入兄弟目录；所有原断言保留。

本轮仅编辑以下8个文件，原有其他修改全部保留；未reset/clean、提交、推送或部署：

- `ios/CareLink/LiveApiService.swift`
- `ios/CoreTests/SecurityChecks.swift`
- `backend/ledger_control.py`
- `backend/test_remediation_controls.py`
- `scripts/build-mobile-review.mjs`
- `tests/mobile-review.test.mjs`
- `CARELINK-SECURITY-REMEDIATION-REPORT-20261030.md`
- `AUTHORIZED-GATEWAY-VALIDATION-RUNBOOK-20261030.md`

新增证据与中间文件位于 `work/p2-review-evidence/`，预览产物位于 `work/carelink-iphone-review.html`。原 accepted 日志与125文件快照保持原样。

### 9.2 精确命令、退出码与结果

所有命令完整参数、运行秒数及日志见 [commands.json](work/p2-review-evidence/commands.json)；环境、已安装依赖版本及SDK检查见 [environment.json](work/p2-review-evidence/environment.json)。测试环境为 `PYTHONDONTWRITEBYTECODE=1`、`PYTHONTRACEMALLOC=10`，Python显式开启 `always::ResourceWarning`。

|证据名称|退出码|结果|
|---|---:|---|
|[build](work/p2-review-evidence/build.log)|0|TypeScript --noEmit及Vite构建通过|
|[diff-check](work/p2-review-evidence/diff-check.log)|0|无空白错误|
|[full-python](work/p2-review-evidence/full-python.log)|1|受限环境231项：229通过、2错误，均为临时回环TLS监听PermissionError；0跳过|
|[ios-core](work/p2-review-evidence/ios-core.log)|0|118项Core检查|
|[ios-security](work/p2-review-evidence/ios-security.log)|0|初版交错覆盖181项；随后补全为206项，见最终轮|
|[ios-security-final](work/p2-review-evidence/ios-security-final.log)|0|206项认证/存储检查|
|[ios-tls](work/p2-review-evidence/ios-tls.log)|1|受限环境临时回环监听PermissionError|
|[ios-tls-local-network](work/p2-review-evidence/ios-tls-local-network.log)|0|19项原生隔离TLS/后端检查|
|[node-warning-trace](work/p2-review-evidence/node-warning-trace.log)|0|4/4语言偏好检查；保留警告调用栈|
|[project](work/p2-review-evidence/project.log)|0|Xcode project plutil结构检查通过|
|[python-local-network](work/p2-review-evidence/python-local-network.log)|0|获准使用临时回环服务后231/231；失败0、错误0、跳过0；父进程ResourceWarning=0、受检子进程ResourceWarning=0|
|[swift-syntax](work/p2-review-evidence/swift-syntax.log)|0|全部15个App Swift源文件解析通过|
|[targeted-python](work/p2-review-evidence/targeted-python.log)|0|19/19；0失败、0错误、0跳过|
|[web](work/p2-review-evidence/web.log)|1|受限环境Node20通过、React31通过/1失败：临时回环监听EPERM|
|[web-local-network](work/p2-review-evidence/web-local-network.log)|0|获准使用临时回环服务后Node20/20、React32/32；0失败/跳过|

保留首轮环境失败与获准本地回环重跑，不把失败日志删除或称为跳过；未修改断言、TLS验证或测试超时来取得通过。原230个Python测试名称全部保留，新增1项（内部5种路径子场景），见 [inventory.json](work/p2-review-evidence/inventory.json)。各检查数分别属于各自套件，不相加为覆盖率。

### 9.3 更正 Web 警告归因

前轮 accepted-web.log 确有1条 `ExperimentalWarning: localStorage is not available because --localstorage-file was not provided.`，第6节已更正为1条。本轮Web同样保留此警告。`node --trace-warnings --test tests/i18n.test.mjs` 定位到 `dist/i18n.js:5:22` 读取 Node v26 的可选语言偏好存储。它是缺少实验性Web Storage配置的运行环境警告，日志没有弃用代码/DeprecationWarning；不应称为弃用警告。可用、不可用与被阻止的偏好存储降级测试通过，因此在此隔离测试用途下未影响断言，可视为良性环境提示；这不证明所有Web警告都无害，也不证明浏览器持久化已验收。它与 Python ResourceWarning=0 分开统计，没有屏蔽警告。

### 9.4 快照范围与部署阻塞

[release-snapshot-p2.json](work/p2-review-evidence/release-snapshot-p2.json) 扩展为138个本地输入：包含 package-lock.json、backend/requirements.txt、Xcode project/scheme、iOS配置模板、资源、生成脚本、tsconfig/vite配置及相关源码/测试。136个测试前输入在测试后逐项重新散列无漂移；补充根 index.html/server.mjs 两个未改动入口。新 [artifact-manifest.json](work/p2-review-evidence/artifact-manifest.json) 记录当前输入、报告、手册和本轮证据散列。旧快照保留，不伪造其范围。

这些是本地可核对快照，不是完整不可变发布清单：未验证依赖供应链/安装产物全量散列、完整SDK/签名、实际发布选择和生产配置。仅有CommandLineTools，无iphoneos SDK；源码解析、Core和结构检查不等于完整iOS构建。

真实写入者inventory、最新独立备份及外部检查点、真实恢复与Session撤销状态、实际TLS/服务运行版本、iOS完整构建/真机Keychain、Android实际工程与工程产物全部仍为 NOT VERIFIED。没有访问真实服务、数据库、凭据或证书，没有真实迁移/恢复、硬件连接、提交/推送/部署。保持 NO-GO；现场独立备份与精确同文件检查已写入手册。
