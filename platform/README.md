# MOSS Studio 本地多人文生图平台

本平台运行在 `F:\uv\text-to-image` 的现有 MOSS-Image / ComfyUI 之上。
Python FastAPI + SQLite 后端，Vue3 + Vben 组件 + Naive UI 前端。
只绑定本机，不自动公开到局域网/公网；不修改驱动、分页文件或现有推理环境。

## 首次使用

在 PowerShell 中运行：

```powershell
Set-Location F:\uv\text-to-image
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-platform.ps1
```

首次启动会在**空数据库**自动创建 `admin / 123456`，不再需要终端初始化。
访问 http://127.0.0.1:5173 登录，必须先设置至少10位的新密码，才能进入创作、图库和管理功能。
修改密码会立即撤销旧会话并轮换当前会话；初始密码失效。已存在账号和密码不会被自动覆盖。
默认密码仅供本机首次初始化，请勿在改密前开放到网络。

双击根目录 start.bat 会先停止经路径核实属于本项目的旧前后端进程树，然后重新启动；正在生成的任务会被中断。其他程序占用8000/5173时会拒绝停止。直接运行 start-platform.ps1 不带 -Restart 时仍拒绝重复启动。手动开发可分别运行：

```powershell
.\platform\.venv\Scripts\python.exe .\platform\serve.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\platform\start-frontend.ps1
```

后端会在8188离线时启动自己的兼容推理子进程；已有外部ComfyUI则只连接，不擅自结束它。
关闭后台实例请使用任务管理器/所记录精确PID，或在前台运行后按Ctrl+C正常退出。
不要使用uvicorn多worker或reload；数据库单worker文件锁会拒绝并发实例。

## 能力与限制

- 支持正反提示词、8/16/20步、种子，画幅可选电脑16:9（768×432）、手机9:16（432×768）和1:1（512×512），每任务1张；单GPU串行，每用户最多1个活动任务。
- 用户私有图库、详情、复制参数、下载、删除；管理员创建/禁用/重置密码（改密和禁用撤销会话）。
- 白天07:00–19:00亮色、其他时间暗色，按浏览器当地时间；亮色/暗色/自动手动切换，浏览器保存。
- 同一浏览器同一站点的不同标签页共享登录会话；不同用户请用独立浏览器/隐私窗口。
- 当前硬件曾出现Windows分页文件不足。平台自有推理进程在任务之间主动冷启动以释放CPU模型；内存失败最多重启重试1次，不重启外部服务。
- 连接外部推理服务时，/free无完成确认接口，暂保守等待15秒；平台自有冷启动进程跳过此等待。不会承诺固定出图时间。
- 任务失败会保存错误状态；后台重启协调已提交任务，不盲目重新提交。无法确认GPU停止时暂停worker，管理员需查日志并重启。
- 默认关闭公开注册。无支付、公开社区、图生图、云部署或公网HTTPS加固。

## 数据与安全

数据库及私有图片在 `platform/data`，不是Web静态目录。不要提交到Git或分享该目录。
生产密码采用scrypt哈希，会话仅在HttpOnly/SameSite cookie中，DB只存令牌哈希；写操作校验CSRF。
ComfyUI仅后端连接，不能作为无认证公共端口暴露。管理员也不能借图片接口读取他人作品。
QA测试数据使用 `platform/.acceptance-data`，测试账号只存在这个隔离数据库，不是生产默认账号。
关闭平台后备份整个 `platform/data`；删除记录只删除该用户平台私有图片副本，不删除原有模型/历史测试输出。

## 重新安装/测试

现有独立环境已与推理Python隔离。重建可用项目Python创建独立venv，再用pip的`--python`安装锁定依赖：

```powershell
D:\Anaconda3\python.exe -m venv --without-pip .\platform\.venv
D:\Anaconda3\python.exe -m pip --python .\platform\.venv\Scripts\python.exe install -r .\platform\requirements-lock.txt
pnpm.cmd --dir .\platform\frontend install --frozen-lockfile
.\platform\.venv\Scripts\python.exe -m pytest .\platform\tests -q --basetemp .\platform\.test-runs\unique-run
pnpm.cmd --dir .\platform\frontend --filter @moss/studio test
pnpm.cmd --dir .\platform\frontend --filter @moss/studio typecheck
pnpm.cmd --dir .\platform\frontend --filter @moss/studio build
```

pytest basetemp须使用全新的目录名，避免覆盖旧证据；Windows受限沙箱可能需普通用户终端执行。
Python依赖锁定见requirements-lock.txt；前端上游来源和许可见frontend里的来源记录及LICENSE。
运行中的日志在platform/logs；完整验证和回滚证据沿用根目录`.runtime/transfer-fix/VERIFICATION.txt`。
## 本地交付验收

- 后端完整测试、前端测试/类型检查/构建及浏览器验证记录：platform/logs。
- 最新连续两账号真实生成：94.764秒、98.295秒（包含任务活动期间的启动/加载开销），无并发重叠。
- 用户隔离、CSRF、会话撤销、单worker锁、队列恢复和原子取消均有测试。
- 站点已运行时，直接打开5173，用admin/123456首次登录后改密；不要重复运行启动脚本。
- 明暗主题边界/手动持久化已通过测试；浏览器截图含亮色、暗色、图库、管理员页和移动登录页。
- 保留已知限制：前端单JS块约716KB，构建有体积警告；当前为本地开发服务，不是经过公网加固的生产部署。

## 等待动画与画幅
桌面新建默认16:9，手机默认9:16，也可手动选择；已有作品按真实尺寸显示，不裁切。排队用浮点等待动画，生成中用绘图/扫描动画；不伪造百分比。遵从系统“减少动态效果”设置。旧512×512作品保留，不修改已有账号密码或生成记录。

## 紧凑工作台
桌面工作台随窗口高度缩放，预览和生成按钮同屏；高级参数默认折叠，展开后参数区可独立滚动。手机图片预览限高，保持正常上下布局。图片仅缩放显示，不裁切或修改输出分辨率。

启动入口直接使用已安装的 Node 和本地 Vite，不再依赖 pnpm 位于桌面会话 PATH；pnpm 仍用于安装依赖和开发构建。Node 优先使用 PATH，缺失时探测本机 E:\nodejs 及 Program Files\nodejs，不修改系统 PATH。

## 推理恢复兼容修复
启动及进程退出确认绕过卡住的 WMI/taskkill，使用已核实路径及原生进程句柄；Python 平台信息使用标准库回退。项目内 .runtime/inference-python 隔离 VC 运行库，不替换系统或 Anaconda DLL。如需重建，在平台 Python 下运行 platform/tools/prepare_inference_runtime.py。生成状态轮询的短暂网络超时不会重新提交任务；真正退出仍报告失败。
