# CareLink 受控现场验证、迁移与恢复手册

本文件是后续审批材料，不是本轮现场操作授权。**当前仍为 NO-GO。** 本轮未读取真实账本、账号库或凭据，未操作真实服务。本手册不猜测真实启动命令、Python 环境、数据库路径、当前 IP 或证书 SAN。

## 1. 范围与角色

- nonce 迁移域：权威 nonce ledger、对应 marker/control、controller 状态、设备接收、读数及告警写入。
- 认证域：账号、密码校验值、Session、限速记录。使用独立数据库及事务；设备 gate 冻结不意味着账号库冻结。不得把认证库选为账本或读数库。
- 认证库的恢复不在 nonce 转换工具的能力内。回滚旧认证库可能复活已撤销 Session、旧密码校验值或已禁用账号；没有独立最新状态证据时，不得这样恢复服务。必要的全量 Session 撤销须另获授权，不等于重置密码。本轮没有自动轮换或重置 ttj/wyn。
- 同用户权限下的外部 SQLite 程序、未更新旧版本、监督器自动拉起不受本分支文件锁自动控制。inventory 是人工审核输入，不是 OS 取证的替代。

## 2. 首先申请的只读现场权限

具体审批应限定进程/启动配置/文件元数据与证书公开部分；不得在聊天或日志中输出完整环境变量、启动命令内秘密或数据库内容。

1. 核实每个服务 PID、父进程、工作目录、解释器路径、worker、代码来源及散列；审查 launchd、终端启动器、定时任务和自动恢复机制。
2. 对照独立分支的写入者矩阵逐一核对实际入口。至少覆盖 HTTP/HTTPS 接收、Web 告警 GET/确认、建表、维护工具、迁移工具、直接 SQL 和历史旧入口。
3. 仅列配置名称、是否设置、实际文件路径及是否相互独立：`CARELINK_LEDGER_CONTROL_ROOT`、`CARELINK_DEVICE_REGISTRY`、`CARELINK_DEVICE_NONCE_DB`、`CARELINK_DATABASE_PATH`、`CARELINK_AUTH_DATABASE_PATH`、`CARELINK_WEB_ORIGINS`。不打印注册表、HMAC、API key、哈希或 Cookie。
4. 重新连接预期热点后检查实际 IP、监听地址、证书 SAN/有效期/链，不假定 IP 仍为历史值。使用受信任 CA 验证，禁止跳过 TLS。
5. 当前设备入口和 Web 登录入口具有不同路由；不得把仅 `/health`、`/sensor-data` 的设备入口当成移动端登录服务。
6. 本轮未授权上述真实检查；全部保持 NOT VERIFIED。

## 3. 维护窗口前必须提交的材料

- 精确发布文件清单、源代码/依赖散列、解释器和启动方式，不能直接部署整棵混有未提交修复的工作树。P2 复核快照扩展至 package-lock.json、backend/requirements.txt、Xcode project/scheme、构建/生成配置及测试输入；仍不是完整不可变发布清单，依赖安装产物、SDK、签名和实际部署输入须另行验证。
- 所有实际写入者与监督器清单，每一项的受控/停止措施、负责人与证据引用；有未知项即禁止迁移。
- 明确时间边界和设备上报暂停影响；前端须将旧数据标为过期，不能把停机中的旧数值显示为新采样。
- 数据库路径、文件/目录权限、别名/硬链接检查。动态 active/candidate/previous、原始 inventory source 以及侧文件都不得与认证/读数库重叠。
- 容量、读写权限、SQLite/OS 同步保障、备份存放位置和可信最新性证明。
- 失败时由谁保持冻结、保留现场和恢复决策；禁止把“重新初始化空账本”作为回退步骤。

## 4. 冻结与在途排空

**只有另行批准维护窗口后才能执行。**

1. 对尚未纳管的旧进程，按获批方式停止设备写入并禁止自动拉起；不能只停新入口或仅看到端口没有监听。
2. 所有更新后的接收者必须使用同一 control-root 与 gate inode。不同控制目录不得接管同一账本。
3. ACTIVE 时先持久发布 FROZEN/null，后来的设备/告警写请求应 503；既有共享租约可完成。
4. 等待排他 gate，确认在途排空；超时保持 FROZEN/null。此时 prepare、verify-backup、switch 均不能继续。先查明未排空写入者，不能删除锁或控制文件。
5. 排空后在源 SQLite writer transaction 中校验并持久记录最终 checkpoint。
6. 记录阶段、序号、完成时间、汇总条数及外部证据引用，不记录 nonce、签名或秘密。
7. 新设备服务在 FROZEN 下可能启动失败，这是 fail-closed 行为。不要为预启动服务而解除完整性检查或临时开放旧入口。

