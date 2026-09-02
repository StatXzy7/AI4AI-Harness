# 项目最高纲领（仅由本人编写和修改，Agent 不得改动此文件）

## 使命
不计代价完成本次 ICLR 2027 投稿（deadline 前必须提交）。完成 > 完美。

## 硬性要求
1. 一切工作以"能否推进投稿"为唯一优先级，没有次要目标。
2. 禁止防御性编程：不写"以防万一"的抽象层、不预留用不到的扩展点、
   不做过度异常处理。代码能跑通实验即可。
3. 禁止防御性表述：论文里少用 hedge，直接陈述结论，保留必要的 limitation 一节即可。
4. 粗糙没关系：实验可以砍、写作可以糙、图表可以简陋，
   但必须按时间节点产出完整可提交的版本。
5. 遇到方向性犹豫，选择最快能出结果的那条路。
6. 实验结果如实报告——可以少做实验、可以砍范围，但已做的结果不许修饰。

## 节点
- **Abstract 截稿：2026 年 9 月 18 日**（AoE 时区）
- **全文截稿：2026 年 9 月 25 日**（AoE 时区）
<!-- ARIS:BEGIN -->
## ARIS Skill Scope
ARIS skills installed in this project: 83 entries.
Manifest: `.aris/installed-skills.txt`
ARIS repo root: `E:\Study\PhD\Research\AI4AI-Harness\Auto-claude-code-research-in-sleep`
Project skill path: `.claude/skills/<skill-name>`
For ARIS workflows, prefer the project-local skills under `.claude/skills/`.
Do not edit or delete junctioned skills in place; update upstream or rerun:
`powershell -NoProfile -ExecutionPolicy Bypass -File "E:\Study\PhD\Research\AI4AI-Harness\Auto-claude-code-research-in-sleep\tools\install_aris.ps1" "E:\Study\PhD\Research\AI4AI-Harness" -Platform claude -Reconcile`
<!-- ARIS:END -->

## 分工（用户 2026-09-01 指定，ZCode Agent 代为登记）

- **ZCode（本 Agent）= 执行者**：写代码、跑实验、改论文、干一切活。
- **Codex = 审核者**：所有 review / 审稿 / 找弱点 / 验收类工作，默认通过 Codex MCP（`mcp__codex__codex` / `mcp__codex__codex-reply`，配置见 `.mcp.json`）调用，即 ARIS `auto-review-loop` 的默认 `REVIEWER_BACKEND=codex` 路径。
- 不要让 Codex 替你写实现代码；不要让 ZCode 自审自己的关键产出。跨模型不变量：执行者与审核者必须是不同模型。
- Codex 不可用（MCP 未连接/超时）时，按 ARIS 约定 emit `REVIEW_UNAVAILABLE` 并如实报告，不得静默用自审代替。
