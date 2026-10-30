# CareLink 最终加密与安全进度报告

日期：2026-10-30。结论：**NO-GO，未部署**。

## 1. 范围、证据与判断规则

本轮继续原独立工作树与分支，没有创建项目、切换工作树或提交。实际路径为 `/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic`；用户最新消息的 `this-an-3` 路径不存在，已按既有环境核对后沿用 `this-is-an-3`。分支 `fix/nonce-atomic-freeze-20261029`。开始状态/公开文件摘要见 [before.json][before]；先盘点再修改的记录见 [修改前盘点][inventory]。

已读取上一轮[修复报告][prior]、[授权手册][manual]、P2测试证据及实际源码。历史测试数字只用于比较。本轮没有访问真实数据库、nonce ledger、生产凭据或真实证书，没有探测真实服务、打开串口、连接硬件、迁移、恢复、冻结或重启9443/18443/18444，也没有部署后端或移动端。

状态含义：PASS仅表示该列指定范围有证据；PARTIAL表示实现/局部测试成立但必要部署证据缺失；FAIL表示已知条件未满足；NOT VERIFIED表示未获证据或本轮未获授权。源码接线、隔离回归、完整平台构建、真实服务和真机是不同验收层。曾经的硬件/Web验收不能证明本分支今天已部署。没有用百分比衡量完成度。

## 2. 八项加密与安全实现盘点

|控制与机制|源码实现|本轮自动化/静态证据|真实运行/设备|总体及必要剩余事项|
|---|---|---|---|---|
|C10 设备身份：HMAC-SHA256，原始body SHA-256，API key摘要与恒定时间比较|PASS；服务器三入口接入，先认证后业务|设备认证/入口/原生TLS测试；完整结果见第7节|NOT VERIFIED；本轮未读注册表或查看运行模块|PARTIAL；核对真实发布源、注册表权限与每设备独立密钥；本树固件来源缺口见2.1|
|C11–C14 时间窗、原子nonce、防重放、fail-closed|PASS；±60s，锁后复检，SQLite唯一键和提交后receipt|线程/多进程、重启、事务/异常退出、损坏/缺失状态、拒绝零额外业务写入测试|NOT VERIFIED|PARTIAL；需真实写入者、存储与重启验收；全套历史一起回退需外部可信证据|
|C20 TLS及服务器身份|PARTIAL；客户端已接入验证，服务器依赖正确TLS终止/配置|原生临时CA、链/SAN/过期/错误信任与实际隔离FastAPI测试|NOT VERIFIED；无真实证书、SAN、监听/网络或在线握手检查|PARTIAL；批准后核对实际地址、CA、主机、启动方式，禁止套用历史IP|
|C02–C09 Web账号、Session、Cookie/CSRF/CORS/权限|PASS；Argon2id、渐进CAS迁移、随机可撤销Session已接入实际路由|密码/并发迁移、Session重启、注销/轮换、限速、越权、来源/CSRF及Web回归|NOT VERIFIED；正式账号库和生产认证未读/未部署|PARTIAL；确认正式库归属、可信迁移和最新撤销恢复方案；保留ttj/wyn原密码|
|C23–C24 iOS凭据、登录/轮换/退出|PASS（源码接线）；Keychain接口、按原Token清理、代次检查|Core/内存存储与交错认证测试、原生TLS、App源解析和project校验|NOT VERIFIED；完整iOS构建与真机Keychain缺证据|PARTIAL；需完整Xcode/SDK、签名/资源配置与锁屏/重启等真机验收|
|C22 Android凭据/认证/TLS|NOT VERIFIED；当前树没有实际Android/Capacitor工程|NOT VERIFIED；无Gradle/APK或移动端可执行测试|NOT VERIFIED|NOT VERIFIED；先取得实际工程，按手册第13节接线验证，不能沿用历史实现声明|
|C15–C16 SQLite访问控制/完整性/冻结|PASS（所审源码域）；私有文件、绑定、租约及排空|新旧路由/连接/游标、路径隔离、未排空与权限故障测试|NOT VERIFIED；不证明全部真实写入者受控|PARTIAL；真实PID/旧版本/直接SQL/监督器核验是阻塞；SQLite不是加密数据库|
|C17–C19 备份、转换、恢复/回滚|PASS（合成工具流程）；独立性检查、全历史比较及冻结checkpoint|独立副本/别名/旧备份/错配/损坏/中断/恢复/认证撤销快照测试|NOT VERIFIED；真实备份最新性、灾难恢复、真实回滚未验证|PARTIAL；外部最新证据、授权副本导入及认证库恢复须单独完成|