## 5. 需要备份的整套材料

在获批、已排空的冻结边界取得一致性材料，不能直接复制在线主文件冒充完整备份。

- 权威 ledger、准确的 `.initialized`、`.control`，存在的 `.initializing`。
- 已存在的 WAL/SHM/journal 故障现场；不能随意删除。正常备份优先采用已审查的 SQLite 一致性快照方案并验证全部历史。
- control-root 的 `state.json`、被引用的事件、gate/admin 文件及设备号/inode记录；inventory及其审核引用。
- 必要的读数/告警库一致性快照、代码和依赖清单、启动配置名称/路径及私有权限材料。
- 独立保护、足够新的冻结检查点和备份清单。仅文件哈希相互一致无法证明它们没有一起回退。
- 认证库需独立方案；nonce 行数与读数行数不相等，不能从读数重建 nonce，也不能由 nonce 推导 Session 撤销状态。

## 6. 显式校验与转换接口

以下仅是占位形式，`<...>` 必须由审核后的真实材料填写。本轮只在临时合成目录中调用过工具。

```text
<已审核Python> scripts/manage-nonce-migration.py --control-root <批准的绝对控制目录> status
<同工具> freeze --drain-timeout 10
<同工具> verify-backup --backup <批准的一致性v2备份绝对路径>
<同工具> prepare --generation <全新代名称>
<同工具> switch
<同工具> resume
```

首次离线接管另有显式 enroll-offline 流程，必须先取得完整写入者停止及源历史审批证据。不得把普通重新启动当作初次接管。

备份必须是与当前权威源独立的文件。工具在持有 admin/gate 锁、确认 FROZEN 和非空排空 checkpoint 后，先执行 `source.resolve(strict=True) == backup.resolve(strict=True)` 与 `os.path.samefile(source, backup)`（设备号/inode 身份）检查；任一相同即拒绝。缺失、解析失败或元数据错误同样拒绝。这些检查在打开任一 SQLite 连接前完成，不读取数据库内容、不复制或修改文件；后续仍要求私有普通文件、无最终符号链接、单硬链接及有效 marker/格式。目录别名、符号链接和硬链接均不能把权威源冒充备份。元数据检查不证明外部最新性，也不能对抗不遵守维护隔离的路径替换者；现场必须控制目录及全部写入者。

`verify-backup` 要求 FROZEN、已排空 checkpoint、可验证的当前权威 v2 源及完整备份/marker。它逐条比较 device_id、nonce、signed_at、accepted_at，不只比条数；不恢复、不自动 resume。权威源丢失时拒绝；它不是灾难恢复证明或外部可信性签名。

本轮同一独立性检查也接入 `prepare --backup`：显式备份若为源本身、路径别名、软链接或同 inode 硬链接，在打开 SQLite 或创建 generation 之前拒绝。合法独立副本仍须通过后续格式和全部历史比较。省略 `--backup` 的 prepare 从权威源生成转换产物；这不是独立备份验证，不能用它满足备份审批条件。

v1 输入须用显式 prepare 产生独立 v2 generation；运行入口不自动转换。复制完整 WAL 快照后，校验格式、元数据、marker 与所有历史值，再发布 VERIFIED。switch 只原子改变权威 state 指针，不逐个覆盖在线文件。

## 7. 中断、损坏及回滚判定

