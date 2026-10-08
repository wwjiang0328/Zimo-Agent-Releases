# Zimo Agent Releases

Zimo Local（织梦本地版）和 Zimo Cloud（织梦云端版）的官方公开安装包仓库。

官网与下载入口：<https://www.zimofy.com/download>。

| 产品 | 标签 | 安装包 |
|---|---|---|
| Zimo Local | `local-vX.Y.Z` | `Zimo-Local-win-X.Y.Z.exe` / `Zimo-Local-mac-X.Y.Z.dmg` |
| Zimo Cloud | `cloud-vX.Y.Z` | `Zimo-Cloud-win-X.Y.Z.exe` / `Zimo-Cloud-mac-X.Y.Z.dmg` |

Windows 为 x86_64，macOS 为 Apple Silicon。两个产品独立更新；请通过官网选择对应产品，不使用全仓库 latest 判断版本。

历史标签及安装包保留，原仓库链接由 GitHub 重定向。本仓库不包含应用源码和生产凭据，不因公开安装包而改变产品许可。

## 构建约定

源码分别位于私有仓库 `Zimo-Agent-Local` 与 `Zimo-Agent-Cloud`。先在对应源码提交上创建产品标签，再在本仓库 main 上创建同名标签。构建凭据 `GH_PAT` 必须能读取对应私有源码仓库。

Local 的签名、COS 上传与线上发布由私有发布控制器完成。Cloud 的线上发布配置需要单独验收，不得套用 Local 的数据库发布作用域。产品名称变化不代表 Cloud 的功能、安装器及数据隔离已经完成发布验收。

2026-10-08 恢复 Local / Cloud 2.1.0 构建发布。历史取消的 v2.0.6 标签保留，新命名的标签不得复用旧构建产物。

`Installer acceptance` 工作流仅在 GitHub 临时 Windows/macOS runner 中运行，验证正式安装包摘要、Local 2.0.5 升级、两个产品共存、卸载隔离及数据保留；不得在用户电脑运行该测试脚本。两款安装包就绪后，以同一版本手动触发此验证，通过后再将对应版本推广到官网和在线更新。

Application source is private. This repository distributes official installers and release workflows only.