### 2.1 设备请求：实际调用和密钥存放

[device_auth.py][device] 的 `canonical_request` 使用7行ASCII、LF分隔且无末尾LF：协议版本、方法、路径、设备ID、十进制时间戳、nonce、精确原始请求体SHA-256。只接收规范POST `/sensor-data`，拒绝查询串/重复认证头/错误体格式；签名验证用HMAC-SHA256与`compare_digest`，API key使用SHA-256摘要比较。HMAC是消息认证，body摘要是哈希；它们不加密传感器数据，保密性由TLS提供。

调用已接入 `app /sensor-data → authenticated_sensor_payload → authenticate_payload → NonceStore.reserve → AcceptedSensorPayload → receive_sensor_data/consume_receipt → readings+alerts事务`。[device_ingress.py][ingress]复用同一receiver；[controlled_device_ingress.py][controlled]通过依赖替换使用受控ledger。这不是只定义未调用的类。

设备注册表从`CARELINK_DEVICE_REGISTRY`指定的本机私有JSON读取（未设时源码有`.secrets`默认路径，**不是本轮确认的真实路径**）。API key存摘要；HMAC256-bit对称密钥必须以可读取形式保存在本机私有配置并装入内存，不能只存不可逆哈希替代验证密钥。检查格式、独立性、enabled和文件类型/权限，注册表身份变化后重新加载。`.secrets/`、firmware秘密头与私钥格式已忽略；Git忽略不等于磁盘加密/历史清除。真实文件没有读取，固件secret头没有检查。

**固件发布来源仍缺证据**：[当前公开Arduino源码][firmware]未发现`WiFiClientSecure`、`setCACert`、HMAC/mbedTLS或时间同步接线，见[公开源码检查结果][firmware-scan]。这不否认历史真实设备200记录，但说明此工作树固件不能被认定为当时安全版，不能发布整树或据此重新烧录。没有读secrets或猜目标地址，没有改固件。必须以后授权对照实际已烧录工程、版本/摘要及编译输入；当前设备协议来源NOT VERIFIED。

### 2.2 原子占用与持久化边界

[nonce_ledger.py][nonce]先检查既有ledger/marker/intent/控制绑定/权限/链接身份、精确schema和metadata计数，再`BEGIN IMMEDIATE`；占用使用`UNIQUE(device_id,nonce)`/主键约束和事务提交。等待锁后再次读取当前时间验证±60s。连接上下文成功commit后才返回占用成功，随后才创建内部receipt；失败没有receipt，业务入口拒绝直接dict/跨ledger/重复消费。相同请求可分别通过无副作用的签名检查，但完整认证成功只能有一个；测试分别记录认证、占用、HTTP、业务计数和数据库增量，不能靠最终行数判断。

WAL、`synchronous=FULL`、历史不可更新/删除trigger、异常关闭回滚提供持久化/并发约束。账本先提交、业务后提交：保证最多一次接纳；不承诺跨两个SQLite数据库的“恰好一次投递”。占用提交后业务失败可能消耗该nonce但没有读数；恢复/重试不能删除已占用nonce，设备应生成新的合法请求。这是保守拒绝重复业务的取舍。

运行只打开已有`mode=rw`文件，不因账本与marker一起丢失就新建。新安装工具显式授权且拒绝任一遗留artifact，包括`.control`；旧v1需显式离线转换。恢复错误均不能自动补标记、清空历史或放开写入。

### 2.3 TLS、Web和存储层

