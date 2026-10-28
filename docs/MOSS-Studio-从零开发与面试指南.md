# 一步一步实现 MOSS Studio：从一次请求到完整项目

## 先说明这份教程怎么读

本文只围绕一条主线：**用户点击生成 → 后端创建任务 → worker 调用模型 → 图片保存 → 用户查看自己的作品。**

你每读完一步，都应能回答：现在增加了什么能力？为什么需要它？代码放哪里？怎样证明它生效？后面的代码依赖前面建立的对象，不是互不相关的知识点。

这是依据当前源码重新组织的教学顺序，不是编造的历史开发日记。代码分为两种：标注“源码”的片段从当前文件提取；标注“教学示例”的片段用于解释接口或流程。片段不是完整文件，复现时应结合对应完整源码，不能把所有片段拼进一个文件。

本文不教训练模型，也不把安装报错当作项目核心难点。目标是让你能自己实现应用层，并讲清楚自己的设计。

---

# 第一部分：先确定我们究竟要做什么

## 第 1 步：把需求改写成一条可验收的用户流程

### 1.1 第一版只做这件事

用户登录，输入“木桌上的红色茶壶”，选择 8 步与 512×512，点击生成。页面显示排队、生成中，最后显示图片。刷新后记录仍存在。

接下来才增加第二位用户：两人共享 GPU，但看不到对方的记录；每位用户一次只能有一个活动任务。

**先不做**公开社区、支付、模型训练、任意工作流上传、多 GPU 调度。这样每个设计都能对应到真实需求，而不是为了简历堆组件。

### 1.2 把流程拆成职责

```text
浏览器负责交互，不直接控制模型
  ↓ 提交参数、查询状态
FastAPI 负责鉴权和业务规则
  ↓ 保存任务
SQLite 负责用户、会话、任务的持久化
  ↓ worker 认领 queued
推理适配器负责把业务参数转换成固定工作流
  ↓ HTTP
ComfyUI / MOSS-Image 负责实际生成
  ↓ 校验 PNG 并保存平台副本
FastAPI 鉴权返回图片 → 浏览器展示
```

为什么需要这些层？因为“生成一张图”和“让多个人可靠地使用生成能力”不是同一件事。模型解决前者，队列、权限、持久化和界面解决后者。

### 本步交付和验收

交付一页需求说明。验收标准不是“页面漂亮”，而是能写出两个场景：A 刷新后能看到旧作品；B 不能通过修改任务 ID 看 A 的作品。

---

# 第二部分：按依赖顺序把代码做出来

## 第 2 步：先封装“给参数，返回一张图片”的能力

**为什么先做：**后面所有功能都依赖模型能完成一次真实生成。否则写完网页，才发现模型或工作流不兼容，会很难定位。

### 2.1 先准备最小环境

本项目根目录是 `F:\uv\text-to-image`。推理环境与 Web 后端环境分开，避免安装 FastAPI 时影响 Torch，或者调整模型依赖时破坏业务服务。

- 推理 Python：`F:\uv\text-to-image\.venv`。
- 业务 Python：`F:\uv\text-to-image\platform\.venv`。
- 前端：`F:\uv\text-to-image\platform\frontend`。

从空机器复现，需要先取得项目与匹配的 ComfyUI 源码、工作流、模型权重及依赖锁文件。本文不把一条 pip 命令说成完整模型安装方案；权重许可、来源和校验值应按取得的发布版本核对。

当前使用文本编码器 qwen3.5_9b_w4a8_gptq、生成模型 moss_image_sft_int8_convrot、VAE flux2-vae_small，文件位于根目录 models 下。当前工作流是 `F:\uv\text-to-image\workflow-api-8steps.json`。

拿到源码后，业务环境的创建示例：

