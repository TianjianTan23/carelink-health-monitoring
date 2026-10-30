# CareLink 最终安全审计与问题修复报告

审计窗口：2026-10-29 至 2026-10-30，Asia/Shanghai。**总体结论：NO-GO，不能批准部署。**

本报告审计的是 `/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic`、分支 `fix/nonce-atomic-freeze-20261029` 的未提交工作树。源码/隔离测试通过不证明真实网关已启用相同代码；本轮没有接触真实账号库、读数库、nonce ledger、9443/18443/18444、硬件、网络配置或真实证书/密钥，也没有提交、推送或合并。

## A. 总体结果与证据边界

- 最终完整 Python **211 项**，退出码 **0**；最终分阶段并发专项 **20/20**，退出码 **0**。完整套件的资源警告文本数 **0**。具体结果以下表及原始日志为准。
- 最终同轮 Node/React、构建、Swift 命令逐条记录，不把专项、重复轮次、历史通过数相加为覆盖率。
- 原始203个测试名称全部保留；当前发现211项，新增8项，删除0项。新增项是文件锁1、返回游标2、生命周期3、侧文件竞态/权限2；没有跳过或屏蔽安全断言。清单：[final-test-inventory.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/final-test-inventory.json)。
- 真实写入者覆盖、完整备份最新性、真实迁移/恢复/回滚、真实部署版本和移动端真机均未验证；iOS Core实际失败，且阶段2移动端安全实现未包含在指定树中。因此即使隔离后端全绿，也不是GO。
- 所有相关文件操作限于本独立树和测试创建的临时目录。仅测试自身随机loopback端口申请了运行权限；初次受限执行的EPERM不是应用缺陷，已单列留档。

## B. 本轮问题、根因和修复

### B1. HTTPS就绪超时：已修复夹具，未放宽TLS

本轮原样复现203项中201通过、两个15秒超时。加入诊断而保持15秒后，两项单独连续运行也超时：应用已导入约6.3–6.8秒，日志仍在 `Waiting for application startup`。保留 `PYTHONTRACEMALLOC=10` 时，实际健康就绪约15.6–16.7秒，因此旧15秒预算会杀掉尚在正常初始化的服务。历史单项成功的完整参数未保留，不能据此断言是测试顺序问题。

现在固定60秒上限，提前检测退出，记录阶段、最后探测类型、退出码和脱敏有界日志尾；不无界等待。父进程持有随机绑定socket并通过FD传递，避免端口释放再绑定；输出改临时文件，避免PIPE无人读取。这两点是预防性治理，未冒充原始超时根因。自签临时CA仍明确受信任且校验localhost身份，错误IP及缺少CA仍必须拒绝。

调用 `uvicorn.Server.run()` 不会像CLI自动给失败启动设置非零退出；夹具显式根据 `server.started` 返回0或3，保留冷启动失败断言。严格开启子进程警告后，又实际检出失败启动未关闭继承socket；已用socket上下文修复，不屏蔽ResourceWarning。

证据：[baseline-loopback-python.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/baseline-loopback-python.log)、[tls-diagnostic-15s.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/tls-diagnostic-15s.log)、[tls-device-single-final.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/tls-device-single-final.log)、[tls-web-single-final.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/tls-web-single-final.log)、[release-round-python.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/release-round-python.log)（包含真实检出的套接字警告）、[tls-resource-fixed.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/tls-resource-fixed.json)（修复后两项通过，子进程警告0）。

### B2. 迁移头检查重新释放SQLite锁：已修复

`_require_sqlite_main_header()` 在拥有SQLite连接的同一进程内原始open/close主文件，会释放该进程已有的POSIX记录锁；仅把探测放在“本次新连接之前”不够，因为另一个连接可能已持事务。保留的旧实现加纠正后的锁回归能复现锁丢失。现把只读文件头探测放到独立短进程，校验头、文件类型/身份/权限，5秒上限、失败拒绝；不修改输入，不让WAL掩盖坏主文件头。主进程仍使用SQLite自有连接、BEGIN IMMEDIATE、FULL提交。移除了没有调用方且依赖未导入名称的旧辅助函数；原备份文件未删除。

证据：[header-lock-before-corrected.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/header-lock-before-corrected.log)、[header-lock-after-corrected.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/header-lock-after-corrected.log)；代码：[backend/ledger_control.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/ledger_control.py)；测试：`test_header_validation_preserves_sqlite_writer_record_lock`。早期探针字节选择错误及首版字符串转义错误也保留在证据目录，未作为修复前后成功证据。

### B3. 快捷execute返回游标绕过租约：已修复

