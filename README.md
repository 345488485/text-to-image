# MOSS Studio / text-to-image

基于 Python FastAPI、Vue3、Vben 组件与 ComfyUI/MOSS-Image 的本地多人文生图平台。

## 功能
- 登录、首次强制改密、账号管理及用户私有图库。
- 单 GPU 串行任务队列、状态查询、参数复用、下载与删除。
- 8/16/20步，1:1、16:9、9:16画幅，明暗主题与响应式布局。
- Windows 启动与项目进程管理，任务重启协调。

## 源码目录
- `platform/backend`：FastAPI、鉴权、SQLite、任务队列、推理适配器。
- `platform/frontend/apps/moss`：Vue3/TypeScript业务页面。
- `platform/tests`：接口、队列及浏览器验收脚本。
- `platform/tools`：项目进程停止、运行库准备和交付工具。
- `docs`：从零开发、实现流程与面试讲解。

## 开始使用
先阅读 [平台运行说明](platform/README.md) 与 [从零开发与面试指南](docs/MOSS-Studio-从零开发与面试指南.md)。

本仓库只包含代码和必要源码资产，**不包含模型权重、ComfyUI本地副本、Python虚拟环境、node_modules、数据库、用户图片或日志**。
需要自行按对应版本准备模型、ComfyUI源码和依赖。仅克隆仓库不能直接完成模型部署。
运行说明中的 `F:\uv\text-to-image`、`D:\Anaconda3`、`E:\nodejs` 是开发机路径，其他机器需要调整。

环境准备完成后，Windows可运行根目录 `start.bat`。重复启动会停止经归属验证的本项目旧进程，因此会中断活动生成任务。
本地页面为 http://127.0.0.1:5173/ 。空数据库仅首次创建默认管理员，登录后必须改密，已有密码不会重置。

## 安全与边界
当前是本机单GPU应用，前端使用Vite开发服务，不是已加固的公网SaaS。不要直接把业务端口或ComfyUI无认证端口暴露到公网。
生成记录与图片存于本地 `platform/data`，不要提交该目录。模型许可和使用范围须另行核对发布方条款。

## 上游来源
前端保留Vben源码及其MIT许可，详见 [来源记录](platform/frontend/MOSS-UPSTREAM.md) 与 [上游许可证](platform/frontend/LICENSE)。
使用已有生成模型，不包含模型训练或自研量化算法。