|情况|安全动作|禁止动作|
|---|---|---|
|冻结未排空或 checkpoint=null|保持 FROZEN，排查在途写入|继续迁移、强删锁|
|COPYING/VERIFIED 中断，当前权威源完整且等于冻结检查点|审核残留后 recover-frozen，只回到冻结；保留候选和事件，下次新 generation|自动 resume、覆盖原候选|
|SWITCHED 但未 resume|核验选定 v2 全部历史，明确批准后 resume；不能猜测旧库更可信|逐个替换 marker/DB|
|缺 ledger、marker、控制绑定、状态或损坏|保留现场，停止接收，人工恢复决策|补 marker、创建空库、忽略权限|
|遗留 `.control` 但 ledger/marker 丢失|初始化工具拒绝，视为既有环境证据|误用“新安装”重置历史|
|备份与权威源为同一文件或别名/同inode|打开SQLite前拒绝，保持冻结；提供独立一致性备份|以源文件自校验冒充备份验证|
|备份缺少后续 nonce、条数相同但内容不同|拒绝备份，保持冻结|拼凑/丢弃异常历史|
|当前权威源丢失，只有旧备份|没有可证明完整历史时拒绝恢复|从旧 state 摘要猜最新状态|
|v2 已接收新的 nonce 后需要代码回退|仅兼容最新完整 v2 且保留 fail-closed 的代码可考虑|回到迁移前 v1 快照、还原旧自动建空库实现|
|账号/Session库需要回滚|单独审批并证明账号、禁用及撤销状态最新；必要时另行受控撤销 Session|因 nonce 迁移成功就恢复旧认证快照|

`initialize-nonce-ledger.py` 仅授权的全新安装；不是恢复工具。现在也拒绝已存在的 `.control`。若整套状态都丢失，本地自洽无法证明历史完整，仍须外部证据，否则停机。

## 8. 切换后需要另获授权的验收

- 只启动审核后的受控入口；不沿用缺失工作目录/环境的旧命令。
- 验证实际证书、完整链、SAN、正常/错误身份、真实设备正向上报及独立测试设备的负向请求。
- 分别记录认证、nonce占用、业务调用、HTTP状态和读数增量。拒绝请求应零额外写入。
- 审批后的重启必须继续使用同一权威 ledger/control，再验证已消费 nonce 仍拒绝。
- Web 最新时间和真实读数持续更新，失败/停机时无 mock 回退，无 null→0。
- 审核移动端实际构建、Keychain/Keystore、重启恢复与注销。macOS Foundation 检查不代表 iPhone 真机验收。

## 9. iOS 本地构建准备（无真实环境操作）

新增安全源码已加入 Xcode Sources；`ios/carelink-config.example.json` 是无凭据模板。完整 Xcode 可用后，将模板复制为被Git忽略的 `ios/carelink-config.json`，填写另行批准的 Web API HTTPS 地址；不要填写仅设备接收的9443地址。

默认使用平台信任库；私有LAN CA应由持有设备的人安装并明确授予信任。若选择随App打包公开DER根证书，配置 `trustAnchorResource` 并明确加入target资源，不能打包CA私钥。代码仍做链、有效期与主机名校验。没有 HTTP 降级或ATS全局放开。

App使用Keychain `WhenUnlockedThisDeviceOnly`保存Token，不使用共享Cookie磁盘存储；重建客户端后向服务器验证，不能只靠缓存角色恢复。离线退出会清除本机凭据并明确提示服务器撤销未确认；无法连接服务器就不能声称远程会话已撤销。存储完全不可用的故障及真实设备锁定/解锁行为必须在真机验证，不能用内存夹具替代。

## 10. 独立备份证据包与授权副本演练

以下均待另行授权，不是本轮已完成的真实操作。

1. **先确定边界**：完成第2节写入者逐项核验，冻结且排空，确认非空 checkpoint。账本源、控制状态、清单和证据使用同一冻结时间边界；认证库另有一致性边界。任何未知写入者或自动重启器存在，停止。
2. **文件独立性**：由获批操作者记录源/备份规范路径、设备号/inode、普通文件类型、链接数、所有者/权限及标记关联。禁止同文件、目录别名、软链接和硬链接；同一目录/磁盘中的另一 inode 只能证明文件独立，不证明灾难域独立。另行核验备份介质、访问主体、离线或不可变保护及加密保护。不要在证据中记录 nonce、密码校验值、Token 或密钥。
3. **完整历史与最新性**：SQLite 一致性快照须包含已提交 WAL 内容，并关联正确 marker/control。保留冻结序号、UTC时间、源历史条数及完整四列历史 checkpoint、清单/代码版本、审核人和独立可信记录的引用。逐条一致性比较在私有工具内完成，只输出 PASS/FAIL 与汇总。条数或本地文件 SHA-256 不能单独证明最新性；源与备份一起回退仍可自洽。摘要应作为受保护清单的一部分，不公开真实 checkpoint。
4. **授权副本边界**：批准单独临时/实验目录后，将经核验的整套材料放入该目录。以私有权限保护，确认不与真实路径同 inode，不含指向真实路径的 control/inventory 引用。不要直接运行仍指向真实路径的复制 state；应由审核工具生成仅指向实验目录的独立控制集，并核对完整历史不变。若需改变控制绑定而没有受审工具支持，停止，不能手改签章/标记绕过检查。本轮合成演练不证明真实副本导入已可用。
5. **演练顺序**：在副本上验证格式/marker/全部历史；显式转换至全新 generation；验证；切换但保持冻结；核对历史；经批准启动仅本机隔离接收器。对批准的测试身份检查已占用 nonce 拒绝、新合法请求仅一次成功、并发重放仅一次接受、模拟重启后仍拒绝历史请求。不可把真实设备秘密输出或复用到通用日志；真实历史 nonce 仅由私有检查器读取，结果不打印 nonce。
6. **失败原则**：任一步未知、缺失、损坏、权限错误、版本错配、历史少一条或排空失败，保留 FROZEN，不 resume。保留源、候选、中间产物及诊断。禁止创建空 ledger、补造 marker、删锁、回退旧账本或从读数重建历史。真实源丢失时，工具的源对比能力不再构成证明，须另有可信最新证据和获批恢复工具，否则停机。