`LeasedConnection.execute()` 原调用C层快捷方法，返回原生 `sqlite3.Cursor`；它绕过自定义游标检查，能关闭只读模式或在原租约失效、冻结后执行SQL。两个新增回归修复前均失败。现在execute/executemany/executescript均经过受控 `LeasedCursor`，每次执行检查同一有效租约和只读限制。仍不允许通过自定义cursor工厂绕过。所有已消费nonce的事务策略保持。

证据：[returned-cursor-before.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/returned-cursor-before.log)、[atomic-cursor-after.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/atomic-cursor-after.log)、最终并发专项；代码：[backend/app.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/app.py)。

### B4. 多进程启动的侧文件消失竞态：已修复并保留失败记录

原始209项完整复核出现一个子进程退出1；补充脱敏stderr后，重复3次中实际1次失败。堆栈指向 `_paths → _file(sidecar) → os.access=False`。可确定性复现同一路径：SQLite空闲WAL/SHM在lstat与access之间被正常删除；access把ENOENT与权限拒绝都表现为false，而旧代码统一503。并发侧文件正常消失应由既有的sidecar专用FileNotFoundError分支处理。

修复仅在access失败时再次lstat：不存在时保留FileNotFoundError；只有已有的侧文件分支允许这种缺席。主库/marker缺失仍503、不创建；仍存在但不可访问的文件仍明确拒绝；不原始打开任何SQLite句柄。新增两个确定性用例，修复前一个报错；修复后50项recovery及3轮双进程专项共53项通过，子进程资源警告0。没有重试业务、放宽认证或忽略存储错误。

证据：[final-unittest-discover.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/final-unittest-discover.log)、[multiprocess-repeat.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/multiprocess-repeat.json)、[sidecar-race-before.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/sidecar-race-before.log)、[nonce-sidecar-fixed.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/nonce-sidecar-fixed.json)；代码：[backend/nonce_ledger.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/nonce_ledger.py)。这些历史失败不以最终通过结果抹去。

### B5. 当前Web源码与后端安全契约不兼容：已修复

修复前新增4项服务测试全部失败：缺CSRF、退出失败被吞掉、401仍缓存授权、接受明文HTTP。现在写请求带CSRF和JSON；退出失败返回错误，本机视图仍清除并显示“未确认服务器撤销”；401清理服务缓存授权和顶层视图；live API只允许HTTPS，同源模式要求HTTPS页面。数据请求不回退mock。

本机传输集成夹具也改为临时HTTPS服务器，明确CA、正常主机校验，并断言错误IP身份被拒绝，没有添加HTTP白名单。没有修改实际运行Web配置或服务。证据：[web-auth-before.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/web-auth-before.log)、[acceptance-node-react.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/acceptance-node-react.log)。

### B6. iOS Core仍失败：未擅自修改告警语义

[ios/CareLink/Monitoring.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/Monitoring.swift) 用全部指标（包含SpO2）；[dist/rules.js](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/dist/rules.js) 的当前指标集只有HR/温度。共享黄金向量 `spo2-89.9` 的JS预期为green，Swift为red。重复运行均在同一断言终止。将Swift降为green只为测试通过会改变告警语义，本轮没有这样做。需要先明确当前产品的指标契约，再统一模型、规则与UI，保留异常告警测试。Core失败不能被Swift语法解析通过替代。

## C. Security Acceptance Matrix

本表编号C01–C25为本次审计编号，不假冒之前矩阵的编号。“测试PASS”只表示合成环境；“运行部署”独立列记录本轮证据。

