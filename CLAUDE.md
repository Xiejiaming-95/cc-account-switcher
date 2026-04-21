# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在此仓库中工作时提供指引。

## 项目范围
- 这是一个仅面向 Windows 本地环境的 Claude 账号快照切换工具。
- 第一版只包含两个交付物：`claude_switch.py` 和 `claude_switch.bat`。
- 使用 Python 3.10+ 与标准库，不要引入第三方依赖。

## 实现约束
- 第一版保持最小实现，不要加入 GUI、exe 打包、token 刷新、凭据加密、云同步、多平台支持、进程管理或并发保护。
- 两个入口都要视为一等公民；修改工具时，要保持 `claude_switch.py` 与 `claude_switch.bat` 行为一致。
- 优先直接、朴素的实现，避免额外抽象。

## 交互与安全
- 所有用户可见的菜单、提示、状态文本、错误信息都必须使用中文。
- 危险操作必须在执行前进行明确的二次确认。
- 切换账号前，只有在用户明确确认所有 Claude 相关窗口已关闭后才能继续。

## 路径与账号识别
- 在 Windows 下，Claude 相关文件路径应按照 `2026-04-21-claude-switch-lite-design.md` 中定义的优先级顺序检查。
- 配置文件优先使用 `%USERPROFILE%/.claude/.config.json`，不存在时回退到 `%USERPROFILE%/.claude.json`。
- 凭据快照来源使用 `%USERPROFILE%/.claude/.credentials.json`。
- 当前账号识别优先读取 `oauthAccount.emailAddress`。

## 验证要求
- 在声称任务完成前，尽量覆盖三类验证：格式检查、自动化测试、菜单级手工走查。
- 如果仓库里还没有专门的测试或格式化工具，就使用诚实且最轻量的替代检查，并明确说明哪些内容尚未验证。

## 参考资料
- 产品与行为要求见 `@2026-04-21-claude-switch-lite-design.md`。