```powershell
Set-Location F:\uv\text-to-image
# 仅在 platform/.venv 尚不存在时创建；其他机器替换基础 Python 路径
& 'D:\Anaconda3\python.exe' -m venv --without-pip .\platform\.venv
& 'D:\Anaconda3\python.exe' -m pip --python .\platform\.venv\Scripts\python.exe install -r .\platform\requirements-lock.txt
# 先准备源码要求的 Node/pnpm，再安装前端锁定依赖
pnpm.cmd --dir .\platform\frontend install --frozen-lockfile
```

### 2.2 定义适配器的输入输出

不让后端路由到处操作工作流节点。先约定一个边界：

```python
# 教学示例：契约，不是另一个可直接运行的实现
job = {
    'id': 'job_001', 'prompt': '木桌上的红色茶壶',
    'negative_prompt': '', 'steps': 8, 'seed': 42,
    'width': 512, 'height': 512,
}
# engine.generate(job, persist_prompt_id, stop_event) 成功时返回：
result = {
    'image_path': 'images/job_001.png',
    'image_sha256': '实际文件的SHA256',
    'elapsed_seconds': 90.468,
}
```

将读取模板、修改参数、提交、轮询、校验结果都放进 `ComfyEngine`，业务层只认识上述契约。

### 2.3 业务参数怎样变成模型参数

源码位置：`F:\uv\text-to-image\platform\backend\engine.py`。下面是核心映射的教学摘录：

```python
# graph 已从固定工作流 JSON 读取，job 已经过类型和范围校验
# 节点数字仅适用于当前模板，不是 ComfyUI 的统一约定
graph['4']['inputs']['text'] = job['prompt']
graph['5']['inputs']['text'] = job.get('negative_prompt', '')
graph['8']['inputs'].update(seed=job['seed'], steps=job['steps'])
graph['6']['inputs'].update(width=job['width'], height=job['height'], batch_size=1)
graph['10']['inputs']['filename_prefix'] = 'platform_' + job['id']
```

实际 `workflow()` 还有 ID、步数、种子和文本校验，宽高来自允许的画幅映射。不能接受浏览器传来的任意节点图、文件路径或批量数。

### 本步交付和验收

交付 `engine.py` 的适配边界。先用 512×512、8 步做一次真实调用：确认 history 为成功，PNG 能被 Pillow 打开，尺寸正确。仅 `/system_stats` 返回 200 不算出图成功。

---

## 第 3 步：设计任务表，让“生成”有状态和记忆

**上一阶段的问题：**只有一次函数调用。程序退出后不知道生成过什么，也不知道失败在哪一步。

**这一阶段增加：**数据库和状态机。先设计状态，再设计表，不要随意添加几个布尔字段。

```text
queued → running → succeeded
   │          └→ failed
   └→ cancelled
```

任务还在排队时可以取消；当前网页不提供任意阶段取消运行中的任务。无法确认推理是否停止时，保留协调信息、暂停调度，而不是假装任务已安全结束。

### 3.1 为什么至少需要三张表

| 表 | 解决的问题 | 核心字段 |
| --- | --- | --- |
| users | 谁在使用平台 | id、username、password_hash、role、is_active、must_change_password |
| sessions | 本次请求凭什么被信任 | token_hash、user_id、csrf_token、expires_at |
| jobs | 生成到哪一步、结果属于谁 | id、owner_id、status、prompt_id、参数、时间、图片路径、错误 |

`job.id` 是平台任务 ID；`prompt_id` 是引擎任务 ID。后面恢复任务时需要第二个 ID，所以一开始就要留这个字段。

实际建表与增量字段维护：`F:\uv\text-to-image\platform\backend\db.py`。画幅保存为 width/height，响应中再推导 aspect_ratio。

### 3.2 封装数据库事务

连接启用外键，设置等待锁超时，数据库启用 WAL。涉及“先检查再修改”的业务使用事务；不是把所有 SQL 都包装成一个长事务。

当前 transaction() 源码：

```python
@contextmanager
def transaction(self):
    with self.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        yield c
```