- TLS：[SecureTransport.swift][transport]接入LiveApiService，最低TLS1.2、ephemeral URLSession、禁共享Cookie磁盘/缓存/credential storage、禁止重定向；系统默认信任或明确公开DER根、`SecPolicyCreateSSL`绑定主机、`SecTrustEvaluateWithError`验证链/时间/身份，无trust-all。服务器的HTTPS scheme检查不是TLS终止器；Uvicorn证书/私钥flags或受审反向代理仍是部署条件。私钥仅部署环境持有，本轮未读真实证书或钥匙。
- [web_auth.py][auth]的Argon2id：64MiB、t=3、p=1、16-byte随机盐、32-byte哈希。PBKDF2-SHA256旧校验值只在受限参数白名单中兼容，原密码验证成功后Argon2id重哈希，以旧校验值CAS更新；并发失败者重读重新验证，不覆盖新凭据。账号不存在/错密码相同响应；内存/工作量限制降低滥用，不能声称网络时序完全不可区分。不强制重置/轮换ttj/wyn。
- Session为32-byte CSPRNG `token_urlsafe`，服务器只存SHA-256(Token)，浏览器通过`carelink_session`持有；8小时绝对过期、数据库持久撤销与原子轮换，轮换不延长原期限。`/api/login`、`/api/session`、`/api/logout`、`/api/session/rotate`均实际接入。Token摘要不是加密，也不是可直接复用Token。
- [app.py][app]设置Secure、HttpOnly、SameSite=Lax、path=/；[web_security.py][websecurity]要求HTTPS可信同origin、限制CORS、拒绝重复安全头/cross-site来源，变更请求要求JSON和CSRF自定义头；`Depends(current_username)`/服务端患者范围与角色检查保护患者与告警。限速持久SQLite桶：15分钟、IP20/账号10/组合5，最多4096桶，拒绝429带Retry-After；测试override明确配置且有界。
- [Web配置][webconfig]、[LiveApiService][webclient]和`src/App.tsx`已接线；live需确认契约及HTTPS，浏览器自动Cookie，JS不持久化Token；fetch失败时XHR仍沿用同HTTPS URL和credentials，不能视为HTTP降级。源码保留mock演示配置，构建成功不证明部署为live，更不证明读取真实设备候选库。
- SQLite ledger/账号/读数均未使用SQLCipher等数据库加密。0700目录/0600文件、owner/inode/link检查、schema/quick_check/marker/计数、状态原子替换属于访问控制/完整性与恢复约束，不是保密加密，也不是带外认证的最新性证明。本地有权限攻击者同时回退完整有效集合的风险仍需外部锚点。文件系统加密/备份介质加密状态未验证。

### 2.4 iOS及Android接线

[SessionCredentials.swift][credentials]用SecItem generic password，以服务名和HTTPS origin隔离；`WhenUnlockedThisDeviceOnly`、不云同步，Keychain存Token+expiresAt。`LiveApiService → DemoStore → 登录/设置/退出UI`已接线，App默认使用真实Keychain实现；测试显式注入MemorySessionStore。UserDefaults仅UI语言等非秘密偏好。客户端重启恢复必须向服务器验证身份，客户端缓存角色不能授权。存储失败不回退普通文件或UserDefaults。

[LiveApiService.swift][ioslive]以MainActor、请求代次、原Session绑定及`removeCredential(matching:)`处理401、轮换、退出和切换账号；比较当前存储Token与原请求Token后才删除，比较到删除间无await。不会无条件删除另一个客户端刚存的新Token。离线退出会尝试清理本地，但明确远端撤销未确认；存储清理本身失败不能宣称成功。该设计与现有交错测试限同进程MainActor，不提供跨进程Keychain CAS保证。日后共享access group/扩展需另审。

当前允许的树中没有Android/Gradle/Capacitor工程或APK，不能核验历史提及的Keystore实现/APK一致性。没有擅自建立占位工程。范围、HTTPS Cookie契约、原生受控桥接、Keystore非导出AES-GCM密钥/密文存储及Gradle/真机标准已写入[手册第13节][manual]。默认SDK目录元数据检查未见platforms/build-tools；未安装、改变SDK或搜索别的项目。

## 3. P2修复与本轮必要补充