|编号|控制目标及实际源码入口|实现|自动化|运行部署|总体|证据、风险及未完成事项|
|---|---|---|---|---|---|---|
|C01|工作区隔离及发布归属；`Git 状态、基线指纹、最终源码指纹`|PASS|PASS|NOT VERIFIED|PARTIAL|仅指定分支修复；没有生产部署包或真实版本取证。 [audit-evidence-20261029/before.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/before.json) / [audit-evidence-20261029/final-code-freeze.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/final-code-freeze.json)|
|C02|Argon2id 密码保存；`HASHER / AuthStore.login`|PASS|PASS|NOT VERIFIED|PARTIAL|64 MiB、t=3、p=1；真实账号库未读取；不能宣称正式库已迁移。 [backend/web_auth.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/web_auth.py) / [backend/test_web_auth.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_web_auth.py)|
|C03|保留原密码的并发渐进迁移；`login CAS + hash_password_for_migration`|PASS|PASS|NOT VERIFIED|PARTIAL|PBKDF2 验证成功后原密码重哈希；CAS 失败重读重验；未重置 ttj/wyn。 [backend/web_auth.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/web_auth.py) / [backend/test_password_preservation.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_password_preservation.py)|
|C04|随机 Session 与摘要存储；`token_urlsafe(32) / token_hash`|PASS|PASS|NOT VERIFIED|PARTIAL|数据库保存 SHA-256 校验摘要；非可复用明文 Token。 [backend/web_auth.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/web_auth.py) / [backend/test_web_auth.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_web_auth.py)|
|C05|撤销、过期、轮换及重启；`/api/logout、/api/session/rotate、username`|PASS|PASS|NOT VERIFIED|PARTIAL|隔离进程重启中有效/过期/撤销的会话均按预期；真实网关未重启。 [backend/app.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/app.py) / [backend/test_auth_https_isolated.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_auth_https_isolated.py)|
|C06|Cookie 安全属性；`_set_session_cookie / delete_cookie`|PASS|PASS|NOT VERIFIED|PARTIAL|Secure、HttpOnly、SameSite=Lax；实际已部署 Cookie 本轮未检查。 [backend/app.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/app.py) / [backend/test_web_auth.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_web_auth.py)|
|C07|CSRF、来源与 CORS；`WebSecurity / allowed_origins`|PASS|PASS|NOT VERIFIED|PARTIAL|限制 HTTPS 与配置来源；拒绝跨来源、重复安全头；写请求要求 JSON 和 CSRF 头。 [backend/web_security.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/web_security.py) / [backend/test_auth_hardening.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_auth_hardening.py)|
|C08|持久、有界登录限速与统一错误；`reserve_login / login_limits`|PASS|PASS|NOT VERIFIED|PARTIAL|15 分钟；默认 IP20、账号10、组合5；最多4096桶。测试覆盖重启、并发、Retry-After。部署须审查测试限额覆盖变量。 [backend/web_auth.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/web_auth.py) / [backend/test_web_auth.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_web_auth.py)|
|C09|角色、患者范围与固定会话攻击；`current_username / _ensure_scope / acknowledge`|PASS|PASS|NOT VERIFIED|PARTIAL|授权来自服务端账号库；受保护数据拒绝未认证/越权；客户端角色不授予权限。 [backend/app.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/app.py) / [backend/test_auth_hardening.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_auth_hardening.py)|
|C10|独立 API key / HMAC；`DeviceAuthenticator.verify`|PASS|PASS|NOT VERIFIED|PARTIAL|方法、规范路径、设备、时间、nonce、原始正文摘要参与签名；恒定时间比较；真实入口未攻击或读取凭据。 [backend/device_auth.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/device_auth.py) / [backend/test_device_auth.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_device_auth.py)|
|C11|时间窗与正文绑定；`verify / parse_sensor_payload / reserve`|PASS|PASS|NOT VERIFIED|PARTIAL|正负60秒、取得写锁后重新检查；拒绝重复头、非规范路径、错设备、无效JSON等；并发夹具固定时钟不更改生产时窗。 [backend/device_auth.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/device_auth.py) / [backend/nonce_ledger.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/nonce_ledger.py) / [backend/test_device_api.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_device_api.py)|
|C12|同 nonce 原子占用；`BEGIN IMMEDIATE + UNIQUE + FULL commit`|PASS|PASS|NOT VERIFIED|PARTIAL|单设备相同nonce一个胜者；2/32/64请求及双进程32请求分别断言认证、占用、业务、HTTP、读数增量。 [backend/nonce_ledger.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/nonce_ledger.py) / [backend/test_atomic_freeze.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_atomic_freeze.py)|
|C13|先持久占用再进入业务；`AcceptedSensorPayload / consume_receipt`|PASS|PASS|NOT VERIFIED|PARTIAL|伪造dict、不同账本凭据、重复消费拒绝；提交失败不进入业务；已提交nonce不因业务失败退还。非跨库 exactly-once。 [backend/device_auth.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/device_auth.py) / [backend/app.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/app.py) / [backend/test_atomic_freeze.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_atomic_freeze.py)|
|C14|账本缺失/损坏 fail closed；`NonceStore.connect / initialize_new_ledger`|PASS|PASS|NOT VERIFIED|PARTIAL|初始化与恢复分离，缺对/坏标记/错配/权限失败均拒绝；新修复仅区分被合法删除的侧文件，不放宽现存坏文件或主库/marker要求。 [backend/nonce_ledger.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/nonce_ledger.py) / [backend/test_nonce_recovery.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_nonce_recovery.py)|
|C15|新旧入口统一冻结与排空；`UnifiedWriteGate / Controller.admission`|PASS|PASS|NOT VERIFIED|PARTIAL|三种更新后的入口均503拒绝冻结写入，等待在途；实际旧进程、监督器、未知SQLite写入者没有核验。阻塞。 [backend/write_gate.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/write_gate.py) / [backend/controlled_device_ingress.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/controlled_device_ingress.py) / [backend/test_atomic_freeze.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_atomic_freeze.py)|
|C16|连接、游标与业务写入租约；`LeasedConnection / LeasedCursor / guarded_write`|PASS|PASS|NOT VERIFIED|PARTIAL|修复 execute 返回的原生游标旁路；初始化、告警更新/确认及读数写入均受控；认证库单独管理且须核验路径无别名。 [backend/app.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/app.py) / [backend/test_atomic_freeze.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_atomic_freeze.py)|
|C17|v1→v2 完整历史转换及中断；`Controller.prepare/switch/recover`|PASS|PASS|NOT VERIFIED|PARTIAL|显式转换，核验全部四列历史；状态发布、重复执行、进程退出、部分替换、权限错误均有合成用例；实际迁移未执行。 [backend/ledger_control.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/ledger_control.py) / [backend/test_ledger_control.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_ledger_control.py)|
|C18|SQLite 锁与迁移检查安全性；`_file / _require_sqlite_main_header`|PASS|PASS|NOT VERIFIED|PARTIAL|移除主进程原始主库文件头开关句柄；改独立短进程探测且失败拒绝；实际Mac故障/ACL/断电未验收。 [backend/ledger_control.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/ledger_control.py) / [backend/test_ledger_control.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_ledger_control.py)|
|C19|可信备份、恢复、回滚与最新性；`checkpoint / backup / recover-frozen`|PARTIAL|PASS|NOT VERIFIED|PARTIAL|合成旧备份少后续nonce拒绝；无法证明完整历史时停机。外部最新性证据、真实备份和真实恢复缺失，阻塞。 [NONCE-CONTROL-OPERATIONS.md](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/NONCE-CONTROL-OPERATIONS.md) / [backend/test_ledger_control.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_ledger_control.py)|
|C20|TLS 主机身份、信任与 SAN；`临时 localhost TLS 服务、证书错误拒绝`|PASS|PASS|NOT VERIFIED|PARTIAL|自建TLS验证信任根、主机错误/缺少CA拒绝；真实证书/SAN/地址/监听未访问，不沿用历史IP。 [backend/tls_test_support.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/tls_test_support.py) / [backend/test_nonce_https_recovery.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_nonce_https_recovery.py)|
|C21|Web 登录/退出及失效处理；`LiveApiService / config / App`|PASS|PASS|NOT VERIFIED|PARTIAL|修复CSRF/JSON、退出失败不可伪报成功、401清除缓存授权、拒绝HTTP；UI清除私密视图并提示未确认的服务器退出。 [src/data/LiveApiService.ts](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/src/data/LiveApiService.ts) / [src/data/services.test.ts](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/src/data/services.test.ts) / [src/App.test.tsx](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/src/App.test.tsx)|
|C22|Android Keystore/存储/构建；`本工作树无 Android 工程或 APK`|NOT VERIFIED|NOT VERIFIED|NOT VERIFIED|NOT VERIFIED|SDK目录存在且已读取组件元数据；不是“没有SDK”。未找到本范围内阶段2源码，不能证明Keystore、APK对应或真机行为。 [audit-evidence-20261029/platform-environment.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/platform-environment.json)|
|C23|iOS Keychain、原生登录、TLS策略；`LiveApiService / DemoStore`|FAIL|NOT VERIFIED|NOT VERIFIED|FAIL|当前树没有Keychain实现或原生登录/退出安全流程；URL配置仍允许HTTP，默认共享URLSession会话不能替代Keychain验收。阶段2实现不在本树。 [ios/CareLink/LiveApiService.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/LiveApiService.swift) / [ios/CareLink/DemoStore.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/DemoStore.swift)|
|C24|iOS 规则回归、SDK及真机；`CoreChecks / Monitoring / JS golden vectors`|FAIL|FAIL|NOT VERIFIED|FAIL|Core首个失败spo2-89.9：JS指标集仅HR/温度，Swift仍纳入SpO2；不擅自降低告警。语法通过不等于iOS构建；完整Xcode/模拟器SDK不可用。 [ios/CoreTests/CoreChecks.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CoreTests/CoreChecks.swift) / [ios/CareLink/Monitoring.swift](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/Monitoring.swift) / [dist/rules.js](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/dist/rules.js)|
|C25|秘密、日志、产物及业务回归；`gitignore / bounded diagnostics / scan / regression`|PARTIAL|PASS|NOT VERIFIED|PARTIAL|公开文本/6个本地可达提交做有限模式扫描；真实密钥和日志未读，无APK可核验。存在演示凭据/校验逻辑，不能证明与真实密码无复用；真实传感器和UI未联调。 [.gitignore](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/.gitignore) / [audit-evidence-20261029/safe-source-scan.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/safe-source-scan.json) / [src/data/MockDataService.ts](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/src/data/MockDataService.ts)|