它通过 `BEGIN IMMEDIATE` 提前获得写事务，防止两个认领者都以为自己拿到了空闲位置。`Database.connect()` 配置 Row、外键和 busy_timeout，连接由上下文管理器提交/回滚并关闭。

### 本步交付和验收

创建一个 queued 记录，关闭程序后再查，记录仍在；事务中故意抛错，修改应回滚。这里还不用接浏览器。

---

## 第 4 步：建立身份，再谈“我的任务”

**为什么现在做：**如果先实现图库再补用户归属，很容易出现接口漏鉴权。owner_id 必须从服务端登录态取得。

### 4.1 登录链路

```text
提交账号密码 → 校验 scrypt 哈希 → 生成随机会话令牌
→ 数据库存令牌哈希和过期时间 → 原始令牌写入 HttpOnly Cookie
→ 后续请求通过 Cookie 找到有效用户
```

实现位于 `F:\uv\text-to-image\platform\backend\security.py`、`F:\uv\text-to-image\platform\backend\app.py`。密码不能明文存；随机盐不是固定常量。

### 4.2 做三个依赖函数

- `current()`：验证会话、过期时间、账号启用状态、首次改密限制。
- `write_user()`：在 current 基础上校验写请求的 `X-CSRF-Token`。
- `admin()` / `write_admin()`：在以上基础上检查管理员角色。

让路由依赖这些函数，而不是每个接口重新手写一套判断。

### 4.3 用一个归属函数堵住越权入口

当前 owned() 源码：

```python
def owned(jid, user):
    job = db.one('SELECT * FROM jobs WHERE id=? AND owner_id=?', (jid, user['id']))
    if not job:
        raise HTTPException(404, '记录不存在')
    return job
```

以后详情、下载、删除都先调用它。拒绝越权返回 404，既不返回作品，也不确认这条记录是否属于其他人。管理员可以管理账号，但没有默认跨用户看图权限。

### 本步交付和验收

A 登录创建记录后，B 用 A 的任务 ID 请求详情/图片/删除都不能成功。首次 admin/123456 仅用于空库初始化，必须改密；已经设置的密码不能被启动脚本覆盖。

---

## 第 5 步：实现提交接口，但先不要在请求里跑模型

**关键决定：**POST /api/jobs 只负责校验与入队。模型需要几十秒甚至更久，不能把整段生成绑在一个浏览器请求上。

实现位置：`F:\uv\text-to-image\platform\backend\app.py`。

先用 `JobInput` 限制提示词长度、8/16/20 步、种子范围与允许画幅，拒绝未知字段。再写以下路由，源码如下：

```python
@app.post('/api/jobs', status_code=201)
def new_job(body: JobInput, user=Depends(write_user)):
    jid = secrets.token_hex(16)
    width, height = ASPECT_SIZES[body.aspect_ratio]
    with db.transaction() as c:
        if c.execute("SELECT 1 FROM jobs WHERE owner_id=? AND status IN ('queued','running')", (user['id'],)).fetchone():
            raise HTTPException(409, '你已有排队或生成中的任务，请等待完成')
        if c.execute("SELECT count(*) FROM jobs WHERE status='queued'").fetchone()[0] >= 20:
            raise HTTPException(429, '等待队列已满，请稍后再试')
        c.execute('INSERT INTO jobs(id,owner_id,prompt,negative_prompt,steps,seed,status,created_at,width,height) VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (jid,user['id'],body.prompt,body.negative_prompt,body.steps,body.seed,'queued',now(),width,height))
    return public_job(owned(jid,user))
```

逐行理解：

1. `Depends(write_user)` 先验证用户与 CSRF。
2. 画幅转换成明确宽高，不让前端随意指定巨大图片。
3. 事务中检查该用户是否已有 queued/running，防止双击造成重复活动任务。
4. 全局队列最多等待 20 项，超出返回 429，而不是无限堆积。
5. 插入 queued 记录，owner_id 来自 user。
6. 返回任务响应，HTTP 201 **不是图片已完成**。

### 本步交付和验收