建议证据表字段：环境标签、审核边界、源/备份身份是否独立、格式/marker是否匹配、历史是否完整、可信最新证据引用、恢复前后历史一致、已用请求拒绝、Session撤销验证、失败冻结验证、操作者/审核者、结论。秘密值和历史逐行内容不进入表格。

## 11. 认证库恢复的独立验收

nonce 工具不提供账号库的抗回滚能力。本轮新增合成测试证明：退出后制作的账号快照恢复时旧 Session 返回401；退出前快照恢复时同一旧 Session 返回200。后者是安全风险诊断，绝不是可接受恢复结果。

获批的认证库副本演练必须覆盖账号 active/权限、密码迁移状态、Session expires_at/revoked_at/replacement_hash 与限速持久状态。用专用测试账号和隐藏输入，在进程内保存测试 Cookie：登录、制作快照、轮换/注销、制作最新快照；恢复最新副本并验证旧 Token401、新 Token符合预期及过期/禁用账号拒绝。对过期副本执行的诊断应证明它会造成错误接受，并明确拒绝该副本用于恢复服务。测试不得打印 Cookie、哈希或密码。

必须有独立于待恢复认证快照的最新撤销/禁用证据，才能批准恢复。不能证明时保持相关认证服务离线；若决定在恢复后使所有旧 Session 失效，应另行审批一致性全量撤销或其他可证明失效方案，执行后再验收，不能自动实施。ttj/wyn 保留原密码及成功登录时 CAS 渐进 Argon2id 迁移的决定不变。

## 12. iPhone 真机验收清单

当前仅有macOS Swift编译及临时TLS服务证据。2026-10-30 检查：活动开发目录为 CommandLineTools；xcodebuild失败；iphoneos/iphonesimulator SDK不可用。未安装/切换SDK，没有完整App构建、签名或真机PASS。

前置：完整Xcode与兼容SDK由用户准备；确定bundle ID、签名、Keychain access group、目标版本、批准的隔离Web API origin及公开CA信任方式。审查真实构建配置前不要把模板当发布配置，不要将9443设备入口填为登录API。构建/导出日志与源码/依赖摘要一并留存。

在准备好批准的隔离配置/公开资源并确认SDK后，可审核以下本地构建形式（本轮未执行；输出目录必须是全新独立目录）：

```text
xcodebuild -project ios/CareLink.xcodeproj -scheme CareLink -configuration Debug -destination 'generic/platform=iOS Simulator' -derivedDataPath <批准的新构建目录> CODE_SIGNING_ALLOWED=NO build
```

这只验证模拟器构建，不验证签名、设备Keychain或release archive。当前scheme没有XCTest TestAction/test target，不能把上述build或独立Swift脚本称为xcodebuild test；增加仪器测试目标须另行实施评审。真机构建/签名与归档使用审核后的真实配置，不在此推测团队、设备或签名命令。

