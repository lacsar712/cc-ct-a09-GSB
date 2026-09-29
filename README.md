# 数控刀补复核台

操作员提交刀具编号与刀补微米值；刀号**必须以「字头台」已登记字头起笔**，否则一律退回。后台 worker 用 PostgreSQL 行锁（`select_for_update(skip_locked=True)`）认领待复核记录，按绝对值是否不超过 12 微米给出「合格」或「超差」。

## 字头规则

- 字头台由**操作员（machinist）维护**：可登记、删除字头；每次增删写一条**改动履历**。
- 刀号起笔必须命中字头表中某个**当前**字头（长字头优先，避免互相遮蔽）。
- 规则在后端唯一收口（`desk/services.py` 的 `validate_tool_code` / `accept_submission`），退回文案统一为 `PREFIX_REJECT_MESSAGE`，三条路径口径一致：
  1. **页面预拦**：字头表与退回文案均取自 `GET /api/prefixes/rule`，页面不自创口径；
  2. **绕过页面直连接口**：`POST /api/submissions` 在后端按同一规则再拦，返回 400 统一文案，不落库；
  3. **落库前刀号被改写**：事务内建行后，以「实际落库行」的 `tool_code` 回读当前字头表复核，不合即整体回滚。
- **删字头不改旧账**：删除字头只影响此后的新提交，已收下的旧刀号原样保留；字头行删除后履历仍在（履历不设级联外键）。
- **复核员（auditor）只读**：可看字头表、退回样例、改动履历，但不能增删字头、不能提交刀补（写接口返回 403）。

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
| machinist | machine123456 | 提交刀补、维护字头台 |
| auditor | audit123456 | 只读列表与字头台 |

## 启动

```bash
docker compose up --build
```

健康检查：`GET http://localhost:8196/api/health` → `{"status":"ok"}`

## 验收

1. machinist 登录后，种子字头表只登记了「甲」；种子数据 T01 合格（5 µm）、T09 超差（20 µm）。
2. 提交「甲刀零一」应收下进入待复核，数秒内 worker 处理为「已完成/合格」；提交「乙刀零九」应被退回，列表中不落库。
3. 绕过页面直连 `POST /api/submissions` 交「乙刀零九」，同样 400 退回、不落库（文案与页面一致）。
4. 菜单进入「字头台」：含维护区、退回样例、改动履历；删除「甲」后履历新增一条删除记录，旧「甲刀零一」刀号仍在；此后再交任何「甲…」刀号均被退回。
5. auditor 登录后只能看：复核列表、字头表、退回样例、改动履历；没有提交表单，字头台无增删按钮，直连写接口返回 403。

## 接口（/api）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | `/auth/login` | 公开 | 登录换 JWT |
| GET | `/submissions` | 登录 | 刀补列表 |
| POST | `/submissions` | 操作员 | 提交（后端按字头规则收口） |
| GET | `/prefixes/rule` | 登录 | 当前字头 + 统一退回文案（页面预拦用） |
| GET | `/prefixes` | 登录 | 字头表 |
| POST | `/prefixes` | 操作员 | 登记字头并写履历 |
| DELETE | `/prefixes/{prefix}` | 操作员 | 删除字头并写履历 |
| GET | `/prefixes/history` | 登录 | 字头改动履历 |

## 目录

```text
backend/          Django 工程（config/、desk/、worker.py）
frontend/         SolidJS 单页
docker-compose.yml
```