|项目|实际核验/修复|当前证据|结论边界|
|---|---|---|---|
|iOS共享凭据竞态|沿用既有按原Token比较清理，不重写已完成修复|SecurityChecks continuation交错：rotate/logout/switch-logout/login/switch-login × success/401/500/network/malformed；暂停A，写入B，恢复A，断言B保留、旧身份不能授权；206检查本轮重跑|PASS（同进程接口/内存替身）；真Keychain和跨进程NOT VERIFIED|
|verify-backup不能自证备份|既有resolve(strict)+samefile身份检查在SQLite打开前执行，错误解析同样拒绝|自文件、规范路径别名、目录链接、软链接、硬链接均拒绝；独立合法副本通过|PASS（隔离文件）|
|新发现prepare --backup旁路|新增共用`require_independent_backup`并接入显式prepare，在打开源SQLite和建generation前拒绝；省略--backup仍可显式转换源，不把它叫备份验证|修复前1个测试内5个子场景均FAIL；修复后相同断言通过，无生成物/状态变化，独立合法副本VERIFIED|PASS（隔离），未部署|
|坏/截断/无marker备份|新增验证用例；保留既有旧备份、同条数篡改、错marker/权限/源丢失测试|损坏头、截断、空文件、无marker都拒绝；源字节/状态保持，合法副本恢复校验成功|PASS（隔离）|
|认证库旧快照撤销回退|新增真实应用路由+合成数据库快照演练，未读取正式库|最新已撤销快照旧Cookie401；退出前快照旧Cookie200（明确UNSAFE诊断）；当前原测试库仍撤销|PASS（揭示风险的测试）；实际恢复能力PARTIAL，过期认证库不能用于恢复服务|

本轮只改4个既有文件：`backend/ledger_control.py`（共用独立性保护）、`backend/test_remediation_controls.py`（3个新增测试）、`backend/test_ledger_control.py`（原有恢复测试改用真正独立快照，断言保留）、`.gitignore`（本轮证据目录忽略）；更新授权手册并新增本报告/证据。其他修改与未跟踪文件均是原有状态，未宣称本轮所有。既有iOS P2源与测试不变。

修复前失败证据原样保留：[prepare-independence-before.log][redlog]。不是最终回归失败被掩盖；这是固定回归用例发现遗漏的证据。后续定向57项和Session单测已通过，定向结果不叠加到全套计数。

## 4. 完整写入者覆盖矩阵（源码域与现场分开）

符号：D=配置的读数/告警库；A=独立认证库；L=Controller.state.active账本；C=control-root。下面是源码路径归属，**不是本轮确认的真实文件路径/进程**。