先不启动 worker：登录后提交一次，得到 queued；立即再提交返回 409；数据库能查到一条记录。这样可以单独确认业务接口，不被模型问题干扰。

---

## 第 6 步：实现 worker，把 queued 真正推进到 succeeded

**上一阶段只排队、不执行。**现在让一个后台线程消费队列。先接模拟引擎验证状态流转，再接第 2 步的真实适配器。

### 6.1 认领任务：检查和修改必须在同一个事务

`F:\uv\text-to-image\platform\backend\worker.py` 的实际源码：

```python
def claim_next(db):
    with db.transaction() as connection:
        if connection.execute("SELECT 1 FROM jobs WHERE status='running' LIMIT 1").fetchone():
            return None
        item = connection.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at,rowid LIMIT 1").fetchone()
        if item is None:
            return None
        started = now()
        connection.execute("UPDATE jobs SET status='running',started_at=?,error=NULL WHERE id=? AND status='queued'", (started, item['id']))
        result = dict(item)
        result.update(status='running', started_at=started)
        return result
```

`status='running'` 的全局检查保证当前单机执行槽位只有一个。排序使用 created_at、rowid，避免时间相同时队列位置和执行顺序不一致。

**事务在认领后立即结束。不要把 GPU 的九十秒推理放在这个数据库事务里，否则别人的登录、入队、删除都可能被阻塞。**

### 6.2 执行、保存与错误分类

同文件 execute() 源码：

```python
def execute(db, engine, item, stop_event, resume=False):
    def persist(prompt_id):
        db.execute("UPDATE jobs SET prompt_id=? WHERE id=? AND status='running'", (prompt_id, item['id']))
    try:
        result = engine.resume(item, stop_event) if resume else engine.generate(item, persist, stop_event)
        finish(db, item['id'], result)
    except EngineUnsafe as exc:
        # Keep running/prompt_id for reconciliation after an operator restores connectivity.
        db.execute("UPDATE jobs SET error=? WHERE id=?", (str(exc), item['id']))
        raise
    except Exception as exc:
        log.exception('Job %s failed', item['id'])
        message = str(exc) if isinstance(exc, EngineError) else '生成失败，请稍后重试或联系管理员。'
        db.execute("UPDATE jobs SET status='failed',finished_at=?,error=? WHERE id=? AND status='running'", (now(), message, item['id']))
```

理解这三条路径：

- 正常：generate 返回结果 → finish 校验任务仍为 running → 写 succeeded、图片路径和耗时。
- 普通失败：保存 failed 和用户可见错误，下一项任务可以继续。
- `EngineUnsafe`：不确定旧 GPU 工作是否停止，记录错误并向上抛出，让 worker 停止调度。

`run_worker()` 负责循环：等引擎就绪 → 协调旧 running → 检查引擎全局队列 → claim_next → execute。另有进程级 worker 文件锁，防止意外启动多个服务实例。

### 6.3 先写一个模拟引擎测试

以下是测试思路的教学示例，不是生产引擎：

```python
class FakeEngine:
    def generate(self, job, on_prompt, stop_event):
        on_prompt('fake-engine-id')
        return {
            'image_path': 'images/fixture.png',
            'image_sha256': 'fixture-hash',
            'elapsed_seconds': 0.01,
        }
# 在测试中替换 ComfyEngine，使用临时数据库。
# 创建两条 queued，验证第一条结束后第二条才开始。
```

模拟测试证明队列逻辑，不证明模型或图片校验正常；真实 PNG 验收在后面单独做。

### 本步交付和验收

两位测试用户各提交一项；同时至多一个 running。模拟失败一次，第一项 failed，第二项仍能完成。不要靠肉眼看页面证明没有并发。

---

## 第 7 步：把 Vue 页面接到任务状态，而不是接到长请求

到这里后端闭环已成立，前端只需要驱动和显示它。

