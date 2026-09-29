import { createSignal, onMount, Show, For, createEffect } from "solid-js";
import {
  addPrefix,
  clearSession,
  createSubmission,
  fetchPrefixes,
  fetchPrefixHistory,
  fetchPrefixRule,
  fetchSubmission,
  fetchSubmissions,
  getUser,
  login,
  removePrefix,
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

const SAMPLE_WORDS = ["甲", "乙", "丙", "丁", "戊", "己", "庚"];

function readHash() {
  const raw = (location.hash || "#/").replace(/^#/, "") || "/";
  const dm = raw.match(/^\/detail\/(\d+)/);
  if (dm) return { name: "detail", id: Number(dm[1]) };
  if (raw === "/prefixes") return { name: "prefixes", id: null };
  return { name: "home", id: null };
}

function App() {
  const [user, setUser] = createSignal(getUser());
  const [rows, setRows] = createSignal([]);
  const [detail, setDetail] = createSignal(null);
  const [route, setRoute] = createSignal(readHash());
  const [error, setError] = createSignal("");
  const [loading, setLoading] = createSignal(false);

  const [loginUser, setLoginUser] = createSignal("machinist");
  const [loginPass, setLoginPass] = createSignal("machine123456");

  const [toolCode, setToolCode] = createSignal("");
  const [offsetUm, setOffsetUm] = createSignal("");

  // 字头台状态：rule 里的 reject_message/prefixes 全部取自后端，页面不自创口径
  const [prefixes, setPrefixes] = createSignal([]);
  const [prefixRows, setPrefixRows] = createSignal([]);
  const [rejectMessage, setRejectMessage] = createSignal("");
  const [history, setHistory] = createSignal([]);
  const [newPrefix, setNewPrefix] = createSignal("");

  function goHome() {
    location.hash = "#/";
  }

  function goDetail(id) {
    location.hash = `#/detail/${id}`;
  }

  function goPrefixes() {
    location.hash = "#/prefixes";
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

  async function loadRule() {
    const rule = await fetchPrefixRule();
    setPrefixes(rule.prefixes || []);
    setRejectMessage(rule.reject_message || "");
  }

  async function loadPrefixDesk() {
    setLoading(true);
    setError("");
    try {
      const [rule, list, log] = await Promise.all([
        fetchPrefixRule(),
        fetchPrefixes(),
        fetchPrefixHistory(),
      ]);
      setPrefixes(rule.prefixes || list.map((p) => p.prefix));
      setPrefixRows(list);
      setRejectMessage(rule.reject_message || "");
      setHistory(log);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  onMount(() => {
    const onHash = () => setRoute(readHash());
    window.addEventListener("hashchange", onHash);
    if (user()) {
      if (route().name === "detail") loadDetail(route().id);
      else if (route().name === "prefixes") loadPrefixDesk();
      else loadRows();
      loadRule().catch(() => {});
    }
    return () => window.removeEventListener("hashchange", onHash);
  });

  createEffect(() => {
    const r = route();
    if (!user()) return;
    if (r.name === "detail" && r.id) loadDetail(r.id);
    if (r.name === "home") loadRows();
    if (r.name === "prefixes") loadPrefixDesk();
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
      await Promise.all([loadRows(), loadRule()]);
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
    setHistory([]);
    goHome();
  }

  // 与后端同一口径：长字头优先的起笔匹配
  function matchPrefix(code) {
    const list = [...prefixes()].sort((a, b) => b.length - a.length);
    return list.find((p) => p && code.startsWith(p)) || "";
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    const code = toolCode().trim();
    if (!code) {
      setError("刀具编号不能为空");
      return;
    }
    // 页面预拦：规则口径取自后端（字头表 + 统一退回文案），直连仍由后端再拦
    if (!matchPrefix(code)) {
      setError(rejectMessage() || "刀号未以已登记字头起笔，已退回");
      return;
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
    const p = newPrefix().trim();
    if (!p) {
      setError("字头不能为空");
      return;
    }
    try {
      await addPrefix(p);
      setNewPrefix("");
      await loadPrefixDesk();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleRemovePrefix(p) {
    setError("");
    try {
      await removePrefix(p);
      await loadPrefixDesk();
    } catch (err) {
      setError(err.message);
    }
  }

  function goodSample() {
    const first = prefixes()[0];
    return first ? `${first}刀零一` : "";
  }

  function badSampleWord() {
    return SAMPLE_WORDS.find((w) => !prefixes().includes(w)) || "";
  }

  return (
    <div class="page">
      <header class="topbar">
        <div class="brand">
          <h1>数控刀补复核台</h1>
          <p class="hint">
            刀号必须以字头台登记过的字头起笔；刀补绝对值不超过十二微米判合格。后台认领进程用行锁跳过已占行领取待复核。
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
              href="#/prefixes"
              class={route().name === "prefixes" ? "active" : ""}
              onClick={(e) => {
                e.preventDefault();
                goPrefixes();
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
                当前已登记字头：
                {prefixes().length ? prefixes().join("、") : "（空，任何刀号都会被退回）"}
                ；刀号须以其中之一起笔。
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

        <Show when={route().name === "prefixes"}>
          <section class="card">
            <div class="toolbar">
              <h2>字头台 · 维护区</h2>
              <button type="button" class="ghost" onClick={loadPrefixDesk} disabled={loading()}>
                {loading() ? "刷新中…" : "刷新"}
              </button>
            </div>
            <Show when={user().can_write} fallback={<p class="hint">复核员只读：可查看字头表、退回样例与改动履历，不能增删字头。</p>}>
              <form onSubmit={handleAddPrefix} class="form inline">
                <label>
                  新字头
                  <input
                    placeholder="如 乙"
                    value={newPrefix()}
                    onInput={(e) => setNewPrefix(e.currentTarget.value)}
                    maxlength="16"
                  />
                </label>
                <button type="submit">登记字头</button>
              </form>
            </Show>
            <table>
              <thead>
                <tr>
                  <th>字头</th>
                  <th>登记时间</th>
                  <Show when={user().can_write}><th></th></Show>
                </tr>
              </thead>
              <tbody>
                <For each={prefixRows()}>
                  {(row) => (
                    <tr>
                      <td>{row.prefix}</td>
                      <td>{new Date(row.created_at).toLocaleString()}</td>
                      <Show when={user().can_write}>
                        <td>
                          <button type="button" class="ghost" onClick={() => handleRemovePrefix(row.prefix)}>
                            删除
                          </button>
                        </td>
                      </Show>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
            <Show when={!prefixes().length && !loading()}>
              <p class="hint">字头表为空：此时任何刀号提交都会被退回。</p>
            </Show>
            <p class="hint">删除字头不会改写已经收下的旧刀号，仅影响此后的新提交。</p>
          </section>

          <section class="card">
            <h2>退回样例</h2>
            <p class="hint">规则口径：{rejectMessage()}</p>
            <table>
              <thead>
                <tr>
                  <th>刀号样例</th>
                  <th>判定</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                <Show when={goodSample()}>
                  <tr>
                    <td>{goodSample()}</td>
                    <td class="pass">收下</td>
                    <td>以当前登记字头「{prefixes()[0]}」起笔</td>
                  </tr>
                </Show>
                <Show when={badSampleWord()}>
                  <tr>
                    <td>{badSampleWord()}刀零九</td>
                    <td class="fail">退回</td>
                    <td>字头「{badSampleWord()}」未登记；{rejectMessage()}</td>
                  </tr>
                </Show>
              </tbody>
            </table>
          </section>

          <section class="card">
            <h2>字头改动履历</h2>
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
                <For each={history()}>
                  {(h) => (
                    <tr>
                      <td>{h.prefix}</td>
                      <td class={h.action === "add" ? "pass" : "fail"}>{h.action_label}</td>
                      <td>{h.operator || "—"}</td>
                      <td>{new Date(h.created_at).toLocaleString()}</td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
            <Show when={!history().length && !loading()}>
              <p class="hint">暂无字头改动</p>
            </Show>
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