|潜在写入者、调用入口/启动方式|写什么|源码保护/冻结覆盖|隔离证据|真实进程覆盖|
|---|---|---|---|---|
|backend.app:app POST /sensor-data|L占用；D readings+告警|UnifiedWriteGate共享租约覆盖认证到业务结束，guarded_write+receipt；冻结503|旧入口并发/冻结/路径切换|NOT VERIFIED|
|backend.device_ingress:app POST /sensor-data|同上|复用同receiver、gate及preflight，不独立绕过|实际隔离路由测试|NOT VERIFIED|
|controlled_device_ingress:create_from_environment /sensor-data|同上|同control-root gate，受控依赖和动态active|新旧同时竞争、线程/进程、切换|NOT VERIFIED|
|_store_alerts/_upsert_alert/_resolve_inactive_alerts|D alerts|同接收事务+租约；占用失败无业务|读数/业务计数断言|NOT VERIFIED|
|GET /api/alerts → _ensure_connectivity_alert|D connectivity告警（GET也会写）|middleware覆盖/api/alerts及guarded_write|冻结时503，非只读GET|NOT VERIFIED|
|POST /api/alerts/{id}/acknowledgement|D告警确认|gate+guarded_write+服务器角色/患者权限|冻结/越权与功能回归|NOT VERIFIED|
|lifespan → initialize_database|D建表/索引；Web初始化A|D初始化受guarded_write；A独立策略，不能说A一起冻结|初始化/数据库错配/缺文件测试|NOT VERIFIED|
|app.connect/LeasedConnection/LeasedCursor及缓存游标|D底层SQL|实际执行/commit校验有效租约，非写租约查询query_only，运行mode=rw不建库|租约结束/冻结后返回游标和连接拒绝写|NOT VERIFIED；外部sqlite直连不受这些包装约束|
|NonceStore.reserve/connect（已绑定）|L历史/计数|绑定同gate；BEGIN IMMEDIATE、唯一键、authorizer、提交检查|并发、异常退出、直接低层绑定路径测试|NOT VERIFIED|
|未绑定底层NonceStore/SQLite API|合成新L/管理阶段|显式初始化/接管的低层能力；不自动被HTTP gate证明覆盖|仅合成工具场景|NOT VERIFIED；若现场有直接调用必须列入inventory，阻塞|
|/api/login|A限速桶、密码CAS迁移、Session|A独立事务/私有权限/路径隔离；**不在设备冻结域**|冻结期间登录/退出仍可用测试|NOT VERIFIED；恢复A需单独维护边界|
|/api/logout、/api/session/rotate|A撤销/轮换|A事务持久化；不受nonce gate冻结|注销401、轮换旧Token失效/重启|NOT VERIFIED|
|AuthStore.initialize/bootstrap_accounts|A schema/一次兼容导入|已存在库权威，运行不自动重置；私有bootstrap校验；不受device gate|缺配置失败/防默认账号/并发迁移|NOT VERIFIED|
|manage-web-auth.py prepare/rotate；AuthStore.change_password/replace_password_hash|显式新A或单账号哈希+撤销|绝对目标/交互确认/隐藏输入/新目标保护；不受device gate|无TTY/无隐藏输入拒绝、副作用测试|NOT VERIFIED；不是ttj/wyn部署重置步骤|
|manage-nonce-migration.py enroll/freeze/prepare/switch/resume/recover|C状态事件/绑定；候选L|admin排他+gate排他+source writer transaction；未排空拒绝；失败冻结|进程竞争、中断/恢复、历史/备份测试|NOT VERIFIED；inventory是人工证据，不能代替现场取证|
|initialize-nonce-ledger.py|全新L/intent/marker|显式授权、O_EXCL、遗留artifact拒绝；不是恢复路径|双缺失/遗留.control/中断测试|NOT VERIFIED；不得对既有环境运行|
|check-device-migration.py|只读检查；可写指定报告文件|需显式config-root和批准；network模式拒绝；不是写入冻结器|无默认读取/拒绝网络测试|NOT VERIFIED；本轮未执行真实检查|
|历史start-local-mac.sh、npm start:api/start:web、simulate-sensor.mjs|启动器/HTTP模拟发送；最终写接收端|不是安全发布入口；新源码接收端要求TLS/HMAC/gate|仅源码检查，未运行这些服务/模拟器|NOT VERIFIED；不能拿旧命令部署|
|server.mjs、Vite静态预览|本机静态/演示页面，无该文件直接SQL写入|不属于ledger写入锁；不是正式TLS终止器|源码/Node/Web测试|NOT VERIFIED；18444实际实现不在此审查边界|
|生成脚本/构建脚本、模型训练脚本|工作树静态资源/模型/构建产物|不是nonce/认证写入者；不得以冻结代替发布权限控制|本轮只运行已审核本地生成/测试构建|NOT VERIFIED（真实调度情况）|
|测试夹具/隔离接收器|TempDirectory合成D/A/L及随机loopback服务|显式测试路径、清理所属进程；与真实服务分离|本轮完整回归|不属于现场进程证据|
|launchd/cron/父进程/多worker/外部SQLite/旧拷贝/未知后台任务|未知|文件锁不能强制不配合者遵守；未审运行者不能视作冻结|无现场权限，不推测|NOT VERIFIED；部署阻塞|

[write_gate.py][gate]、[storage_paths.py][paths]动态隔离active/candidate/previous/原inventory源、control-root和SQLite侧文件，避免A/D/L混用。源码域内新旧HTTP路由受统一冻结；查询路径的数据库租约也可能在冻结时返回503，前端必须显示不可用/过期。它不代表旧的实际内存代码或其他项目已更新。本轮没有操作carelink-live或查其文件。

## 5. 独立备份、恢复与回滚证据/缺口