目录：`F:\uv\text-to-image\platform\frontend\apps\moss\src`。从 api.ts 的请求封装开始，再写 App.vue；Vben 负责布局，Naive UI 提供表单、确认框等组件，业务状态自己管理。

### 7.1 三类状态不要混在一起

| 状态 | 例子 | 来源 |
| --- | --- | --- |
| 用户正在编辑什么 | 提示词、步数、画幅 | 表单 |
| 服务器实际在做什么 | queued/running/succeeded | API |
| 界面怎么展示 | 当前页面、主题、侧栏、弹窗 | 前端本地 |

例如，用户选择新画幅时，不应该被后台轮询回来的旧作品尺寸覆盖。当前实现通过 drafting 等状态区分“编辑新任务”和“查看旧记录”。

### 7.2 提交与查询的分工

下面是与当前设计一致的教学示例；省略了完整的错误、分页和组件类型封装：

```typescript
const form = reactive({ prompt: '', negative_prompt: '', steps: 8,
                        seed: 42, aspect_ratio: '1:1' });
const selected = ref<Job | null>(null);
const submitting = ref(false);

async function submit() {
  if (submitting.value) return;
  submitting.value = true;
  try {
    selected.value = await api.request<Job>('/jobs', {
      method: 'POST', body: { ...form },
    });
    // 到这里仅说明已入队，不显示“出图成功”。
  } finally {
    submitting.value = false;
  }
}
async function refreshSelected() {
  if (!selected.value) return;
  selected.value = await api.request<Job>(
    `/jobs/${encodeURIComponent(selected.value.id)}`,
  );
}
```

`ApiClient` 统一添加 CSRF、保留会话并处理 401。定时刷新要在组件卸载时清理，并避免重叠请求；当前应用可见时约每 4 秒刷新，不是每张卡片创建一个定时器。

### 7.3 按状态展示，不伪造百分比

```vue
<!-- 教学示例：状态映射 -->
<p v-if="selected?.status === 'queued'">排队位置：{{ selected.queue_position }}</p>
<GenerationWaiting v-else-if="selected?.status === 'running'" />
<img v-else-if="selected?.status === 'succeeded'" :src="selected.image_url" alt="生成结果" />
<p v-else-if="selected?.status === 'failed'">{{ selected.error }}</p>
```

实际动画组件需要按现有 props 使用。没有可靠的全流程进度，就展示等待状态，不把采样步数百分比冒充总进度。

### 本步交付和验收

点击生成后按钮防重复提交；刷新网页后可通过列表重新看到活动任务；失败显示具体状态而不是一直转圈。先用浏览器模拟 API 测试，再做真实联调。

---

## 第 8 步：围绕已完成任务做图库，而不是再做一套数据系统

图库和工作台使用同一张 jobs 表，不需要单独复制一份历史任务数据。

### 8.1 列表查询

查询条件必须从 `owner_id = 当前用户` 开始，再追加状态和分页：

```sql
-- 教学 SQL：参数化执行，不能拼接用户输入
SELECT * FROM jobs
WHERE owner_id = ?
ORDER BY created_at DESC, rowid DESC
LIMIT ? OFFSET ?;
```

列表只返回必要元数据，不暴露服务器真实路径。成功任务给出鉴权图片接口 URL，而不是公开静态目录。

### 8.2 为什么图片要经过后端

下载链路：GET /api/jobs/{id}/image → current() → owned() → 检查成功状态和私有目录范围 → FileResponse。

否则即使列表隐藏了别人的作品，别人猜中图片地址仍可能读到文件。这是“功能能用”和“权限闭环”的区别。

### 8.3 删除与参数复用

- 删除：卡片按钮 → 二次确认 → DELETE → 后端检查归属与非活动状态 → 删除平台图片副本与记录 → 刷新当前页。
- 参数复用：把 prompt、negative_prompt、steps、seed、aspect_ratio 填回工作台，用户确认后创建新任务，而不是修改旧任务。

文件与数据库不是同一事务系统。当前删除流程不能声称是跨文件系统的完全原子事务；更大规模可设计删除标记和后台清理。

