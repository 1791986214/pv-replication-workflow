# 如何更高效地实现 PV 复刻

保留原片时间线，用替换角色原画、源动作差分与程序合成复刻 PV。重点是让动作覆盖、人体一致、图层所有权和验收成为生产输入，减少“成片后用户逐秒指出遗漏”的返工。

- [工作流与效率策略](docs/如何更高效地实现PV复刻.md)
- [本次真实复盘与经验边界](docs/本次项目复盘.md)
- [恢复与清理边界](docs/恢复与清理.md)
- [可执行 Codex skill](skill/pv-replication/SKILL.md)
- [合同字段与可填写模板](skill/pv-replication/references/contract.md)

校验器只使用 Python 标准库。运行其行为验证：

```bash
python3 skill/pv-replication/scripts/test_validate_contract.py
python3 skill/pv-replication/scripts/test_verify_recovery.py
```

复制 `skill/pv-replication` 到你的技能目录即可使用。技能默认允许正常自动发现；也可明确要求“用 pv-replication 检查这支 PV 的动作拆分与合成合同”。源码发布不等于原作或角色素材开放，本包不包含原片、角色图、音轨、缓存或本地邮件信息。

方法与工程起点来自 [StuGRua/trick-heart-roxy-pv](https://github.com/StuGRua/trick-heart-roxy-pv)，特别感谢其中 `docs/production-guide.md`、规划模板、图层与持物修复实践；以及无糖淀粉的 [千早爱音版方法分享](https://www.bilibili.com/video/BV1giez6QEzc)。原曲/PV 为 [MIMI《トリックハート》](https://www.bilibili.com/video/BV1ohuu6LEBP)。本次新增文档与纯 Python 合同工具按 MIT 提供，保留来源 MIT 许可；音乐、PV、角色设计、衍生原画不在该授权范围。

本包基于一个项目的实际失败和修复经验；尚未通过下一支不同 PV 的生产验证，不声称适用于任意动画或保证一次零返工。