1. 源存在且已冻结排空时，`verify_backup`可证明独立文件与当前源的全部device_id/nonce/signed_at/accepted_at历史相等；marker/格式/计数/schema/quick_check须成立。v1到v2显式转换保存全部四列，不自动转换旧账本。现有verify-backup要求v2源/副本；v1离线接管依赖审核inventory与源checkpoint，不能拿v2校验接口成功代替v1备份审批。
2. 同文件身份保护覆盖verify和显式prepare；同路径/目录别名/软硬链不能自证。独立inode仍可能处于同一磁盘/权限/灾难域；“存在备份”不等于“可恢复且最新”。
3. 合成测试覆盖v1转换、完整v2恢复、switch/recover中断、进程竞争、权限/部分文件错配、旧备份缺后续nonce拒绝、全部历史相同及历史重放409。源缺失时拒绝，不自动从备份建新权威；不清理失败现场。
4. 真备份最新性、不可变/外部checkpoint、冻结全覆盖、故障时fsync/介质行为、整个文件集合被回退、真实灾难恢复工具/授权副本导入均NOT VERIFIED。不能声称有可用的真实回滚。转换工具不提供缺源灾难恢复证明，也不提供认证库恢复。
5. 本轮合成认证恢复演练已证明旧A快照可复活撤销Session；必须独立证明A的撤销、禁用、权限和密码迁移状态最新，或另行批准可证明失效方案；不能为解决回滚风险自动重置原密码。
6. 手册已补文件/故障域独立性、可信清单与完整历史checkpoint、授权副本隔离、不得复制仍指真实路径的state就运行、恢复后nonce/Session行为、失败保持冻结及审批层次。没有执行真实副本复制或恢复。详情见[授权手册第10–14节][manual]。

## 6. iOS完整构建、真机与Android现状

Xcode project的Sources包含LiveApiService、SessionCredentials和SecureTransport；单一CareLink App target，iOS deployment target17.0、Swift5、自动签名、bundle ID com.carelink.demo。共享scheme有Build/Launch/Profile/Archive，**没有XCTest TestAction/test target**；Core/security/TLS由独立macOS脚本执行，不能称xcodebuild test成功。公开配置模板不能代替真实构建资源与签名，私有配置本轮未读取。

|环境检查命令|退出码|实际结果|
|---|---:|---|
|`xcode-select -p`|0|`/Library/Developer/CommandLineTools`|
|`xcodebuild -version`|1|当前活动目录不是完整Xcode|
|`xcrun --sdk iphoneos --show-sdk-path`|1|iphoneos SDK找不到|
|`xcrun --sdk iphonesimulator --show-sdk-path`|1|iphonesimulator SDK找不到|
|`swift --version`|0|Swift5.8.1，arm64 macOS|

以上是环境不具备条件的实际失败，未隐藏或计入测试跳过。没有运行注定缺SDK的完整App build命令，也没有伪报完整构建通过。

App完整构建：**NOT VERIFIED（SDK缺失，未执行完整build/archive）**。没有擅自安装Xcode/SDK或更改开发目录。15个App Swift源解析、macOS Foundation安全层编译/运行及project结构通过只说明各自层次。真实Keychain写读/重启/锁屏/首次解锁/存储不可用、App签名/entitlements、真实端到端账号和TLS均NOT VERIFIED。手册第12节列逐项设备证据要求，不能用MemorySessionStore206项替代。

Android：当前工程实现、完整构建、APK来源一致性、Keystore与真机均NOT VERIFIED。手册第13节定义业务范围和后端Cookie/CSRF/权限契约、Keystore AES-GCM/IV/认证标签/密钥失效、原生网络/桥接边界、TLS错误拒绝、应用生命周期、构建产物和测试标准。无假工程或无业务占位类。

## 7. 本轮测试命令、结果及警告

全部在本工作树运行；Python使用既有`.venv`，未安装依赖，测试启动的网络仅为随机本机隔离端口/临时CA。命令完整参数、退出码、时长和日志映射见[commands.json][commands]；`PYTHONDONTWRITEBYTECODE=1`、`PYTHONTRACEMALLOC=10`，Python使用`-W always::ResourceWarning`。没有屏蔽警告或放宽断言。环境探测原命令/退出码见[environment.json][environment]。