### 本步交付和验收

取消确认不发 DELETE；确认只发一次；A 不能删 B；queued/running 不能删；删空最后一页回退前一页。只使用测试记录，不拿用户作品做破坏性验收。

---

## 第 9 步：补上最重要的可靠性——超时与重启后怎么办

到第 8 步，正常流程已完成。现在故意让网络超时、进程重启，检查数据是否仍可信。**这一步才是从演示程序走向可用应用的分界。**

### 9.1 为什么必须先保存 prompt_id

```text
错误顺序：POST 模型 → 等响应拿 ID → 存数据库
风险：模型已接受任务，但响应丢了；数据库不知道这个任务。

当前顺序：生成 ID → 存数据库 → POST 模型（携带同一个 ID）
收益：响应丢失后，仍能查 history/queue 协调，不必盲目重提。
```

当前 generate() 中的关键顺序：

```python
prompt_id = str(uuid.uuid4())
on_prompt(prompt_id)  # worker 回调先提交到 jobs.prompt_id
accepted = self._request('/prompt', {
    'prompt': graph, 'prompt_id': prompt_id, 'client_id': 'moss-platform',
})
if accepted.get('prompt_id') != prompt_id:
    raise EngineUnsafe('推理服务任务标识异常，队列已暂停。')
return self._wait_result(job, prompt_id, stop_event, started)
```

此片段省略资源检查。它是“可协调”的基础，不是宣称实现跨所有故障场景的 exactly-once。

### 9.2 恢复时先查什么

| 查到的事实 | 处理方式 |
| --- | --- |
| history 已有结果 | 校验结果，补写成功或失败 |
| queue 仍有这个 prompt_id | 继续等待同一任务 |
| 读取期间 queue→history 发生切换 | 再查一次 history，避免误判丢失 |
| 确认记录不存在 | 明确失败，让用户决定是否重试 |
| 无法确认旧任务停止 | 暂停新调度，不制造第二个不确定任务 |

这里要区分两个超时：单次 HTTP 读取超时可能只是暂时不可用；整个任务超过允许时长，则进入停止/协调流程。当前适配器不会因为一次读取超时就再次 POST。

### 本步交付和验收

写故障注入测试：提交响应丢失、轮询先超时再成功、队列刚好切到历史、后端重启。断言不只是“没有抛异常”，还要验证没有重复提交。

---

## 第 10 步：最后做体验、启动和完整验收

先有可用闭环，再加体验：昼夜自动主题与手动切换、等待动画、低高度布局、手机竖屏、侧栏点击固定与居中。

启动入口是 `F:\uv\text-to-image\start.bat`。启动脚本将前后端与推理进程生命周期串起来，运行时不依赖用户桌面 PATH 中必须存在 pnpm。当前是本机 Vite 开发服务，不是生产公网部署。

重启只能停止路径已核实属于本项目的进程，不能 `taskkill /IM python.exe` 误杀别人的 Python。重启会中断活动任务，应在界面和说明中告知。

### 完整验收顺序

1. 临时数据库跑后端测试，验证校验、权限、队列、恢复。
2. 模拟 API 跑浏览器测试，验证提交/状态/删除/侧栏交互。
3. 独立账号跑真实 8 步出图，校验 PNG 与宽高。
4. 两位用户先后提交，核实 GPU 无重叠、图片归属正确。
5. 再验证重启和失败路径，不把一次成功当长期稳定性结论。

当前已有一次恢复验收：512×512、8 步，记录耗时 90.468 秒；后端历史完整回归 57 项通过。报告为 `F:\uv\text-to-image\platform\logs\engine-recovery-live.json`。这不是 SLA、平均耗时或压力测试成绩。

到此你已经把第 1 步的用户流程逐段落实，而不是得到一堆互不相关的页面。

---

# 第三部分：把完整流程讲给面试官，而不是背技术清单

## 11. 先用两分钟讲清楚项目

