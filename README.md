# 数控刀补复核台

操作员提交刀具编号与刀补微米值；后台 worker 用 PostgreSQL 行锁（`select_for_update(skip_locked=True)`）认领待复核记录，按绝对值是否不超过 12 微米给出「合格」或「超差」。

## 字头台规则

- 刀号**必须以字头台登记过的字头起笔**，不合字头一律退回。字头表由操作员在「字头台」维护，新增、删除都写入**改动履历**。
- 校验只在服务端 `desk.services.accept_submission` 一处收口：页面预拦、**绕过页面的直连接口**、以及落库前写入都走同一规则、同一退回口径；落库前任何改写刀号的尝试仍会被退回，刀号不会被偷改。
- 不合字头的刀号记入**退回样例**（字头台可见），不产生刀补记录。
- 删除字头**只影响新提交**：已收下的旧刀号原样保留（字头为字符串快照，不与字头表联动），可与履历做新旧对照。
- 复核员可查看字头表、退回样例、改动履历，但**不能维护字头**（增删均 403）。

## 字头台接口（均需登录）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/prefixes` | 全员 | 字头表 |
| POST | `/api/prefixes` | 操作员 | 登记字头并写履历（重复 409） |
| DELETE | `/api/prefixes/{prefix}` | 操作员 | 删字头并写履历，旧刀号不改 |
| GET | `/api/prefix-changelogs` | 全员 | 字头增删履历 |
| GET | `/api/rejected-tool-codes` | 全员 | 不合字头退回样例 |

## 技术栈

| 层 | 选型 |
|----|------|
| 后端 | Django 5 + django-ninja（ASGI / uvicorn） |
| 前端 | SolidJS + Vite，nginx 反代 `/api` |
| 数据库 | PostgreSQL 16 |
| 鉴权 | JWT（python-jose），令牌存浏览器 localStorage |

## 端口

| 服务 | 地址 |
|------|------|
| 页面 | http://localhost:3196 |
| 接口 | http://localhost:8196 |
| PostgreSQL | localhost:54396（库名 `cncoffset`） |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| machinist | machine123456 | 可提交刀补 |
| auditor | audit123456 | 只读列表 |

## 启动

```bash
cd projects/17-cnc-tool-offset-desk
docker compose up --build
```

健康检查：`GET http://localhost:8196/api/health` → `{"status":"ok"}`

## 验收

1. machinist 登录后，种子数据应显示刀具 T01 合格（刀补 5 µm）、T09 超差（刀补 20 µm）；字头台初始登记「甲」「乙」。
2. 提交一条新刀补后，状态先为「待复核」，数秒内 worker 处理为「已完成」并给出结论。
3. auditor 登录后只能看列表，没有提交表单。
4. 字头规则（字头台只留「甲」时）：
   - 交「甲刀零一」应收下；交「乙刀零九」应退回，并出现在退回样例。
   - 网页预拦与直连 `POST /api/submissions`（绕过页面）退回口径一致，均为 400 且文案相同；落库前改写成未登记字头也被退回。
   - 删掉「甲」后再交「甲刀零一」应退回；此前已收下的旧「甲刀零一」刀号原样仍在。
   - 字头增删在「改动履历」可查，可与旧刀号做新旧对照。
   - 复核员能看到字头表、退回样例、履历，但增删字头均被拒绝。

### 自动化测试

后端验收测试见 `backend/desk/tests/test_prefix_desk.py`，覆盖上述三条路径、新旧对照与只读权限。本地用 SQLite 跑：

```bash
cd backend
POSTGRES_ENGINE=django.db.backends.sqlite3 POSTGRES_DB=':memory:' POSTGRES_HOST=localhost \
  python manage.py test desk.tests.test_prefix_desk
```


## 目录

```text
backend/          Django 工程（config/、desk/、worker.py）
frontend/         SolidJS 单页
docker-compose.yml
PRD.md
```
