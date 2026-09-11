# 固定上游运行环境的实际恢复验收（Stage 29）

日期：2026-09-11。范围：回应可复现性建议 9.1/9.3 的本地恢复证据；不改变 A–D/W1 科学实验的未完成状态。

## 已核验

从本地 Git 对象导出固定上游 `69a614d04f2a7f3eacb64a63193078ab4be56ba5` 到独立目录。原 `external/TTHE` 未修改。冻结归档 ZIP 哈希为 `e8c11946a275330e59029ec5a1ce2999df0358d5184b4d807e17399e259f9cb7`，内部与外部 manifest 一致，392 个载荷成员逐字节通过 SHA-256（391 个源码及一个补丁）。解包前验证路径边界。

首次在主仓库子目录直接运行 `git apply` 时，check/apply 均返回 0，却未应用补丁。`restore_result.json` 保存这一失败状态。初次命令返回 0 的依据是本轮工具调用中的返回码断言通过；两个 stdout/stderr 文件为空，未单独保存返回码日志，因此该细节无法仅凭归档日志独立复核。恢复目录建立独立 Git 仓库后，verbose 日志确认五个文件均应用成功。`isolated_restore_result.json` 保存修正后的结果：五个运行文件与当前工作树在统一换行后内容一致；原始字节比较单独保留，不将换行差异伪装为字节一致。恢复后 444 个 Python 文件全部编译通过。

新建不继承 system site-packages 的 Python 3.13.9 虚拟环境，安装 `requirements-runtime.lock.txt`，安装退出码 0，29 个依赖的实际版本逐项一致。并非复制原运行环境。

在恢复目录导入 bridge、ase.db、solver_cache、llm，确认模块路径确实指向恢复树。使用内置 demo 数据库、mock provider、专用缓存及 Python socket 审计拦截进行离线检查；记录到的网络尝试为 0。BareHarness 的调用/轨迹、缓存 flush、无效 SQL 拒绝，以及显式 `SELECT COUNT(*) FROM singer` 返回 3 均检查通过。

## 失败与边界

第一次 smoke 的最小配置遗漏 base_url，触发 KeyError；补齐显式 loopback 地址后，第二次因误以为内置 mock 会输出有效 SQL 而断言失败。内置 mock 对 harness 请求实际返回 `OK`。最终检查保留这条无效 SQL 作为负向通路检查，并另用手写 SQL 检查数据库；没有替换 mock 输出或修改归档运行源码来制造有效生成结果。两次失败原因记录在 `offline_smoke.json`；最初两次完整 traceback 仅存在工具记录，未单独保存为日志。

这次验收只支持 Windows 上的源码恢复、依赖安装与离线基础通路。没有执行 391 个 harness 的完整运行测试、BIRD 基准、真实模型调用、跨平台测试或独立重复实验。不能据此宣称科学结论复现、缓存独立、成本已知或论文 ready。

## 可执行恢复要求

1. 从固定上游导出到新的专用目录，核验冻结 ZIP 与成员哈希。
2. 确保恢复目录具有独立 Git 边界（例如在此目录 git init），用 `git rev-parse --show-toplevel` 核实；随后 `git apply --check --verbose` 和 `git apply --verbose`。
3. 检查五个目标文件实际内容；仅检查退出码不足以证明恢复成功。
4. 在新的 Windows Python 3.13.9 venv 中安装锁定依赖。配置应显式包含 base_url，即使使用 mock。
5. mock 的返回内容不代表有效 SQL；将基础通路检查与真实模型实验分开报告。

证据目录：`artifacts/revision_20260910/runtime_restore_check/`。论文正文与双语 PDF 本轮未变。A–D 的真实采集仍等待本轮已请求的预算上限和账户计费依据；W1 的正式选择不确定性推断仍未完成。
