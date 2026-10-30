# 显式转换、请求冻结与受控切换

2026-10-29。本说明对应新增的控制协议；**尚未部署，不构成真实网关操作授权**。当前独立修复树中的通用 app、device_ingress 与 controlled factory 已接入统一 gate；实际部署仓库及现有服务没有修改。详见 ATOMIC-UNIFIED-FREEZE.md。

## 控制范围与必要信任条件

新入口 `backend.controlled_device_ingress:create_from_environment` 是独立 factory，只提供设备上报与健康检查。每次 POST 获得进程间共享 gate 锁，直到认证、原 receive_sensor_data 处理（包括读数提交）及响应处理结束才释放。认证仍检查 HTTPS、独立 API key、HMAC、时间窗和持久 nonce，不切换进程环境变量，不改签名契约。

所有接收进程必须指向同一个控制根目录、同一个不可替换 gate inode。管理操作另用排他 admin 锁。替换任一锁文件、丢失状态、变更 inventory 或状态引用的审计事件都会拒绝，不自动修复。

**文件锁只能约束使用此协议的接收者。** 旧 v1 入口不认识 gate；不能仅靠“创建锁文件”声称它已冻结。首次接管必须在另行授权的维护窗口，审核全部旧进程、worker、启动管理器及自动拉起并确认旧写入者停止。工具要求私有 inventory 审批记录，绑定源绝对路径、设备号/inode、完整历史检查点、审核引用和有效期，确认全部写入者受控及旧写入者已停止。工具核验记录与输入的一致性，**不把该记录当作自动完成的 OS 进程取证**。

真实 inventory、旧进程停止证据和真实历史当前均未核验；缺少它们不得执行真实接管。拥有同一用户权限并可协调回退全部文件的攻击，不由本地 JSON/flock 解决。

## 文件和输入

- `state.json`：原子替换、文件/目录同步的唯一已提交状态；包含当前路径、阶段、检查点、inventory 指纹及对应事件引用。
- `gate.lock`、`admin.lock`：接管时排他创建，设备号/inode 固定；禁止删除替换。
- `event-序号-随机标识.json`：先持久写事件再发布 state。事件只含阶段、序号和时间；孤立未提交事件保留，不作为成功证据。
- `<generation>/nonce.db`、`.initialized`、`.initializing`：独立目标文件对与迁移意图。保留 SQLite 侧文件及失败残留，不覆盖已有 generation。
- inventory：本机私有审核输入，不输出内容。必要字段：`source`、`device`、`inode`、`checkpoint`（count、digest）、`review_reference`、`expires_at`、`all_writers_controlled=true`、`legacy_writers_stopped=true`。digest 是按四列全量排序、固定 JSON 编码计算的逻辑摘要；不是 nonce/HMAC 密钥，也不是备份新鲜度的独立信任锚。

文件由当前用户拥有、0600，目录0700，拒绝符号链接、多硬链接、共享权限、OS 读写拒绝、悬空初始化意图、危险 SQLite 侧文件和重复 JSON 键。工具不会 chmod 或补建缺失运行文件。

接管仅接受非空、已知 v1/v2、完整性检查通过且历史与审批检查点完全匹配的输入。v1 必须有准确旧 marker、四列结构/类型/联合主键、WITHOUT ROWID，无未知额外对象；v2 须精确 schema、metadata/marker/计数一致。未知格式、坏行、空历史一律拒绝，不丢弃异常行来“修好”。

## 状态机

```text
独立审核后的 offline enrollment → FROZEN（已确认检查点）
ACTIVE → FROZEN（checkpoint=null，开始拒绝新请求）
       → 排空共享锁 + SQLite writer transaction → FROZEN（最终检查点）
FROZEN → COPYING → VERIFIED → SWITCHED → 显式 resume → ACTIVE
COPYING / VERIFIED / SWITCHED → 显式 recover-frozen → FROZEN
```