## D. 实际顺序与冻结覆盖

1. HTTP写请求先取得同一gate共享租约，持有到认证、业务提交和响应结束。冻结先持久发布FROZEN，使新请求503，再等排他gate排空在途。
2. 检查HTTPS、重复认证头、长度、规范方法/路径、API key与HMAC、时间窗；验证JSON、正文设备身份和字段。
3. BEGIN IMMEDIATE内校验既有v2账本/marker/metadata/历史计数，重新检查时间，INSERT唯一(device_id,nonce)，FULL提交。
4. 只有提交成功才产生绑定当前账本的单次内存凭据；原业务入口消费凭据，再分类并在读数库事务中写读数和告警。nonce失败无凭据、无受保护业务。
5. 已提交nonce后业务失败/进程退出仍保留占用；未提交事务进程退出由SQLite回滚。本方案是at-most-once准入，不是两个数据库之间的exactly-once交付。

|写入者/入口|隔离源码中的冻结约束|隔离验证|真实运行覆盖|
|---|---|---|---|
|通用`backend.app:app`的`/sensor-data`|UnifiedWriteGate + receipt + guarded_write|PASS|NOT VERIFIED|
|旧形态`backend.device_ingress:app`|同一UnifiedWriteGate及所选账本|PASS|NOT VERIFIED|
|新controlled factory|同一Controller/gate，不是独立冻结开关|PASS|NOT VERIFIED|
|初始化readings/alerts表|guarded_write + 连接租约|PASS|NOT VERIFIED|
|读取告警时的连接告警更新、告警确认|HTTP gate + guarded_write + 连接租约|PASS|NOT VERIFIED|
|绑定账本的NonceStore.reserve/底层连接|同一control绑定；失效租约拒绝|PASS|NOT VERIFIED|
|独立账号、Session、限速库|独立认证事务，非nonce迁移对象；必须确认无路径别名|PASS|NOT VERIFIED|
|未更新旧进程、自动拉起脚本、外部原生SQLite写入者|本分支无法自动约束，inventory不是OS取证|NOT VERIFIED|NOT VERIFIED|

