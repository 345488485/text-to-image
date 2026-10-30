# MOSS Studio

**面向本地 GPU 的多人文生图工作台。**

使用 Vue 3、FastAPI 与 ComfyUI，将 MOSS-Image 推理能力组织为可登录、可排队、可追踪、可管理的完整创作流程。

> 本仓库发布应用源码与必要资源，不包含模型权重、推理环境、用户数据或生成图片。项目定位为本机单 GPU 应用，不是开箱即用的云服务，也不包含模型训练。

[功能](#功能) · [架构](#架构) · [部署准备](#部署准备) · [运行](#运行) · [开发与测试](#开发与测试) · [安全与限制](#安全与限制)

## 功能

- **创作工作台**：正向/反向提示词、随机种子、8/16/20 步采样与图片预览。
- **多画幅**：1:1（512×512）、16:9（768×432）、9:16（432×768）。
- **私有图库**：生成记录分页、状态筛选、详情、参数复用、PNG 下载和删除确认。
- **账号管理**：登录会话、首次强制改密、管理员创建/禁用账号及重置密码。
- **共享 GPU 队列**：单任务串行执行、每用户一个活动任务、排队位置与状态查询。
- **异常处理**：持久化任务与引擎 ID、重启协调、网络超时处理和自有推理进程管理。
- **界面适配**：响应式布局、等待动画、自动昼夜主题与手动主题切换。

## 架构

```text
Vue 3 / TypeScript / Vben / Naive UI
                  │ /api
                  ▼
           FastAPI 业务服务
      鉴权 · 参数校验 · 用户隔离
                  │
                  ▼
        SQLite 持久化任务队列
                  │
                  ▼
           单 worker 串行消费
                  │ 本机 HTTP
                  ▼
       ComfyUI + MOSS-Image → PNG
                  │
                  ▼
       校验与私有存储 → 鉴权访问
```

业务请求与 GPU 执行解耦：提交接口负责入队，worker 认领并执行任务，页面查询状态。任务的 `queued / running / succeeded / failed / cancelled` 状态保存在数据库中。

| 层级 | 技术 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vben 核心布局、Naive UI、Vite |
| 后端 | Python、FastAPI、Pydantic |
| 存储 | SQLite（WAL）、本地私有文件目录 |
| 推理 | ComfyUI、MOSS-Image 固定工作流、PyTorch / CUDA |
| 本地运行 | Windows PowerShell、独立 Python 环境、Node.js |

## 目录结构

```text
text-to-image/
├── platform/
│   ├── backend/            # 业务 API、鉴权、数据库、worker、推理适配
│   ├── frontend/
│   │   ├── apps/moss/      # 应用页面与前端测试
│   │   └── packages/      # Vben 上游基础组件与工具
│   ├── tests/             # 接口、引擎与浏览器验收脚本
│   ├── tools/             # 进程管理、兼容运行库与交付工具
│   ├── requirements-lock.txt
│   └── serve.py           # 后端入口
├── start.bat              # Windows 启动入口
├── start-platform.ps1     # 前后端启动与重启
├── run_moss_compatible.py # 推理兼容入口
├── extra_model_paths.yaml
└── workflow-api*.json     # 固定 API 工作流
```

模型、缓存、运行日志、虚拟环境及用户数据通过 `.gitignore` 排除。本地教程和笔记保留在开发机器，不随仓库发布；仓库只保留本页 Markdown 说明。

## 部署准备

### 1. 环境要求

- Windows，Python 3.12。
- 支持 CUDA 的 NVIDIA GPU，以及与所选 PyTorch 构建匹配的驱动。
- Node.js：遵循前端上游记录的 `^22.18.0 || ^24.12.0`；包管理器记录为 `pnpm@11.16.0`。
- 足够的磁盘、可用内存和系统提交内存。开发机使用 RTX 4060 Laptop 8GB 显存、约 48GB 内存，这不是对所有配置的最低要求或运行保证。

模型文件大小不等于推理时的内存峰值；Windows 分页文件不足也可能导致加载失败。

### 2. 获取源码

```powershell
git clone https://github.com/345488485/text-to-image.git
Set-Location text-to-image
```

后续命令均在项目根目录执行。部分脚本保留了开发机路径，例如 `D:\Anaconda3`、`E:\nodejs`；换机器时需要检查并调整，不能直接假设这些位置存在。

### 3. 准备推理环境与模型

推理与业务 Python 环境应隔离：根目录 `.venv` 用于推理，`platform/.venv` 用于业务服务。

请按照对应模型发布方的说明准备匹配版本的 ComfyUI、PyTorch 与量化依赖，并核对许可证、格式和校验值。ComfyUI 源码应放在兼容入口所引用的 `.runtime/source/ComfyUI-master`。本仓库不提供一条命令完成模型部署的承诺。

当前工作流使用以下权重：

| 目录 | 文件 |
| --- | --- |
| `models/text_encoders/` | `qwen3.5_9b_w4a8_gptq.safetensors` |
| `models/diffusion_models/` | `moss_image_sft_int8_convrot.safetensors` |
| `models/vae/` | `flux2-vae_small.safetensors` |

修改 `extra_model_paths.yaml` 中的 `base_path`，使其指向本机实际模型目录。不要将权重提交到 Git。

**先确认模型端能用固定工作流生成一张可读取的 PNG，再继续业务联调。端口可连接不代表模型已成功加载。**

### 4. 安装业务与前端依赖

以下命令使用本机已安装、可执行的 `python`。仅在目标虚拟环境尚未创建时执行第一条：

```powershell
python -m venv --without-pip .\platform\.venv
python -m pip --python .\platform\.venv\Scripts\python.exe install -r .\platform\requirements-lock.txt
pnpm.cmd --dir .\platform\frontend install --frozen-lockfile
```

如果基础 Python 没有 pip，应先准备可用的 pip；不要将业务依赖直接安装到全局推理环境。

## 运行

完成环境和权重准备后，双击根目录 `start.bat`，或运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-platform.ps1
```

| 地址 | 用途 |
| --- | --- |
| `http://127.0.0.1:5173/` | 前端工作台 |
| `http://127.0.0.1:8000/` | 业务后端 |
| `http://127.0.0.1:8188/` | 本地推理引擎 |

- 空数据库首次启动会创建 `admin / 123456`，登录后必须修改密码；已有账号密码不会被启动操作覆盖。
- 不要并行启动多个后端 worker。单 GPU 串行方案不支持通过多开服务提升生成并发。
- 重启会中断活动任务。外部已存在的推理服务只连接，不应被无条件终止。
- 本次发布的仓库版本使用 Vite 开发服务提供前端；启动后仍需等待前端与引擎分别就绪。

### 配置与运行数据

环境变量示例见 `platform/.env.example`。可配置数据目录、允许来源和 Cookie 安全选项；不要把真实凭据写入示例文件或提交到仓库。

| 本地位置 | 内容 |
| --- | --- |
| `platform/data/moss.sqlite3` | 用户、会话及生成任务 |
| `platform/data/images/` | 平台私有图片副本 |
| `platform/data/engine.log` | 引擎运行记录 |
| `platform/logs/` | 前后端启动与验收日志 |

这些位置需要由运行环境创建。数据库与图片属于私有数据，不应直接暴露为 Web 静态目录。备份时使用停机备份或一致性备份方式，注意 SQLite WAL 文件。

## 开发与测试

前端开发：

```powershell
pnpm.cmd --dir .\platform\frontend --filter @moss/studio dev
```

前端校验与构建：

```powershell
pnpm.cmd --dir .\platform\frontend --filter @moss/studio test
pnpm.cmd --dir .\platform\frontend --filter @moss/studio typecheck
pnpm.cmd --dir .\platform\frontend --filter @moss/studio build
```

后端隔离测试：

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
& .\platform\.venv\Scripts\python.exe -m pytest .\platform\tests -q --basetemp ".\platform\.test-runs\manual-$stamp"
```

测试目录应使用新的名称，避免覆盖旧记录。部分浏览器验收脚本使用开发机上的 Playwright 路径，其他机器需要调整。

测试应区分三个层次：接口与队列逻辑、模拟 API 的浏览器交互、真实 GPU 出图。前两者通过，不等于模型部署成功。不要使用真实用户图片或重置用户密码进行破坏性测试。

## 安全与限制

- 密码采用带随机盐的 scrypt 哈希；会话令牌以哈希形式保存。
- 写操作校验 CSRF；列表、详情、图片和删除均检查资源所属用户。
- 管理员管理账号，不自动获得读取其他用户私有图片的权限。
- 当前固定工作流只开放受支持参数，不支持任意节点图上传。
- 默认本机绑定，不包含公网 HTTPS、反向代理加固、支付、配额和分布式调度。
- 当前不支持模型训练、图生图或多 GPU 并发。生成速度取决于加载、采样、内存和硬件状态，不能仅按步数推断。

**请勿直接向公网暴露业务端口或未经鉴权的 ComfyUI 服务。**

## 致谢与许可

- 前端基于 [Vben Admin](https://github.com/vbenjs/vue-vben-admin) 的实际核心组件，保留的上游源码基线为 `8c87902658b8b8aa8703cf371323bca1273d3a7c`。
- Vben 上游许可证保留在 [`platform/frontend/LICENSE`](platform/frontend/LICENSE)；删除文档不删除该许可证及源码中的版权声明。
- 推理依赖 ComfyUI 与已有 MOSS-Image 权重。相关模型、运行库及上游项目的许可需分别遵守；本项目不包含模型训练成果，也不将上游组件声明为原创。

## 问题反馈

提交 Issue 时建议提供操作系统、Python/Node 版本、显卡与显存、复现步骤、任务状态及脱敏错误信息。请勿上传密码、会话 Cookie、令牌、完整用户数据库或私有作品。