按“为什么做 → 做了什么 → 请求如何走 → 重点解决什么 → 边界”来讲：

> 我做的是一个基于已有 MOSS-Image 模型的本地多人文生图平台，目标是把单人推理工具变成可以登录、排队和管理私有作品的应用，不涉及训练模型。
>
> 技术上使用 Vue3、Vben 组件、FastAPI 和 SQLite。用户提交后，接口只做鉴权、参数校验和任务入库；单 worker 原子认领任务，调用固定 ComfyUI 工作流，生成后校验并保存图片。前端查询任务状态，成功后通过鉴权接口展示结果。
>
> 我主要关注三个问题：多人共享单 GPU 怎么避免任务重叠；长任务遇到超时和重启怎么避免重复提交；图片接口怎么确保用户隔离。分别通过短事务认领、持久化 prompt_id 与恢复协调、后端统一 owner 校验实现。
>
> 当前已经有登录、私有图库、复用、下载、删除和响应式界面，也有模拟测试与真实出图验收。它仍是单机串行方案，没有包装成分布式高并发平台。

如果有 AI 辅助开发，应明确自己的真实职责：需求拆解、方案理解、代码审查、调试和验证。没有独立完成的部分不要硬说成全部独立原创。

## 12. 让人印象深刻的三个问题：讲设计矛盾，不讲安装流水账

### 问题一：请求超时了，但 GPU 可能还在跑，怎么办？

**为什么难：**业务端没收到响应，与引擎没接受任务，是两个不同事实。直接重试可能浪费 GPU、生成两张图，甚至让平台状态与引擎状态对不上。

**最初容易想到但不可靠的方案：**捕获 TimeoutError 后重新 POST；或重启时把所有 running 改成 queued。

**最终设计：**先持久化 prompt_id，再提交；不确定时查询队列和历史，已有结果就恢复，仍运行就继续等，确实丢失则失败；无法证明安全时停止继续派发。

**验证：**模拟响应丢失和读取超时，断言调用次数没有增加；模拟队列刚切到历史，验证再次读取历史能找回结果。

**面试可以这样说：**

> 我印象最深的不是模型怎么调用，而是怎么处理“请求失败但任务可能成功”。后来我把平台 ID 与引擎 ID 分开，提交前先持久化引擎 ID。恢复时根据事实协调状态，而不是把超时直接等同于失败。这让我认识到长任务系统首先要保证状态可追踪，而不只是捕获异常后重试。

**不能夸大：**不是通用消息队列的 exactly-once；跨引擎重启导致历史消失时仍可能只能明确失败。

### 问题二：多人提交，为什么 Web 可以并发而 GPU 必须串行？

**为什么难：**多人能同时调用 API，不等于这台 8GB 显存机器能同时加载多个模型任务。把推理放到每个请求线程，只会让显存竞争更严重。

**设计：**入队与执行分离；每用户最多一个活动任务，全局限制排队数；数据库短事务原子认领；单 worker 文件锁防止启动多个后端；执行前还检查推理端是否有其他本地客户端的任务。

**验证：**两个用户同一时间入队，比较 started_at/finished_at 与引擎队列，确认执行不重叠；模拟失败后检查下一项是否继续。

**面试可以这样说：**

> 我没有为了“异步”而让 GPU 并发。我的做法是让 API 快速入队，把稀缺的 GPU 当作一个容量为一的资源槽位。事务只覆盖认领，不覆盖推理，这样任务执行九十秒时其他用户仍能登录和查询。这里事务、进程锁、引擎队列检查各自解决不同层面的竞争。

**不能夸大：**本项目不是分布式调度；增加第二台机器后需要任务租约、worker 标识与资源归属，不能简单多开线程。

### 问题三：图库列表做了鉴权，为什么图片仍可能泄露？

**为什么难：**只在前端隐藏别人的卡片，没有限制图片 URL；或认为管理员天然可以读所有作品。