|验收|必要证据与通过条件|
|---|---|
|写入/读取|签名App登录专用账号；Keychain成功写入/读取；仅输出状态；无UserDefaults/文件/JS明文替代|
|应用重启|结束App后重开；从Keychain读取并向服务器验证Session；伪造缓存角色不能恢复权限|
|轮换|新Cookie成功写入；旧Token访问受保护接口401；新Token可用且不延长绝对期限|
|注销|在线退出旧Token立即401、本地凭据清理；多客户端迟到响应不删除新凭据|
|切换账号|旧请求完成或失败均不能污染新身份；患者范围由服务器决定|
|锁屏/重启|WhenUnlockedThisDeviceOnly在锁定及重启首次解锁前不可用时安全失败；解锁后按系统结果恢复；禁止降级存储|
|存储不可用|注入/复现SecItem失败；无持久化成功就不能宣称登录成功；清理失败明确显示错误，不静默接受旧身份|
|认证失效|Session过期、撤销、账号禁用均401并清理匹配凭据；服务器5xx/离线不把旧状态当新验证|
|离线注销|本地清理，明确远端撤销未确认；恢复联网后按单独方案核查，不能声称已经远程撤销|
|TLS|无信任CA、过期证书、错误SAN/主机、重定向到其他origin均拒绝；不发送凭据到错误服务器，不关闭TLS校验|
|诊断与产物|日志/崩溃报告/App包无Token、密码、私钥；仅允许公开CA；记录设备/OS/App版本，不记录秘密|

共享存储竞态测试目前限定同进程MainActor与接口替身；不能推论跨App扩展/进程Keychain读改写具备原子比较删除。若日后增加共享access group或扩展，需新增跨进程设计与验收。没有对应设备记录的每项保持 NOT VERIFIED。

## 13. Android 工程范围与验收契约

允许检查的当前工作树没有 Android/Gradle/Capacitor 工程或APK。默认SDK目录存在但未发现platforms/build-tools；未安装、更改SDK或搜索其他项目。历史对话中的Keystore实现不能作为此工作树的实现证据。先获得实际Android工程归属和允许范围，不能创建脱离业务的占位类来补报告。

- 工程范围：实际CareLink登录、患者/读数/告警业务、应用生命周期、网络桥接与构建配置。若为Capacitor，明确WebView与原生职责、插件授权和原生网络入口；不能只给Web页面接localStorage保存Token。
- API契约：复用`/api/login`、`/api/session`、`/api/session/rotate`、`/api/logout`及患者范围接口；HTTPS同origin，Cookie名/绝对过期、CSRF自定义头、JSON与Origin行为遵守当前后端，不擅自创造Bearer接口。服务端角色是授权依据。若桥接需要Origin兼容调整，应独立评审，不放宽CORS。
- 凭据：Android Keystore生成不可导出AES-GCM密钥；随机且不复用的IV，认证标签校验；持久层只放密文/IV/必要元数据。不得明文SharedPreferences、localStorage或JS可访问Token；原生桥接只暴露业务结果，禁止把Token交给任意页面。禁备份/日志泄露，处理密钥失效、锁定和卸载重装；失败拒绝恢复登录。
- 网络：平台TLS验证链/有效期/服务器身份；最小受审LAN公开CA或平台信任，无trust-all、宽松HostnameVerifier、SSL错误proceed或HTTP降级；release明文策略禁止、debug CA不混入release，限制跨origin重定向。
- 验收：登录、关闭重开、系统重启/锁定、旧Token轮换失效、在线/离线退出、服务器401/403、患者越权、Keystore密文篡改/密钥失效、错误CA/SAN/过期、桥接origin/JS注入、备份/日志/产物秘密扫描。分别记录JVM/仪器测试、完整Gradle构建与真机结果。
- 发布证据：SDK/Gradle/JDK版本、锁定依赖、签名与release配置、源码摘要和APK对应关系；无完整构建及设备证据不能标Android安全完成。

## 14. 分阶段授权及放行条件

1. 先审核本轮源码、证据与报告；不等于部署授权。
2. 独立授权只读现场进程/路径元数据/公开证书与握手核验，确定全部写入者和实际版本；不读取秘密内容。
3. 再批准备份、受保护副本和维护窗口；先解决可信最新性、全部写入者排空、认证库恢复边界及副本工具，不允许用生产尝试填补方案缺口。
4. 移动端完整构建/真机、固件来源对应、真实正反向认证/重启和实时UI须分别明确授权与验收。
5. 所有必要控制均有可复核证据、最小发布包和失败停机方案后才可建议GO。任一部署阻塞仍未知则NO-GO；不把隔离PASS转记为真实环境PASS。
