# Figma MCP 检查记录 · 2026-10-22

目标文件： https://www.figma.com/design/bOI1cB8GMKvUde0avJFkjJ

## 实际调用与结果

1. 已发现连接器工具：`whoami`、`use_figma`、`get_metadata`、`get_screenshot`、`get_variable_defs`、`get_design_context`、`get_libraries`、`search_design_system`，以及文件创建/设计写入等工具。本次只调用前三步列出的能力。
2. `whoami` 成功。当前返回 Starter plan、View seat、团队 admin。身份请求成功说明连接与认证在该请求时有效，不代表文件写入权限、可用额度或恢复日期。
3. 一次只读 `use_figma` 成功：读取 Page 1、5 个 Web/LCD 画板、其字体/颜色/布局样本及颜色变量集合。没有修改节点。
4. 一次最小写入探测：计划创建 1×1 隐藏临时矩形，在空白区域验证后立即删除，不触碰现有 Frame。请求被 MCP 限额拒绝，没有成功执行写入。收到 `isError: true`，`error_code: INVALID_ARGUMENT`；具体正文明确指出 Starter tool-call limit。

错误原文：

> You've reached the Figma MCP tool call limit on the Starter plan. Upgrade your plan for more tool calls: https://www.figma.com/files/team/1562034973811555937/all-projects?upgrade=mcp_rate_limit_paywall Use the whoami tool for more plan details. Learn more: https://developers.figma.com/docs/figma-mcp-server/rate-limits-access/

## 结论与未确认项

- 读取：本次确实成功一次，不能保证后续所有读取都可用。
- 写入：本次被调用额度限制阻塞；没有可靠证据确认文件写入权限本身。没有收到认证失败或权限不足的响应，不能把这些原因与本次限额错误混为一谈。
- 月度上限、已用次数、剩余次数和准确恢复时间：工具未给出，均未知。
- 本轮未重复尝试写入、未升级套餐、未修改账户/权限，Figma 设计保持原样。当前没有新增的手机设计内容或新原型。
- 修复路径：待该账户的 MCP 可用额度恢复或由账户持有人自行处理套餐/席位后，重新做低成本读取和单次最小写入检查。此记录不保证升级或改席位必然解决全部权限问题。

## 成功读取到的现有风格

- 背景 `#f6f8f7`、白色表面、主文字 `#233e38`、次文字 `#788b85`。
- 品牌色 `#197b6e`，薄荷色 `#e8f3ee`。使用 CareLink / UI colors 变量集合（Light）。
- 字体 Noto Sans SC，Regular / Medium；常见卡片圆角 12，Logo 圆角 10，间距以 12/18/22/24 等分组。
- 原有 01–05 为 Web 登录、Pro 总览、Pro 详情、Basic、LCD 1602A；06–10 为上次留下的 iPhone 空 Frame。

本地原生工程保留品牌浅色资产，采用 iOS 系统字体/动态字号、NavigationStack、TabView、List 和 SF Symbols。深色资产是本地设计提案，不声称已在 Figma 中存在。后续回填会在同一原文件完成，保留 Web/LCD。