不能因新入口停止、端口没有监听或存在inventory JSON，就声称所有真实写入者已冻结。未绑定的底层新安装/单元原语仍不是通用生产写入接口，不能拿它绕过接收入口。任意同用户外部代码可直接打开SQLite，不由本协议防御；生产前必须核实并排除这种写入者。

### 分阶段并发证据（最终专项，不与完整套件相加）

“签名通过”不等于“认证接受”；所有计数分别断言，读数与nonce使用增量。

|场景|签名通过|nonce尝试|nonce提交|认证接受|业务进入|HTTP分布|nonce增量|读数增量|
|---|---:|---:|---:|---:|---:|---|---:|---:|
|32-mixed-http|32|32|1|1|1|200×1, 409×31|1|1|
|64-mixed-http|64|64|1|1|1|200×1, 409×63|1|1|
|no-raw-sqlite-fd|32|32|1|1|1|200×1, 409×31|1|1|
|freeze-inflight-old-new|1|1|1|1|1|200×1, 503×2|1|1|
|24-frozen-all-entries|0|0|0|0|0|503×24|0|0|
|old-new-after-switch|2|2|1|1|1|200×1, 409×1|1|1|
|crash-uncommitted|2|2|1|1|1|200×1, 409×1|1|1|
|crash-committed|2|2|0|0|0|409×2|0|0|
|commit-failure|2|2|0|0|0|503×2|0|0|
|2-process-32-mixed-http|32|32|1|1|1|200×1, 409×31|1|1|
|two-mixed-http|2|2|1|1|1|200×1, 409×1|1|1|

崩溃后已提交场景：子进程已持久写入的那条占用在重放前就存在，因此表中重放增量0，HTTP409；不是“没有占用”。未提交崩溃场景允许后续一次成功。切换场景另断言旧账本增量0。完整聚合：[final-atomic.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/final-atomic.json)。

## E. 迁移、备份、恢复与回滚

