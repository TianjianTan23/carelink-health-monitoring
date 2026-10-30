# 并发原子占用与统一冻结：当前修复约束

本文件适用于 `fix/nonce-atomic-freeze-20261029`，仅隔离开发与测试。没有改变真实运行仓库、服务、配置或账本；不能把测试通过当成生产验收。

## 原子性与认证顺序

HTTP请求先取得统一共享写入租约，然后检查TLS scheme、重复头、正文大小、API key/HMAC、规范路径/方法、时间窗、JSON及设备绑定。随后在SQLite BEGIN IMMEDIATE中再次检查时间，INSERT唯一(device_id,nonce)，FULL同步提交成功后才返回带账本身份的内存认证凭据。业务入口校验并单次消费该凭据，最后才分类、写读数和告警。任何nonce失败都不能创建此凭据。

SQLite UNIQUE、writer transaction及WAL继续承担原子占用。修复的关键是移除 `_file()` 对SQLite主库/WAL/SHM额外open/close：这类close可释放同进程其他连接的记录锁，原先“更多检查”反而破坏了并发保证。当前使用lstat、所有权/链接数/权限、os.access及不可变标志检查，再由SQLite mode=rw、实际事务/提交确认可写性。没有chmod、setInsecure或降低时间窗。

凭据不是浏览器Token，不加入JSON或SQLite raw_payload；普通请求dict不能伪造，凭据只能在匹配的当前租约中使用一次。持久nonce已提交后业务失败或进程退出，nonce保持消费；重试同nonce拒绝。进程在提交前退出，SQLite回滚未提交状态，新请求可占用一次。

## 统一冻结覆盖

隔离树的 `backend.app:app`、`backend.device_ingress:app` 与 `backend.controlled_device_ingress:create_from_environment` 共用 `UnifiedWriteGate`。`/sensor-data` 和全部 `/api/alerts` 路径在认证/业务之前取得同一gate共享锁，处理完成才释放。冻结拒绝新请求503，等待既有请求排空，不能仅关闭新入口宣称冻结。

直接业务函数 receive_sensor_data、启动数据库初始化、连接告警与告警确认也要求租约。关联读数连接和游标在每次执行/提交时校验租约，拒绝无租约DML/DDL；GET告警也可能写库，必须受控。账号/session库是独立Web认证状态，不作为nonce迁移对象，仍需确认没有路径别名。

绑定账本的底层 reserve 会自动遵守同一控制目录及冻结状态，不能因绕过HTTP而继续占用。底层NonceStore连接的修改语句也要求有效租约。未绑定的显式新安装/单元夹具账本仍可用于底层测试，但HTTP和受保护业务入口始终不能在缺少gate时接收写入。

每个已管理账本额外持有私有 `<ledger>.control`，绑定 control_root 与 gate inode。第二控制目录不能接管同一账本。转换后的generation发布前建立同一绑定；旧HTTP入口读取gate选定的账本，切换后不再按陈旧nonce环境路径写旧文件。绑定缺失、错配或gate替换拒绝，不自动补建。

## 启动与迁移边界

所有更新后的入口必须显式配置 `CARELINK_LEDGER_CONTROL_ROOT`，缺失则传感器请求拒绝，数据库初始化也拒绝。FROZEN时启动默认接收入口可能因初始化受控而失败，这是fail closed；不能据此改回无gate启动。新factory还要求显式registry与readings路径。原设备认证环境变量不作为gate之外的替代接收通道。

首次接管仍要求审批inventory、原始完整历史核验、全部旧写入者/自动拉起停用证据；源非空、格式和检查点必须匹配。**未更新的实际旧仓库、动态加载历史源码的启动器、外部原生SQLite程序不会因本分支代码变更自动遵守gate。** 这些必须在真实迁移前排除或更新，无法确认则禁止迁移。

运行时ledger、control-root和inventory须置于Git忽略的本机私有目录（如 `.secrets/`），不能提交运行状态或凭据。`.control`绑定是新增恢复文件，须连同完整ledger/marker、控制状态/事件/锁身份、现存SQLite侧文件现场、inventory与独立最新备份证据纳入恢复审查。不得手工复制绑定到第二根目录或删除后重新接管；不提供这种自动恢复方式。源丢失时仍拒绝用旧检查点猜测恢复。

## 验证说明

`scripts/test-atomic-freeze.py` 选择当前全部测试模块（含两项临时localhost TLS进程测试和夹具生命周期回归）。测试输出只有名称和状态；指定输出文件时另外保存分阶段聚合统计，不包含密码、签名、nonce或密钥。

并发ASGI批次固定仅该批次的fixture时钟，隔离并发性质与调试/任务中断引起的时间过期；生产60秒窗口和既有过期/未来请求测试保持，真实TLS测试仍正常运行。该控制没有传入生产代码或环境开关。

证据按签名验证、nonce尝试/提交、完整认证返回、受保护业务进入、HTTP状态、nonce增量和读数增量分别记录。基准夹具含一条已消费的专用bootstrap nonce，因此报告使用增量，而非把最终总数误当接收次数。nonce提交后崩溃的用例还单列子进程提交增量。

所有数据库、注册表、绑定和证书为临时合成文件。ASGI状态是实际FastAPI路由返回，但不等于真实硬件网络验收；两项独立TLS测试使用随机loopback端口及正确证书验证。真实网关负向测试、真实备份/回滚和生产切换均未验证。

## 2026-10-30 审计补充

- `LeasedConnection.execute/executemany/executescript` 返回受控游标；不能保留原生快捷游标绕过租约或关闭只读模式。每次执行仍检查同一有效租约。
- 迁移中的主文件头检查必须在独立短生命周期进程完成，不能在持有 SQLite 连接的进程内额外打开/关闭主文件。独立检查仍校验主文件头，不依赖 WAL 掩盖坏头，不修改输入；超时/失败拒绝操作。
- 临时 TLS 测试保留父进程绑定的随机 loopback socket 并传递给子进程，消除端口释放竞态；使用临时文件保存输出，防止 PIPE 堵塞。开启 tracemalloc=10 时实际完整应用启动约16秒，旧15秒截止会截断有效启动。当前固定60秒上限，提前检测子进程退出、报告阶段/退出码/最后探测原因，并验证每个子进程无 ResourceWarning；未降低证书或安全断言。
- nonce 提交后，业务事务失败仍消耗 nonce；不以清除历史换取重试。迁移仍不包含真实写入者、备份新鲜度或灾难恢复证明。

- SQLite 合法删除 idle WAL/SHM 时，若发生在 lstat 与 os.access 之间，必须保留真正的 FileNotFoundError，仅既有侧文件分支可接受这种缺席；现存不可访问侧文件、缺主库及缺 marker 仍拒绝。不得因此重试或放宽 nonce 认证。
- 测试子进程必须显式开启 ResourceWarning；父进程的 -W 不自动传递。继承 socket 的服务启动失败时也由上下文关闭 socket；任何捕获到的资源警告使测试失败，不作为“可忽略”输出。