|检查|命令（工作目录为本报告第1节）|退出码|数量/结果|失败/跳过|警告事件|日志|
|---|---|---:|---|---|---|---|
|Python（全部发现）|`./.venv/bin/python -W always::ResourceWarning scripts/audit-regression.py <本轮绝对路径/python.json>`|0|234/234|0/0|0|[python.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/python.log)|
|Node＋React|`npm test`（含pretest）|0|Node20/20；React32/32|0/0|1 ExperimentalWarning|[web.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/web.log)|
|Web构建|`npm run build`（含prebuild；tsc --noEmit＋Vite）|0|通过，非测试计数|不适用|0|[build.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/build.log)|
|iOS Core|`sh ios/test-core.sh`|0|118项检查|0/0|0|[ios-core.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/ios-core.log)|
|iOS认证/存储接口|`sh ios/test-security.sh`|0|206项检查；内存替身|0/0|0|[ios-security.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/ios-security.log)|
|原生隔离TLS|`sh ios/test-tls.sh`|0|19项检查；非OS Keychain|0/0|0|[ios-tls.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/ios-tls.log)|
|App Swift语法|`swiftc -frontend -parse`＋15个源文件（精确argv见commands.json）|0|15源解析，非完整构建|不适用|0|[swift-syntax.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/swift-syntax.log)|
|Xcode工程结构|`plutil -lint ios/CareLink.xcodeproj/project.pbxproj`|0|通过，非App编译|不适用|0|[project.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/project.log)|
|差异空白检查|`git diff --check`|0|通过|不适用|0|[diff-check.log](/Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/diff-check.log)|

当前发现234项＝历史231个同名Python测试全部保留＋3个新增方法；删除0，跳过0。新方法如下（子场景不单独累加为测试方法）：

- `backend.test_remediation_controls.RecoveryEvidenceTests.test_corrupt_truncated_or_unmarked_backup_cannot_change_authority`
- `backend.test_remediation_controls.RecoveryEvidenceTests.test_prepare_explicit_backup_rejects_source_aliases_before_sqlite_or_generation`
- `backend.test_remediation_controls.RemediationWriterTests.test_auth_backup_restore_requires_latest_revocation_state`

iOS206、Core118、TLS19和Node/React各自单位不同，没有相加成总覆盖率。此前149、183、230等历史轮次不参与当前测试总数。

阶段性证据：定向`backend.test_remediation_controls backend.test_ledger_control`运行57项，退出0，失败/错误/跳过/警告0；随后新增Session恢复单测1项退出0。它们不是全套额外测试数，不与全套相加。修复前回归用例1项运行、5个alias子场景失败、退出1，保持在redlog，修复前后断言相同。

Python主进程警告0；40条受检查子进程流的ResourceWarning合计0。Node有1次`ExperimentalWarning: localStorage is not available because --localstorage-file was not provided`（日志另有1行提示如何trace warnings，不另计一条警告）；其余本轮测试/构建日志警告0。Node提示仍保留，没有通过关闭警告或配置持久秘密存储掩盖它。源码语言偏好访问与Token存储不同；此提示不是密码或Session泄露证据。

覆盖证据包括：完整Python报告的逐条status、concurrency分阶段计数、TLS和recovery记录，iOS continuation交错与错误信任链检查，Node/React回归及构建日志。本轮PASS仅为隔离环境，不是对真实9443负向测试或真实重启/恢复的替代。

## 8. 本轮修改、证据与保留情况

- 必要保护修改：[ledger_control.py][control]；新增独立性/损坏备份/账号快照三项测试：[test_remediation_controls.py][remtests]；修正原恢复夹具使用独立备份：[test_ledger_control.py][controltests]。
- 文档：[授权验证手册][manual]、本报告；`.gitignore`新增`security-status-evidence-*/`。证据中不含真实凭据/证书/数据库；所有数据库、CA、密钥均为测试新建，未记录测试Token/密码/完整签名值。
- [tested-inputs.json][inputs]记录本轮143个公开输入文件SHA-256，包括源、测试、锁文件、依赖声明、构建/项目配置，不读取秘密配置。不等于完整生产发布/签名/依赖安装产物证明。最终差异和测试清单比较见[verification.json][verification]。
- 原有未提交修改、未跟踪文件、旧测试日志/快照/备份保留。iOS P2源未改；没有Git提交/推送/合并/reset/clean，也没有操作其他工作树。测试生成受审本地静态构建产物，不代表替换线上资源。

## 9. 部署阻塞清单与解除条件

