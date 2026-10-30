# 知助：dev 分支审核说明

仓库：[xiao-e-xiao-e/zhizhu-support](https://github.com/xiao-e-xiao-e/zhizhu-support)。审核分支：`dev`，目标主分支：`master`。

仓库由 `rag-knowledge-base` 改名为 `zhizhu-support`，网站、API、包名与主说明同步使用“知助 · 智能客服与知识协作平台”。本机工作目录与 Compose 数据卷没有改名，以保留现有运行数据。

## 提交范围

远端原有 `master` 提交 `9aa1bc6e6c2850a8bcdeed22a5f51629659fa7ea` 作为开发分支起点。保留原主分支历史，把本地已有的前后端改造和后续业务功能整理为连续提交，逐批推送，不使用强制推送。

| 批次 | 提交 | 内容 |
| --- | --- | --- |
| 1 | [bcbd451](https://github.com/xiao-e-xiao-e/zhizhu-support/commit/bcbd4512571cefb0fd4237f8b9fdc483c0fa5cc5) | refactor: 重构为前后端分离架构并修复五个缺陷 |
| 2 | [44e7f40](https://github.com/xiao-e-xiao-e/zhizhu-support/commit/44e7f4083c7bf3df0f956d1490c51667532efce7) | fix(frontend): 显式绑定 IPv4 并禁止端口漂移 |
| 3 | [c01636b](https://github.com/xiao-e-xiao-e/zhizhu-support/commit/c01636b9cf4ae41b147fc848e30d2d708d122f07) | fix(backend): 修复中文会话名导出返回 500 |
| 4 | [45c3be0](https://github.com/xiao-e-xiao-e/zhizhu-support/commit/45c3be0535e38a200cb29b93fa7572f88c1c67e2) | feat(core): 建立账号权限、产品授权与工单协作数据基础 |
| 5 | [05be238](https://github.com/xiao-e-xiao-e/zhizhu-support/commit/05be2388924e3455b8df7ee0e37865361dc736ce) | feat(knowledge): 实现后台入库、文档修订与检索问答 |
| 6 | [54ebc7a](https://github.com/xiao-e-xiao-e/zhizhu-support/commit/54ebc7ab3db6ee99c9e80ca6222fbb54b9fe15d6) | feat(assistant): 加入工具工作流、确认建单与真实正文流式输出 |
| 7 | [4db2834](https://github.com/xiao-e-xiao-e/zhizhu-support/commit/4db2834fac9bf39472961639198a5b9e7762434c) | feat(frontend): 接入业务权限、资料与工单运营页面 |
| 8 | [66f70b0](https://github.com/xiao-e-xiao-e/zhizhu-support/commit/66f70b0907892dfd2802aab198dbbee069381bb6) | feat(chat): 统一智能助手入口并重构会话与引用界面 |
| 9 | [407dad6](https://github.com/xiao-e-xiao-e/zhizhu-support/commit/407dad6f4540a37f654050d5b693189f4c75d216) | test: 补齐业务隔离、流式输出回归与模型质量评估 |
| 10 | [0b13522](https://github.com/xiao-e-xiao-e/zhizhu-support/commit/0b1352207a9cb2d7ffd1e6eeada778d012f5b347) | chore(deploy): 添加容器、后台 worker 与部署初始化配置 |
| 11 | [283af83](https://github.com/xiao-e-xiao-e/zhizhu-support/commit/283af838bf965edfdf395d1ea1191592527b0307) | fix(deps): 修复四项高危依赖公告并更新前端包标识 |
| 12 | [baa3198](https://github.com/xiao-e-xiao-e/zhizhu-support/commit/baa3198dd96219f1af0cd9eb92d42b0358e0782e) | 品牌命名、部署模板、项目文档与 CI |
| 13 | 本说明所在提交 | 空测试数据库配置回退与 CI 矩阵独立运行 |

这些批次描述一个完整版本的组成层次；安装与部署请使用 `dev` 的完整最新版本。

## 建议审核顺序

1. 阅读 [README](../README.md) 与 [开发和部署说明](DEPLOYMENT.md)，核对项目定位和启动方式。
2. 在网站使用自己的业务账号登录，检查“知助”名称、资料范围、最近对话与手机导航。
3. 向助手询问“你是谁”“你的大模型是什么”“你好”，检查公开身份信息和普通交流。
4. 选择产品版本，询问产品知识，检查流式正文和引用片段；停止回复后检查已收到内容和历史记录。
5. 让助手整理工单，编辑后确认提交，核对工单状态与对话副本；客服检查处理流程与 FAQ 审核发布。
6. 查看 PR 的 CI、改动文件及 [执行记录](EXECUTION_LOG.md)。测试使用专用数据库，不连接业务数据库。

## 合并约定

本次只在 `dev` 开发并创建草稿 PR。没有启用自动合并，也不修改默认分支指向。主分支合并需要用户在当前协作中明确确认后再执行。

运行凭据、账号密码、数据库、上传原件、备份、私有验证产物及个人简历草稿均不属于提交内容。