- 正常运行仅既有v2；v1不自动转换；缺失两件套不当成新安装。显式新安装授权不能替代存量恢复授权。
- 状态机：审核离线接管→FROZEN；ACTIVE→FROZEN/null→排空→最终checkpoint；FROZEN→COPYING→VERIFIED→SWITCHED→显式resume→ACTIVE。中断只允许在权威源完整且检查点相等时recover-frozen；不会自动开放写入。
- prepare以排他gate和源SQLite写事务冻结历史，通过SQLite一致性backup复制WAL快照，核验全量四列历史，发布独立generation；不会逐个覆盖在线文件。源历史变化、缺失、坏输入、未知schema、目标部分文件均拒绝。
- 必备材料：账本与准确`.initialized`、存在的`.initializing`、`.control`绑定、现存WAL/SHM/journal现场、一致性读数库备份、control-root的state/events/gate/admin及身份清单、inventory、代码/解释器/入口/配置名称清单、冻结最终count/digest及独立可信最新证据。Session账号库需单独的完整备份流程，不从nonce反推。
- 文件存在、哈希能对上、metadata计数一致、SQLite完整性通过，都不证明备份包含冻结前完整历史。旧备份缺少后续nonce必须拒绝；活跃期旧state摘要不能充当最新性证据。
- 权威账本丢失/损坏且没有独立可信完整历史时，保持停止接收/503；不删标记、不创建空账本、不从读数重建、不降级认证。
- 一旦v2接受新nonce，就不能回滚到迁移前v1快照。代码回退只能配合最新完整v2和fail-closed实现。所有本地文件一起协调回滚仍需外部信任锚；本版本不宣称具备已验证灾难恢复。
- 原说明中“没有转换工具”的历史表述已纠正为显式工具及权威文档链接，保留“不静默转换”的要求。参见[NONCE-CONTROL-OPERATIONS.md](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/NONCE-CONTROL-OPERATIONS.md)、[NONCE-LEDGER-RECOVERY.md](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/NONCE-LEDGER-RECOVERY.md)、[ATOMIC-UNIFIED-FREEZE.md](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ATOMIC-UNIFIED-FREEZE.md)。

## F. 最终完整回归与历史失败

下表仅本次最终顺序验收轮次。前面各轮是复现/专项/重复证据，不相加为测试覆盖率。

|命令|退出码|实际结果|证据|
|---|---:|---|---|
|`./.venv/bin/python -W always::ResourceWarning -m unittest discover -s . -t . -p test_*.py -v`|0|211项；以日志末尾OK/FAILED为准；ResourceWarning文本0|[acceptance-python.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/acceptance-python.log)|
|`./.venv/bin/python -W always::ResourceWarning scripts/audit-regression.py audit-evidence-20261029/final-atomic.json backend.test_atomic_freeze`|0|20/20，失败0，错误0，跳过0；父/已捕获子进程资源警告0/0|[acceptance-atomic.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/acceptance-atomic.log)|
|`npm test`|0|Node 19/19；Vitest 32/32；0失败、0跳过；未见资源警告|[acceptance-node-react.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/acceptance-node-react.log)|
|`npm run build`|0|TypeScript --noEmit及Vite build；非测试计数，未见警告|[acceptance-build.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/acceptance-build.log)|
|`sh ios/test-core.sh`|133|FAIL：首个断言JS/Swift parity spo2-89.9；提前终止，没有完整通过/失败总数|[acceptance-ios-core.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/acceptance-ios-core.log)|
|`swiftc -frontend -parse /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/AlertViews.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/CareLinkApp.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/DemoStore.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/DesignSystem.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/DesignTokens.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/DetailViews.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/InteractionModels.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/LiveApiService.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/Models.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/Monitoring.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/Services.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/SettingsViews.swift /Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/Views.swift`|0|Swift源码语法解析通过；不是类型检查、iOS构建或真机测试|[acceptance-swift-syntax.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/acceptance-swift-syntax.log)|

Python命令均使用工作树`.venv`（Python3.14.5），启用`PYTHONDONTWRITEBYTECODE=1`和`PYTHONTRACEMALLOC=10`，没有过滤资源警告。测试子进程显式继承`always::ResourceWarning`，日志检查发现则测试失败，不能把只检查父进程误称全部为0。两项TLS成功、失败及超时均有有界终止/kill/wait与文件/socket清理；进程批次用ExitStack在断言失败和超时也回收。`os._exit`故障注入按设计不运行Python终结器，由OS关闭资源并由SQLite恢复未提交事务。

历史记录明确保留：