|编号|必要条件/当前状态|风险与解除条件|
|---|---|---|
|B01 全部真实写入者|NOT VERIFIED|阻塞：批准只读PID/worker/cwd/解释器/父进程/启动管理/旧SQL入口核验；每个写入者及自动拉起方式有证据，再审核统一gate或获批停写措施|
|B02 真实TLS、网络与运行版本|NOT VERIFIED|阻塞：重连目标热点后检查实际IP、监听/SAN/信任链、实际代码版本及路由；不因临时网络变化改代码|
|B03 真实备份完整/最新/独立|NOT VERIFIED|阻塞：冻结排空后独立文件与故障域、完整历史及带外可信最新证据；文件存在/hash自洽不够|
|B04 真实恢复与回滚|NOT VERIFIED|阻塞：授权副本工具、nonce与认证域各自方案、历史旧请求/撤销Session及重启验证，失败保持冻结；无证明不得恢复写入|
|B05 正式账号库/迁移/认证部署|NOT VERIFIED|阻塞：正式归属与保护确认，原密码兼容CAS迁移、旧Session策略及部署配置审批；不自动重置ttj/wyn|
|B06 固件来源对应|NOT VERIFIED|阻塞：本树公开旧源缺安全协议，需对照已烧录安全工程/构建输入；不得据历史HTTP200认定当前发布包一致|
|B07 iOS完整构建/Keychain真机|NOT VERIFIED|移动端发布阻塞：完整Xcode及满足iOS17.0目标的SDK/签名、资源/公开CA配置及第12节真机证据；不妨碍隔离代码审核但不允许声称App验收|
|B08 Android工程/构建/真机|NOT VERIFIED|Android发布阻塞：获准实际工程、Keystore/TLS业务接线、APK对应、完整构建和真机证据；如另行批准明确排除Android，则须书面缩小发布范围|
|B09 最小发布包/启动与失败策略|PARTIAL|阻塞：当前大量未提交修改、历史HTTP启动器不等于发布工件；需固定源/依赖/SDK/配置、审过的工作目录/环境/监督器和fail-closed恢复手册|
|B10 历史秘密风险/数据保护|PARTIAL|未重新读取真实日志/产物/账号库；历史公开校验值风险不能靠忽略文件消除。用户保留原密码，不擅自轮换；部署前记录风险接受与访问/备份保护，其他确认泄露的密钥另行批准处置|
|B11 现场正反向/重启/Web真实数据|NOT VERIFIED|阻塞：仅在维护/测试授权后真实设备和批准测试身份检查；分别认证/占用/业务/HTTP/DB与最新时间，无mock回退。此轮未执行攻击或重启|

优先顺序：审核本报告和代码 → 限定只读现场证据授权 → 完整写入者与最小发布包确认 → 可信备份/授权副本恢复方案 → 移动端实际构建/设备与固件来源确认 → 明确维护窗口/受控迁移及现场验收授权。每一步都需要相应证据，不能把本轮修复授权扩大为部署权限。

**最终结论：隔离修复与适用回归的结果按第7节记录；真实部署的必要证据仍未闭合，维持NO-GO。下一步应先审核并取得限定范围的真实环境核验授权；本轮到此停止。**

[before]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/before.json>
[inventory]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/INVENTORY-BEFORE-CHANGES.md>
[prior]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/CARELINK-SECURITY-REMEDIATION-REPORT-20261030.md>
[manual]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/AUTHORIZED-GATEWAY-VALIDATION-RUNBOOK-20261030.md>
[device]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/device_auth.py>
[ingress]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/device_ingress.py>
[controlled]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/controlled_device_ingress.py>
[firmware]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/firmware/elder_sensors/elder_sensors.ino>
[firmware-scan]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/firmware-public-source.json>
[nonce]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/nonce_ledger.py>
[transport]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/SecureTransport.swift>
[auth]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/web_auth.py>
[app]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/app.py>
[websecurity]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/web_security.py>
[webconfig]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/src/data/config.ts>
[webclient]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/src/data/LiveApiService.ts>
[credentials]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/SessionCredentials.swift>
[ioslive]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/ios/CareLink/LiveApiService.swift>
[redlog]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/prepare-independence-before.log>
[gate]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/write_gate.py>
[paths]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/storage_paths.py>
[commands]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/commands.json>
[environment]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/environment.json>
[control]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/ledger_control.py>
[remtests]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_remediation_controls.py>
[controltests]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/backend/test_ledger_control.py>
[inputs]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/tested-inputs.json>
[verification]: </Users/tan/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-3/work/carelink-nonce-atomic/security-status-evidence-20261030/verification.json>