1. freeze 先在共享锁下持久化 FROZEN，使后来的请求立即503；在途共享锁持有者可完成整个请求。
2. 在管理锁内等待 gate 排他锁（默认10秒，最多30秒）。超时仍保持 FROZEN/null，禁止 prepare；排空后重试 freeze。
3. 获得排他锁后再持有源 SQLite BEGIN IMMEDIATE，校验并记录最终历史检查点。SQLite 锁进一步阻止迁移期间的其他 SQLite 提交，但不能证明旧进程在锁释放后不会写旧路径。
4. prepare 在管理锁、排他 gate 和源 writer transaction 下进行；检查源仍与冻结检查点一致。新 generation 排他创建，先持久化 COPYING 与迁移意图，再用 SQLite backup 从 RO 连接取得完整 WAL 快照。
5. v1 在目标副本单事务内重建精确 v2 schema、复制全部四列并保留所有设备、时间值；计数 trigger 与插入同事务。v2 副本保持已有格式。核对全部历史等价，提交和同步数据库、marker、目录后撤销意图，再用实际 NonceStore 检查，最后发布 VERIFIED。
6. switch 再次检查源与目标完整性及全部历史一致，以一次原子 state 发布选择整套目标路径，进入 SWITCHED；不会逐个覆盖在线库/marker。
7. resume 再检查当前 v2、历史检查点和控制状态才发布 ACTIVE。重启管理进程不会自动 resume。实际接收进程每个请求读取已提交 state，无需改变全局环境或重启其他服务。

freeze 超时、坏输入、权限失败、备份缺历史及不完整候选均不开放接收。首次 enrollment 失败残留不能自动重新接管；须人工审查。已运行控制器的迁移失败可 recover-frozen，但仅在当前权威源仍完整匹配冻结检查点时；保留所有候选和事件，下次必须使用全新 generation 名称。

## 操作界面（仅供审核）

工具：`scripts/manage-nonce-migration.py`，没有任何默认真实路径。

```text
<Python> scripts/manage-nonce-migration.py --control-root <审批绝对目录> enroll-offline
  --source <审批源账本绝对路径> --inventory <私有审批记录绝对路径>
  --confirm-audited-offline-adoption
<同一工具及 control-root> freeze --drain-timeout 10
<同一工具及 control-root> prepare --generation <全新代名称>
<同一工具及 control-root> switch
<同一工具及 control-root> resume
<同一工具及 control-root> recover-frozen
<同一工具及 control-root> status
```

输出只包含 PASS/FAIL、阶段和序号；错误不打印底层异常、路径、SQL或认证信息。`status` 不代表全系统写入者已经核实。

新 factory 要求显式绝对路径变量 `CARELINK_LEDGER_CONTROL_ROOT`、`CARELINK_DEVICE_REGISTRY`、`CARELINK_DATABASE_PATH`。以后单独批准启动时需保持 Uvicorn TLS 证书/私钥 flags、`--no-proxy-headers --no-access-log`，由批准的网络/SAN 决定绑定地址。本文不提供或执行带真实路径的启动命令，不改变原入口。

## 备份及恢复约束

冻结完成后保存：一致性 ledger 快照与准确 marker、存在的 intent 和 SQLite 侧文件现场、必要读数库快照、代码/依赖/入口/配置路径清单、冻结最终检查点、独立保护的最新备份审计材料。不能直接复制在线主文件，也不能用读数反向重建 nonce；两库不是跨库原子事务。

`prepare --generation <新名称> --backup <审批完整v2副本>` 是**保留当前完整历史的恢复准备**：必须有可验证的当前权威账本、有效冻结检查点，备份全部四列须与当前历史完全相等。少任何后续 nonce、损坏或 marker 错配均拒绝。它不是“只要备份文件存在就可还原”，也不合并猜测冲突历史。

当前权威账本已丢失/损坏时，freeze 或 prepare 拒绝；本版本不提供绕过此检查的灾难恢复。以后必须另行建立可信最新检查点与完整备份的独立验证协议，不能使用旧 state 中 ACTIVE 前的陈旧摘要作为最新证据。

v2 消费新 nonce 后，不允许回到迁移前 v1 快照。代码回退只能使用兼容最新完整 v2 且 fail closed 的版本；不能恢复旧自动建空库构造器。无法证明完整历史时保持拒绝接收，不创建空账本、不删标记、不降级 HTTP。

## 验证范围与剩余阻塞

当前仅合成临时目录测试，ASGI 测试使用模拟 HTTPS scheme，未启动新监听端口；不等同真实 TLS 握手或真实数据入库验收。新 middleware 复用原接收函数，但端到端原接收函数的受控真实数据库/硬件联调仍待批准后验证。

必须先完成真实写入者/监督器清单与离线接管证据、真实备份来源与新鲜度、经批准副本演练、最小发布包审核、Mac 文件锁/磁盘/权限/容量评估及维护授权。真实备份、真实恢复、真实回滚、真实接收链路切换均 NOT VERIFIED。全部控制文件和 ledger 一起被协调回退仍需要独立信任锚；本地完整性不证明最新。