|轮次|实际结果/退出码|说明|
|---|---|---|
|最初受限完整运行|203，201通过、2错误；1|随机端口bind被EPERM拒绝；不是应用缺陷|
|允许loopback后原样完整复现|203，201通过、2超时；1|[baseline-loopback-python.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/baseline-loopback-python.log)|
|15秒诊断双项|0/2；1|两项均在正常应用启动阶段被旧预算截断|
|头检查锁回归（纠正探针）|0/1；1 → 修复后迁移控制37/37；0|原始错误和修复证据分别留档|
|返回游标回归|0/2；1 → atomic+生命周期22/22；0|原生快捷游标旁路，已修复|
|Web新增契约回归|4失败；1 → 最终全部通过|CSRF、退出错误、401、HTTPS策略|
|中间完整回归|208/208；0|当时尚未显式检查全部子进程资源警告，不替代最终结果|
|原始命令209项复核|208通过、1失败；1|多进程子进程退出1，补诊断后定位侧文件竞态|
|严格子进程警告209项回归|208通过、1失败；1|真实检出TLS冷启动继承socket资源警告；已修复|
|补诊断后的多进程重复3次|2通过、1失败；1|堆栈定位sidecar access路径，不以单独成功掩盖|
|侧文件修复专项|53/53；0|50项nonce recovery加同一多进程测试重复3次；不是53个独立覆盖点|
|严格警告TLS修复后双项|2/2；0|父/子资源警告0；仍校验证书及拒绝冷启动|

逐条最终命令及运行时间：[acceptance-commands.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/acceptance-commands.json)。专项诊断失败、转义开发错误、错误解释器发现尝试均非部署证据；未删除相应保留日志。历史单项通过数不与本轮相加。

## G. 平台、秘密及产物审查

- 本范围内没有Android目录、Gradle项目或APK，因此不能验证Keystore、Token加密、APK是否对应源码，也没有尝试安装/更改SDK。SDK默认目录存在，组件元数据见[platform-environment.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/platform-environment.json)；环境变量是否设置和目录是否存在分别记录，不再沿用“SDK缺失”的假设。
- iOS为较旧SwiftUI工程：UserDefaults仅看到语言偏好；这不等于Token已在Keychain。当前native service只有读取既有session接口，没有阶段2的Keychain与原生登录/退出；HTTP配置仍可通过。这是当前树的明确缺口，未从其他工作树盲目复制补丁。
- `xcode-select`为CommandLineTools；xcodebuild和iPhone simulator SDK查询均失败。Swift Core能编译到运行断言，但实际失败；Swift语法通过不能证明SwiftUI可完整构建。
- `[scripts/check-device-migration.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/scripts/check-device-migration.py)` 仍有历史真实路径/端口默认值，会读取本机凭据和数据库；本轮只审查源码，没有执行该工具。不得拿它直接作为本次受控发布/真实恢复命令。
- `[scripts/start-local-mac.sh](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/scripts/start-local-mac.sh)`、package start及旧开发代理仍提供HTTP/8000启动方式；没有执行或修改真实配置。不能把当前全树默认启动作为已审查的安全发布包。
- Git忽略涵盖`.secrets/`、TLS私钥、固件凭据等；保留原有忽略规则。对公开文本及6个可达本地提交做有限模式检查，未找到该规则识别的私钥正文，发现演示密码比较/校验逻辑；补充检查还在历史backend/app.py定位到密码校验值模式，修改前差异含2处，均不输出其值。原始差异仅私有保留，报告链接为脱敏副本。没有读取正式密码来确认复用，不能声称“无秘密泄露”；须人工核实演示凭据未在真实账号使用。ttj/wyn原密码保留，不自动重置或轮换，也不重写Git历史。
- 无APK可扫描；生成Web产物仅供隔离回归，没有发布。常见模式扫描不覆盖未知格式、全部二进制、所有历史秘密；真实服务日志和真实凭据未获访问授权。详细范围与文件位置：[safe-source-scan.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/safe-source-scan.json)。

## H. 修改清单与保留情况

修改前证据：[before.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/before.json)、[before.diff.redacted](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/before.diff.redacted)。原90个公开源文件均存在，未丢失；branch和HEAD保持，未触碰其他工作树。

本轮修改的既有公开源文件（与修改前指纹比较，不把此前未提交修复算作本轮新增）：