**设计：**owner 从会话取得；列表、详情、图片、删除统一归属检查；图片放私有目录，经 FileResponse 返回；服务端检查路径范围，不接受任意文件名；管理账号权限与看图权限分开。

**验证：**A、B 两账号分别测试详情、图片、删除，不只测试列表；尝试修改 ID 与路径，确认越权和穿越被拒绝。

**面试可以这样说：**

> 我最初关注的是“列表里只有自己的数据”，后来把检查扩展到真正的数据出口。图片不再作为公开静态资源，而是经过同一套会话和 owner 校验返回。安全边界不是某个页面，而是所有能读写这份资源的接口。

**不能夸大：**本地鉴权不等于已经具备公网完整安全能力；公网还需要 HTTPS、限流、审计、备份与内容安全设计。

### 环境故障应该怎么讲？

只有在面试官追问 Windows 部署和排障时，再讲 WMI 阻塞、运行库隔离和 PATH。讲“观测到什么 → 用什么证据定位 → 怎样局部修复 → 如何验证”，不要罗列每一次尝试，更不要把尚未证明的推测讲成根因。

这些是工程排障能力的补充，不替代前面三个业务设计问题。运行库隔离后真实出图通过，是观察到的结果；不能推导成“所有访问异常都由某个 DLL 引起”。

## 13. 接着会被追问什么？

| 追问 | 回答的核心 |
| --- | --- |
| 为什么不用 Redis/Celery？ | 当前单机规模用持久化 SQLite 队列降低部署成本，必要时再引入专业队列，不是认为它们没价值 |
| 为什么不直接 async await？ | async 不解决持久化、断线、恢复和 GPU 容量限制，长任务生命周期要独立于请求 |
| 为什么不用 JWT？ | 当前 Cookie 会话便于改密、禁用后撤销；JWT 也要处理撤销与存储安全 |
| 8 步是不是比 16 步快一倍？ | 总耗时还有加载、文本编码、解码与保存，必须拆阶段测量，不能按步数线性推断 |
| 生成失败后队列一定能继续吗？ | 普通失败可以；停止状态不确定时故意暂停，安全优先于错误地继续 |
| 你做了模型优化吗？ | 使用已有量化权重、步数/分辨率约束和资源生命周期管理，没有自研量化算法或训练模型 |
| 删图和删数据库能完全原子吗？ | 当前不是跨文件系统事务，后续可用删除标记与后台清理处理一致性 |

### 简历只写能解释和演示的内容

> MOSS Studio｜FastAPI / Vue3 / TypeScript / SQLite / ComfyUI
>
> - 实现文生图任务入队、单 GPU 串行消费、状态持久化与私有图库。
> - 通过会话、CSRF 与 owner 约束保护列表、图片和删除接口。
> - 设计 prompt_id 预持久化及重启协调流程，减少不确定状态下的重复提交风险。
> - 建立接口、浏览器模拟与真实 GPU 三层验收，完成本地运行交付。

不写自研大模型、百万并发、商业级 SaaS 或没有对照实验的性能提升百分比。

## 14. 最后怎么演示，让讲述和代码对得上

演示只走一条线，控制在 5～8 分钟：

1. 打开工作台，提交一张测试图；此时解释“201 表示入队”。
2. 等待期间打开 new_job → claim_next → execute，顺着调用链解释。
3. 展示另一用户看不到前一用户作品，并解释 owned()。
4. 出图后展示宽高、详情、下载和参数复用。
5. 展示一个超时不重复提交的测试，而不是现场故意打断别人的任务。
6. 结束时讲一个真实取舍：单 GPU 串行更稳定，但吞吐受限；下一步若扩容要拆调度和 worker。

真实生成耗时较长，提前准备历史截图作为备份，但明确它是历史结果。不要假装是实时生成。

**读完应能做到：不用背稿，画出一次请求的流向；找到对应代码；解释一次异常路径；现场修改一个字段并补测试。做到这些，项目才真正属于你的知识，而不是一份技术名词列表。**
