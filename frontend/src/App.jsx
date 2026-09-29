import { createSignal, onMount, Show, For, createEffect } from "solid-js";
import {
  addPrefix,
  clearSession,
  createSubmission,
  deletePrefix,
  fetchPrefixChangelogs,
  fetchPrefixes,
  fetchRejectedToolCodes,
  fetchSubmission,
  fetchSubmissions,
  getUser,
  login,
  setSession,
} from "./api";

const statusLabel = {
  pending: "待复核",
  processing: "复核中",
  done: "已完成",
};

const roleLabel = {
  machinist: "操作员",
  auditor: "复核员",
};

// 与后端 services.reject_message 完全一致的统一口径
function rejectMessage(toolCode, head) {
  return `刀号「${toolCode}」起笔字头「${head}」未在字头台登记，刀号必须以已登记字头起笔，退回。`;
}

// 与后端一致的最长字头匹配
function matchPrefix(prefixes, code) {
  let matched = null;
  for (const p of prefixes) {
    if (code.startsWith(prefix) && (matched === null || p.length > matched.length)) {
      matched = p;
    }
  }
  return matched;
}

function readHash() {
  const raw = (location.hash || "#/").replace(/^#/, "") || "/";
  const m = raw.match(/^\/detail\/(\d+)/);
  if (m) return { name: "detail", id: Number(m[1]) };
  if (raw === "/prefix" || raw.startsWith("/prefix")) return { name: "prefix", id: null };
  return { name: "home", id: null };
}

function App() {
  const [user, setUser] = createSignal(getUser());
  const [rows, setRows] = createSignal([]);
  const [detail, setDetail] = createSignal(null);
  const [route, setRoute] = createSignal(readHash());
  const [error, setError] = createSignal("");
  const [notice, setNotice] = createSignal("");
  const [loading, setLoading] = createSignal(false);

  const [loginUser, setLoginUser] = createSignal("machinist");
  const [loginPass, setLoginPass] = createSignal("machine123456");

  const [toolCode, setToolCode] = createSignal("");
  const [offsetUm, setOffsetUm] = createSignal("");

  // 字头台
  const [prefixes, setPrefixes] = createSignal([]);
  const [prefixRows, setPrefixRows] = createSignal([]);
  const [prefixesLoaded, setPrefixesLoaded] = createSignal(false);
  const [newPrefix, setNewPrefix] = createSignal("");
  const [rejected, setRejected] = createSignal([]);
  const [changelogs, setChangelogs] = createSignal([]);

  function goHome() {
    location.hash = "#/";
  }

  function goDetail(id) {
    location.hash = `#/detail/${id}`;
  }

  function goPrefix() {
    location.hash = "#/prefix";
  }

  async function loadRows() {
    setLoading(true);
    setError("");
    try {
      const data = await fetchSubmissions();
      setRows(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(id) {
    setLoading(true);
    setError("");
    try {
      setDetail(await fetchSubmission(id));
    } catch (e) {
      setError(e.message);
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }

  async function loadPrefixes() {
    try {
      const data = await fetchPrefixes();
      setPrefixRows(data);
      setPrefixes(data.map((p) => p.prefix));
      setPrefixesLoaded(true);
    } catch (e) {
      // 字头表加载失败时不臆造规则，交给服务端收口
      setPrefixesLoaded(false);
    }
  }

  async function loadPrefixDesk() {
    setError("");
    try {
      const [ps, rs, ls] = await Promise.all([
        fetchPrefixes(),
        fetchRejectedToolCodes(),
        fetchPrefixChangelogs(),
      ]);
      setPrefixRows(ps);
      setPrefixes(ps.map((p) => p.prefix));
      setPrefixesLoaded(true);
      setRejected(rs);
      setChangelogs(ls);
    } catch (e) {
      setError(e.message);
    }
  }

  onMount(() => {
    const onHash = () => setRoute(readHash());
    window.addEventListener("hashchange", onHash);
    if (user()) {
      loadPrefixes();
      if (route().name === "detail") loadDetail(route().id);
      else if (route().name === "prefix") loadPrefixDesk();
      else loadRows();
    }
    return () => window.removeEventListener("hashchange", onHash);
  });

  createEffect(() => {
    const r = route();
    if (!user()) return;
    if (r.name === "detail" && r.id) loadDetail(r.id);
    if (r.name === "home") loadRows();
    if (r.name === "prefix") loadPrefixDesk();
  });

  async function handleLogin(e) {
    e.preventDefault();
    setError("");
    try {
      const data = await login(loginUser(), loginPass());
      setSession(data.token, {
        username: data.username,
        role: data.role,
        can_write: data.can_write,
      });
      setUser(getUser());
      goHome();
      await Promise.all([loadRows(), loadPrefixes()]);
    } catch (err) {
      setError(err.message);
    }
  }

  function handleLogout() {
    clearSession();
    setUser(null);
    setRows([]);
    setDetail(null);
    setPrefixes([]);
    setPrefixRows([]);
    setRejected([]);
    setChangelogs([]);
    goHome();
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setNotice("");
    const code = toolCode().trim();
    // 页面预拦：与直连接口、落库前收口同一口径。最终仍由服务端兜底。
    if (prefixesLoaded()) {
      const matched = matchPrefix(prefixes(), code);
      if (matched === null) {
        setError(rejectMessage(code, code.slice(0, 1)));
        return;
      }
    }
    try {
      await createSubmission(code, offsetUm());
      setToolCode("");
      setOffsetUm("");
      await loadRows();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleAddPrefix(e) {
    e.preventDefault();
    setError("");
    setNotice("");
    try {
      await addPrefix(newPrefix().trim());
      setNewPrefix("");
      await loadPrefixDesk();
      setNotice("字头已登记并写入履历");
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDeletePrefix(prefix) {
    setError("");
    setNotice("");
    if (!window.confirm(`确认删除字头「${prefix}」？已收下的旧刀号不会被改写。`)) return;
    try {
      await deletePrefix(prefix);
      await loadPrefixDesk();
      setNotice(`字头「${prefix}」已删除并写入履历，旧刀号原样保留`);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div class="page">
      <header class="topbar">
        <div class="brand">
          <h1>数控刀补复核台</h1>
          <p class="hint">
            刀号必须以字头台登记过的字头起笔，不合字头一律退回；刀补绝对值不超过十二微米判合格。
          </p>
        </div>
        <Show when={user()}>
          <nav class="topnav">
            <a
              href="#/"
              class={route().name === "home" ? "active" : ""}
              onClick={(e) => {
                e.preventDefault();
                goHome();
              }}
            >
              复核总览
            </a>
            <a
              href="#/prefix"
              class={route().name === "prefix" ? "active" : ""}
              onClick={(e) => {
                e.preventDefault();
                goPrefix();
              }}
            >
              字头台
            </a>
          </nav>
        </Show>
      </header>

      <Show when={error()}>
        <div class="banner error">{error()}</div>
      </Show>
      <Show when={notice()}>
        <div class="banner ok">{notice()}</div>
      </Show>

      <Show
        when={user()}
        fallback={
          <section class="card">
            <h2>登录</h2>
            <form onSubmit={handleLogin} class="form">
              <label>
                用户名
                <input
                  value={loginUser()}
                  onInput={(e) => setLoginUser(e.currentTarget.value)}
                />
              </label>
              <label>
                密码
                <input
                  type="password"
                  value={loginPass()}
                  onInput={(e) => setLoginPass(e.currentTarget.value)}
                />
              </label>
              <button type="submit">进入系统</button>
            </form>
            <p class="hint">操作员 machinist / machine123456；复核员 auditor / audit123456（只读）</p>
          </section>
        }
      >
        <section class="card toolbar">
          <div>
            当前用户：<strong>{user().username}</strong>（{roleLabel[user().role] || user().role}）
          </div>
          <button type="button" class="ghost" onClick={handleLogout}>
            退出
          </button>
        </section>

        <Show when={route().name === "home"}>
          <Show when={user().can_write}>
            <section class="card">
              <h2>提交刀补</h2>
              <p class="hint">
                已登记字头：
                {prefixes().length ? prefixes().join("、") : "（字头台为空，任何刀号都将退回）"}
              </p>
              <form onSubmit={handleSubmit} class="form inline">
                <label>
                  刀具编号
                  <input
                    placeholder="如 甲刀零一"
                    value={toolCode()}
                    onInput={(e) => setToolCode(e.currentTarget.value)}
                    required
                  />
                </label>
                <label>
                  刀补（微米）
                  <input
                    type="number"
                    value={offsetUm()}
                    onInput={(e) => setOffsetUm(e.currentTarget.value)}
                    required
                  />
                </label>
                <button type="submit">提交待复核</button>
              </form>
            </section>
          </Show>

          <section class="card">
            <div class="toolbar">
              <h2>复核列表</h2>
              <button type="button" class="ghost" onClick={loadRows} disabled={loading()}>
                {loading() ? "刷新中…" : "刷新"}
              </button>
            </div>
            <table>
              <thead>
                <tr>
                  <th>刀具</th>
                  <th>字头</th>
                  <th>刀补 µm</th>
                  <th>状态</th>
                  <th>结论</th>
                  <th>提交时间</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <For each={rows()}>
                  {(row) => (
                    <tr>
                      <td>{row.tool_code}</td>
                      <td>{row.prefix || "—"}</td>
                      <td>{row.offset_um}</td>
                      <td>{statusLabel[row.status] || row.status}</td>
                      <td class={row.verdict === "合格" ? "pass" : row.verdict === "超差" ? "fail" : ""}>
                        {row.verdict || "—"}
                      </td>
                      <td>{new Date(row.created_at).toLocaleString()}</td>
                      <td>
                        <button type="button" class="ghost" onClick={() => goDetail(row.id)}>
                          详情
                        </button>
                      </td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
            <Show when={!rows().length && !loading()}>
              <p class="hint">暂无记录</p>
            </Show>
          </section>
        </Show>

        <Show when={route().name === "prefix"}>
          <section class="card">
            <div class="toolbar">
              <h2>字头台 · 字头维护</h2>
              <button type="button" class="ghost" onClick={loadPrefixDesk}>
                刷新
              </button>
            </div>
            <p class="hint">
              刀号必须以已登记字头起笔。删除字头只影响新提交，已收下的旧刀号原样保留。
            </p>

            <table>
              <thead>
                <tr>
                  <th>字头</th>
                  <th>登记时间</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <For each={prefixRows()} fallback={<tr><td colspan="3" class="hint">字头台为空</td></tr>}>
                  {(p) => (
                    <tr>
                      <td><strong>{p.prefix}</strong></td>
                      <td class="hint">{new Date(p.created_at).toLocaleString()}</td>
                      <td>
                        <Show when={user().can_write}>
                          <button type="button" class="danger ghost" onClick={() => handleDeletePrefix(p.prefix)}>
                            删除
                          </button>
                        </Show>
                      </td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>

            <Show when={user().can_write} fallback={
              <p class="hint">复核员只读：可查看字头表、退回样例与改动履历，不能维护字头。</p>
            }>
              <form onSubmit={handleAddPrefix} class="form inline" style={{"margin-top": "1rem"}}>
                <label>
                  新增字头
                  <input
                    placeholder="如 甲"
                    value={newPrefix()}
                    onInput={(e) => setNewPrefix(e.currentTarget.value)}
                    required
                  />
                </label>
                <button type="submit">登记字头</button>
              </form>
            </Show>
          </section>

          <section class="card">
            <h2>退回样例</h2>
            <p class="hint">不合字头被退回的刀号，供对照口径。</p>
            <table>
              <thead>
                <tr>
                  <th>退回刀号</th>
                  <th>起笔字头</th>
                  <th>刀补 µm</th>
                  <th>退回原因</th>
                  <th>提交人</th>
                  <th>时间</th>
                </tr>
              </thead>
              <tbody>
                <For each={rejected()} fallback={<tr><td colspan="6" class="hint">暂无退回样例</td></tr>}>
                  {(r) => (
                    <tr>
                      <td>{r.tool_code}</td>
                      <td>{r.prefix || "—"}</td>
                      <td>{r.offset_um ?? "—"}</td>
                      <td class="fail">{r.reason}</td>
                      <td>{r.submitter_name || "—"}</td>
                      <td>{new Date(r.created_at).toLocaleString()}</td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
          </section>

          <section class="card">
            <h2>改动履历</h2>
            <p class="hint">字头新增、删除均留痕，可与旧刀号做新旧对照。</p>
            <table>
              <thead>
                <tr>
                  <th>字头</th>
                  <th>动作</th>
                  <th>操作人</th>
                  <th>时间</th>
                </tr>
              </thead>
              <tbody>
                <For each={changelogs()} fallback={<tr><td colspan="4" class="hint">暂无履历</td></tr>}>
                  {(log) => (
                    <tr>
                      <td><strong>{log.prefix}</strong></td>
                      <td class={log.action === "add" ? "pass" : "fail"}>{log.action_label}</td>
                      <td>{log.operator_name || "—"}</td>
                      <td>{new Date(log.created_at).toLocaleString()}</td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
          </section>
        </Show>

        <Show when={route().name === "detail"}>
          <section class="card">
            <div class="toolbar">
              <h2>刀补详情</h2>
              <button type="button" class="ghost" onClick={goHome}>
                返回总览
              </button>
            </div>
            <Show when={detail()} fallback={<p class="hint">{loading() ? "加载中…" : "未找到记录"}</p>}>
              {(d) => (
                <div class="detail-grid">
                  <p>编号：{d().id}</p>
                  <p>刀具：{d().tool_code}</p>
                  <p>字头：{d().prefix || "—"}</p>
                  <p>刀补 µm：{d().offset_um}</p>
                  <p>状态：{statusLabel[d().status] || d().status}</p>
                  <p class={d().verdict === "合格" ? "pass" : d().verdict === "超差" ? "fail" : ""}>
                    结论：{d().verdict || "—"}
                  </p>
                  <p>提交时间：{new Date(d().created_at).toLocaleString()}</p>
                  <p>
                    复核时间：
                    {d().reviewed_at ? new Date(d().reviewed_at).toLocaleString() : "—"}
                  </p>
                </div>
              )}
            </Show>
          </section>
        </Show>
      </Show>
    </div>
  );
}

export default App;