- [backend/test_nonce_https_recovery.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_nonce_https_recovery.py)
- [backend/ledger_control.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/ledger_control.py)
- [backend/nonce_ledger.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/nonce_ledger.py)
- [backend/test_auth_https_isolated.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_auth_https_isolated.py)
- [backend/test_atomic_freeze.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_atomic_freeze.py)
- [backend/test_ledger_control.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_ledger_control.py)
- [backend/test_nonce_recovery.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_nonce_recovery.py)
- [backend/app.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/app.py)
- [backend/test_auth_hardening.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_auth_hardening.py)
- [scripts/test-atomic-freeze.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/scripts/test-atomic-freeze.py)
- [src/App.tsx](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/src/App.tsx)
- [src/App.test.tsx](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/src/App.test.tsx)
- [src/data/services.test.ts](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/src/data/services.test.ts)
- [src/data/http.integration.test.ts](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/src/data/http.integration.test.ts)
- [src/data/LiveApiService.ts](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/src/data/LiveApiService.ts)
- [src/data/config.ts](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/src/data/config.ts)

本轮新增：

- [backend/tls_test_support.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/tls_test_support.py)
- [backend/process_test_support.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/process_test_support.py)
- [backend/test_fixture_lifecycle.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_fixture_lifecycle.py)
- [scripts/audit-regression.py](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/scripts/audit-regression.py)

文档：[ATOMIC-UNIFIED-FREEZE.md](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ATOMIC-UNIFIED-FREEZE.md), [NONCE-LEDGER-RECOVERY.md](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/NONCE-LEDGER-RECOVERY.md)；本报告及audit-evidence目录。原始备份 `backend/ledger_control.py.before-header-fix` 保留。安装前端依赖仅使用 `npm ci --offline --ignore-scripts --no-audit --no-fund`，没有联网安装或修改系统SDK；node_modules/build为忽略的隔离产物。

最终源码指纹：[final-code-freeze.json](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/audit-evidence-20261029/final-code-freeze.json)。报告生成时再次校验全部指纹相等，防止测试后代码改变。

## I. 部署阻塞清单及解除条件

1. **BLOCKER：真实写入者覆盖未知。** 另获只读现场核验授权，列明实际进程、worker、父进程/启动管理器、代码快照、所有库写入路径；维护窗口确认旧进程和自动拉起已停止/升级为统一gate。不能仅靠JSON声明。
2. **BLOCKER：真实备份新鲜度、恢复和回滚无证据。** 需要冻结前后外部可信最新checkpoint、全部关联文件一致性和经授权副本演练；当前权威历史无法证明完整时禁止恢复接收。真实账本本轮未读，不能保证转换适用。
3. **BLOCKER：移动端集成源码不完整。** 在获准范围定位并审核阶段2真实补丁来源，再验证Keystore/Keychain、登录/恢复/退出/失效、TLS、不明文存储；Android完整构建和两端真机须另行验收。不能发布本树旧移动端。
4. **BLOCKER：iOS Core实际失败。** 先确认当前传感器/指标契约，不以降低告警获取green；统一规则/向量后重跑Core，再用完整Xcode构建。
5. **BLOCKER：没有审核过的最小发布包/启动恢复配置。** 后端工作树包含尚未部署的阶段1代码、大量未跟踪修复和旧HTTP启动器。须审核精确文件、依赖、解释器、三个数据库路径无别名、私有control-root/registry和所有启动器的统一配置。不能直接运行npm start当安全部署。
6. **BLOCKER：真实TLS/地址/入口与运行版本未验证。** 在恢复正确热点后另查实际IP、监听、SAN、有效期和信任链，不假定历史IP仍有效；核实真实入口运行此版本，再按批准计划进行真实负向测试与重启恢复验收。
7. **发布前安全决策：演示凭据/历史暴露可能性。** 确认真实账号未复用公开演示凭据、也未继续对应历史已跟踪的密码校验值。历史校验值可支持离线猜解，当前改Argon2id不能撤回既有暴露；若仍对应真实账号，需用户决定如何处理或明确接受保留原密码的剩余风险。没有擅自重置ttj/wyn或真实设备密钥。
8. **性能与故障风险仍需验证。** 全历史检查/永久保留有容量与时延成本，尚无真实负载、磁盘满/ACL/断电验收；不能通过删nonce或跳过完整性检查解决。

## J. 后续安全步骤（仅方案，未执行）

先审核本报告和最终差异；隔离后端通过只能解除源码层问题。明确移动端版本与iOS指标契约并完成构建验收。之后另获授权只读核对真实启动管理、配置名称和证书；再提交包含完整备份、外部最新性证据、全部写入者冻结核验、停机边界和兼容最新v2回退方案的具体维护计划，等待人工批准。只有维护授权后才能冻结、转换、验证、切换与恢复写入；任一步证据不足保持冻结/拒绝，不猜测恢复。当前不提供带真实路径的重启或迁移命令，也没有执行这些操作。

**审计工作停止在此报告，生产部署仍为NO-GO。**
