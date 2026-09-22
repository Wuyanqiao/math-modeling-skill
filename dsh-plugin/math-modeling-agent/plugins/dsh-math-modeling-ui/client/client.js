window.__ModuleLoader__.load({
  id: 'dsh-math-modeling-ui',
  factory(require) {
    const React = require('react')
    const h = React.createElement
    const CHANNEL = '/math-modeling-ui'
    const names = { modeling: '建模', programming: '求解', paper: '论文' }
    const scopes = { full: '完整流程', modeling: '建模任务', programming: '求解任务', paper: '论文任务' }
    const statuses = { pass: '通过', fail: '未通过', blocked: '阻塞', pending: '待审', invalidated: '需复验', stale: '需复验', done: '完成', current: '进行中', inprogress: '进行中', skipped: '不适用' }
    const records = value => Array.isArray(value) ? value : Object.entries(value || {}).map(([id, item]) => ({ id, ...item }))
    const message = value => typeof value === 'string' ? value : value?.message || value?.text || value?.reason || JSON.stringify(value)
    const timestamp = value => value ? new Date(value).toLocaleString() : '时间未记录'
    const CSS = `
.mmwb{--paper:#f8f7f2;--ink:#202c2b;--muted:#65736e;--line:#dce1d9;--accent:#176f64;--warning:#985414;color:var(--ink);background:var(--paper);font-family:'Segoe UI','Microsoft YaHei',sans-serif;font-size:13px;line-height:1.6;box-sizing:border-box}
.mmwb *{box-sizing:border-box}.mmwb button{font:inherit;color:inherit;cursor:pointer}.mmwb button:disabled{cursor:wait;opacity:.55}.mmwb button:focus-visible,.mmwb summary:focus-visible{outline:3px solid #d8a83b;outline-offset:3px}
.mmwb-dock{pointer-events:auto;position:fixed;right:16px;top:16px;width:min(390px,calc(100vw - 32px));max-height:calc(100vh - 32px);overflow:auto;border:1px solid var(--line);border-top:4px solid var(--accent);border-radius:3px;box-shadow:0 10px 36px #162e2426;z-index:30}
.mmwb-dock.mmwb-closed{width:auto;max-width:calc(100vw - 32px)}.mmwb-head{padding:16px 18px 12px;border-bottom:1px solid var(--line)}.mmwb-kicker{font-family:Consolas,monospace;font-size:10px;letter-spacing:1.6px;text-transform:uppercase;color:var(--accent)}.mmwb-row{display:flex;align-items:center;justify-content:space-between;gap:12px}.mmwb h2{font-family:Georgia,'Songti SC','SimSun',serif;font-size:21px;line-height:1.35;margin:6px 0;overflow-wrap:anywhere}.mmwb h3{font-size:12px;letter-spacing:.4px;margin:0 0 10px}.mmwb p{margin:6px 0}.mmwb-muted{color:var(--muted);font-size:11px}.mmwb-btn{border:1px solid var(--line);border-radius:3px;padding:5px 10px;background:transparent;white-space:nowrap}.mmwb-btn:hover{background:#176f640c}.mmwb-btn-primary{background:var(--accent);color:#fff!important;border-color:var(--accent)}.mmwb-tabs{display:flex;padding:0 14px;border-bottom:1px solid var(--line)}.mmwb-tab{flex:1;background:none;border:0;border-bottom:2px solid transparent;padding:10px 4px;font-size:12px!important}.mmwb-tab[aria-selected=true]{border-color:var(--accent);font-weight:700;color:var(--accent)}.mmwb-content{padding:16px 18px}.mmwb-section{margin-bottom:20px}.mmwb-section:last-child{margin-bottom:0}.mmwb-warning{border-left:3px solid #cc9237;padding:10px 12px;background:#f4ebda;font-size:12px;margin-bottom:14px}.mmwb-error{border-left-color:#b54434;background:#fae9e4}.mmwb-success{border-left:3px solid var(--accent);padding:9px 12px;background:#e4eee7;margin-bottom:14px}.mmwb-list{list-style:none;margin:0;padding:0}.mmwb-list>li{padding:9px 0;border-bottom:1px solid var(--line)}.mmwb-list>li:last-child{border-bottom:0}.mmwb-badge{display:inline-block;border-radius:2px;padding:2px 6px;background:#e4e8e2;font-size:10px;white-space:nowrap}.mmwb-badge[data-status=pass],.mmwb-badge[data-status=done]{color:#176446;background:#dfece0}.mmwb-badge[data-status=fail],.mmwb-badge[data-status=blocked],.mmwb-badge[data-status=invalidated]{color:#873b22;background:#f2e1d2}.mmwb summary{cursor:pointer;overflow-wrap:anywhere}.mmwb details+details{margin-top:10px}.mmwb code,.mmwb pre{font-family:Consolas,'Cascadia Code',monospace;font-size:11px}.mmwb pre{margin:8px 0;padding:10px;background:#eaede6;border:1px solid var(--line);white-space:pre-wrap;overflow-wrap:anywhere;max-height:260px;overflow:auto}.mmwb-path{font-size:11px;color:var(--muted);overflow-wrap:anywhere}.mmwb-foot{padding:12px 18px;border-top:1px solid var(--line)}.mmwb-empty{color:var(--muted);padding:12px 0;font-size:12px}.mmwb-progress{height:3px;background:#dce2d7;margin-top:6px}.mmwb-progress>span{height:100%;display:block;background:var(--accent)}.mmwb-settings{max-width:580px;padding:20px;border:1px solid var(--line)}.mmwb-close{border:0;background:none;font-size:16px!important}.mmwb-preview{padding-top:12px;margin-top:12px;border-top:1px solid var(--line)}
@media(prefers-color-scheme:dark){.mmwb{--paper:#202925;--ink:#e5e9df;--muted:#a3b0a7;--line:#3d4840;--accent:#7bb7a1}.mmwb-warning{background:#463a28;color:#f0d6aa}.mmwb-error{background:#472d29}.mmwb-success{background:#293f32}.mmwb pre{background:#19211c}.mmwb-badge{background:#3d4840}.mmwb-btn-primary{color:#13251d!important}}
@media(prefers-reduced-motion:reduce){.mmwb *{scroll-behavior:auto!important}}
.mmwb summary>.mmwb-row{display:inline-flex;width:calc(100% - 16px)}
`
    function Badge({ status }) {
      const key = String(status || 'pending').toLowerCase()
      return h('span', { className: 'mmwb-badge', 'data-status': key }, statuses[key] || key)
    }
    function Section({ title, children }) { return h('section', { className: 'mmwb-section' }, h('h3', null, title), children) }
    function Empty({ children }) { return h('p', { className: 'mmwb-empty' }, children) }
    function useSession(ctx) {
      const store = ctx.sessions?.list
      const subscribe = React.useCallback(listener => {
        if (store?.subscribe) return store.subscribe(listener)
        const timer = setInterval(listener, 1000)
        return () => clearInterval(timer)
      }, [store])
      const snapshot = React.useCallback(() => {
        const value = store?.getSnapshot?.()
        return Object.values(value?.byId || {}).find(session => (session.retainedBy?.mainView || 0) > 0)?.id || value?.current || null
      }, [store])
      return React.useSyncExternalStore(subscribe, snapshot, () => null)
    }
    function Overview({ data }) {
      const blockers = data.blockers || []
      const steps = data.progress?.steps || []
      const gates = records(data.gates)
      return h(React.Fragment, null,
        data.stale ? h('p', { className: 'mmwb-warning' }, data.refreshNotice || '当前显示保存的快照。重新验证可检查产物变更。') : null,
        data.refreshError ? h('p', { className: 'mmwb-warning mmwb-error', role: 'alert' }, data.refreshError) : null,
        data.completed ? h('div', { className: 'mmwb-success' }, data.stale ? '上次验证已完成' : '当前任务验证完成', h('div', { className: 'mmwb-muted' }, timestamp(data.completedAt))) : null,
        h(Section, { title: '当前阻塞' }, blockers.length ? h('ul', { className: 'mmwb-list' }, blockers.map((item, index) => h('li', { key: index }, message(item)))) : h(Empty, null, data.completed ? '没有阻塞项。' : '尚无记录；以运行时验证结果为准。')),
        h(Section, { title: '阶段进度' }, h('ul', { className: 'mmwb-list' }, steps.map(step => {
          const task = data.progress?.tasks?.[step.key]
          return h('li', { key: step.key }, h('div', { className: 'mmwb-row' }, h('span', null, step.label || names[step.key]), h(Badge, { status: step.status })),
            task ? h('div', { className: 'mmwb-muted' }, `${task.done ?? 0} / ${task.total ?? 0} 项`, h('div', { className: 'mmwb-progress', role: 'progressbar', 'aria-label': `${step.label || step.key}任务进度`, 'aria-valuenow': task.pct || 0, 'aria-valuemin': 0, 'aria-valuemax': 100 }, h('span', { style: { width: `${Math.max(0, Math.min(100, task.pct || 0))}%` } }))) : null)
        }))),
        h(Section, { title: '审核门禁' }, gates.map(gate => h('details', { key: gate.id }, h('summary', null, h('span', { className: 'mmwb-row' }, h('span', null, `${gate.id} · ${gate.title || ''}`), h(Badge, { status: gate.status }))),
          gate.invalidation_reason ? h('p', { className: 'mmwb-warning' }, gate.invalidation_reason) : null,
          gate.receipt ? h(React.Fragment, null, h('p', { className: 'mmwb-muted' }, `审核来源：${gate.receipt.review_source || '未记录'}；身份为审计声明`), h('pre', null, JSON.stringify(gate.receipt, null, 2))) : h(Empty, null, '尚无审核回执。')))),
        data.progress?.nextAction ? h('p', { className: 'mmwb-muted' }, data.progress.nextAction) : null,
        h('details', null, h('summary', null, '运行能力'), h('pre', null, JSON.stringify(data.capabilities || {}, null, 2))))
    }
    function Evidence({ data, preview, openPreview, busy }) {
      return h(React.Fragment, null,
        h(Section, { title: '已登记产物' }, records(data.artifacts).length ? h('ul', { className: 'mmwb-list' }, records(data.artifacts).map(item => h('li', { key: item.id || item.path },
          h('div', { className: 'mmwb-row' }, h('span', null, `${item.kind || '文件'}${item.question ? ` · ${item.question}` : ''}`), h('button', { className: 'mmwb-btn', disabled: busy, onClick: () => openPreview(item.path), 'aria-label': `预览 ${item.path}` }, '预览')),
          h('div', { className: 'mmwb-path' }, item.path), h('div', { className: 'mmwb-muted' }, item.sha256 ? `SHA-256 ${item.sha256.slice(0, 16)}…` : '未记录哈希')))) : h(Empty, null, '用 mm_artifact_add 登记结果、图表或文档。')),
        preview ? h('div', { className: 'mmwb-preview', role: 'region', 'aria-label': '产物预览' }, h('h3', null, '文件预览'), h('pre', null, preview.content ?? JSON.stringify(preview, null, 2))) : null,
        h(Section, { title: '主张与证据' }, records(data.claims).length ? h('ul', { className: 'mmwb-list' }, records(data.claims).map(item => h('li', { key: item.id || item.claim_id }, h('p', null, item.text), h('div', { className: 'mmwb-path' }, (item.artifact_ids || []).join(' · ')), item.locator ? h('div', { className: 'mmwb-muted' }, item.locator) : null))) : h(Empty, null, '用 mm_claim_add 关联主张与产物。')),
        h('details', null, h('summary', null, '审核任务与检查点'), h('pre', null, JSON.stringify({ review_tasks: data.review_tasks, checkpoints: data.checkpoints }, null, 2))))
    }
    function Runs({ data, preview, openLog, busy }) {
      const runs = records(data.runs).slice(-20).reverse()
      return h(React.Fragment, null,
        h(Section, { title: '运行记录' }, runs.length ? runs.map(run => h('details', { key: run.id || run.run_id }, h('summary', null, h('span', { className: 'mmwb-row' }, h('code', null, (run.argv || []).join(' ') || run.id), h('span', { className: 'mmwb-badge' }, `退出码 ${run.exit_code ?? run.exitCode ?? '未知'}`))),
          h('div', { className: 'mmwb-row' }, ['stdout', 'stderr'].map(stream => h('button', { key: stream, className: 'mmwb-btn', disabled: busy, onClick: () => openLog(run.run_id || run.id, stream) }, `读取 ${stream}`))),
          h('pre', null, JSON.stringify(run, null, 2)))) : h(Empty, null, '通过 mm_run 执行命令后，真实日志会显示在这里。')),
        preview ? h('section', { className: 'mmwb-preview', 'aria-label': '运行日志' }, h('h3', null, '运行日志'), preview.truncated ? h('p', { className: 'mmwb-warning' }, '日志过长，当前显示受限预览。') : null, h('pre', null, preview.content || '（空日志）')) : null,
        h(Section, { title: '最近活动' }, h('ul', { className: 'mmwb-list' }, (data.ledgerTail || []).slice().reverse().map((entry, index) => h('li', { key: `${entry.at}-${index}` }, h('div', null, entry.event), h('div', { className: 'mmwb-muted' }, timestamp(entry.at)), entry.detail ? h('pre', null, typeof entry.detail === 'string' ? entry.detail : JSON.stringify(entry.detail, null, 2)) : null)))))
    }
    function Dock({ ctx, rpc }) {
      const sid = useSession(ctx)
      const [data, setData] = React.useState(null)
      const [error, setError] = React.useState(null)
      const [open, setOpen] = React.useState(false)
      const [tab, setTab] = React.useState('overview')
      const [busy, setBusy] = React.useState(false)
      const [preview, setPreview] = React.useState(null)
      const [logPreview, setLogPreview] = React.useState(null)
      const sequence = React.useRef(0)
      const previewSequence = React.useRef(0)
      const refresh = React.useCallback(async (verify = false) => {
        if (!sid) return
        const request = ++sequence.current
        if (verify) setBusy(true)
        try {
          const result = await rpc('mm.state', { sessionId: sid, refresh: verify })
          if (sequence.current !== request) return
          if (!result.ok) throw new Error(result.error?.message || '无法读取项目')
          setData(result.value); setError(null)
        } catch (error) { if (sequence.current === request) setError(String(error.message || error)) }
        finally { if (sequence.current === request) setBusy(false) }
      }, [sid, rpc])
      React.useEffect(() => {
        setData(null); setError(null); setPreview(null); setLogPreview(null); setBusy(false)
        refresh()
        const timer = setInterval(() => { if (document.visibilityState !== 'hidden') refresh() }, 10000)
        const changed = () => refresh()
        window.addEventListener('mmwb-settings-change', changed)
        return () => { clearInterval(timer); window.removeEventListener('mmwb-settings-change', changed); sequence.current++; previewSequence.current++ }
      }, [refresh])
      async function openPreview(path) {
        const request = ++previewSequence.current
        setBusy(true)
        try {
          const result = await rpc('mm.artifact', { sessionId: sid, path })
          if (previewSequence.current !== request) return
          if (!result.ok) throw new Error(result.error?.message || '无法预览')
          setPreview(result.value); setError(null)
        } catch (error) { if (previewSequence.current === request) setError(String(error.message || error)) }
        finally { if (previewSequence.current === request) setBusy(false) }
      }
      async function openLog(runId, stream) {
        const request = ++previewSequence.current
        setBusy(true)
        try {
          const result = await rpc('mm.runLog', { sessionId: sid, run_id: runId, stream })
          if (previewSequence.current !== request) return
          if (!result.ok) throw new Error(result.error?.message || '无法读取日志')
          setLogPreview(result.value); setError(null)
        } catch (error) { if (previewSequence.current === request) setError(String(error.message || error)) }
        finally { if (previewSequence.current === request) setBusy(false) }
      }
      if (!sid || data?.hidden || (!data && !error)) return null
      const title = data?.project?.title || '数学建模工作台'
      const tabs = [['overview', '项目'], ['evidence', '证据'], ['runs', '运行']]
      return h('aside', { className: `mmwb mmwb-dock${open ? '' : ' mmwb-closed'}`, 'aria-label': '数学建模项目状态' },
        h('header', { className: 'mmwb-head' }, h('div', { className: 'mmwb-row' }, h('div', null, h('div', { className: 'mmwb-kicker' }, 'MODEL / VERIFY / WRITE'), open ? h('h2', null, title) : h('span', null, title)), h('button', { className: 'mmwb-btn', onClick: () => setOpen(value => !value), 'aria-expanded': open, 'aria-label': open ? '收起项目看板' : '展开项目看板' }, open ? '收起' : '展开')),
          open ? h('div', { className: 'mmwb-muted' }, `${data?.project?.competition || '研究项目'} · ${scopes[data?.project?.scope] || '任务范围待定'} · ${names[data?.currentPhase] || ''}`) : null),
        open ? h(React.Fragment, null,
          h('div', { className: 'mmwb-tabs', role: 'tablist', 'aria-label': '项目详情' }, tabs.map(([id, label], index) => h('button', {
            key: id, id: `mmwb-tab-${id}`, className: 'mmwb-tab', role: 'tab', tabIndex: tab === id ? 0 : -1,
            'aria-selected': tab === id, 'aria-controls': `mmwb-panel-${id}`, onClick: () => setTab(id),
            onKeyDown: event => {
              const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length : null
              if (next === null) return
              event.preventDefault(); setTab(tabs[next][0]); event.currentTarget.parentElement.children[next].focus()
            },
          }, label))),
          h('div', { className: 'mmwb-content', id: `mmwb-panel-${tab}`, role: 'tabpanel', 'aria-labelledby': `mmwb-tab-${tab}`, tabIndex: 0 }, error ? h('p', { className: 'mmwb-warning mmwb-error', role: 'alert' }, error) : null,
            data?.initialized ? tab === 'overview' ? h(Overview, { data }) : tab === 'evidence' ? h(Evidence, { data, preview, openPreview, busy }) : h(Runs, { data, preview: logPreview, openLog, busy }) : null),
          h('footer', { className: 'mmwb-foot' }, h('div', { className: 'mmwb-row' }, h('span', { className: 'mmwb-muted' }, data?.stale ? '已保存快照' : '运行时已核验'), h('button', { className: 'mmwb-btn mmwb-btn-primary', disabled: busy, onClick: () => refresh(true) }, busy ? '正在读取…' : '重新验证')), h('div', { className: 'mmwb-muted' }, timestamp(data?.snapshotAt || data?.updated_at)))) : null)
    }
    function Settings({ rpc }) {
      const [enabled, setEnabled] = React.useState(null)
      const [busy, setBusy] = React.useState(false)
      const [error, setError] = React.useState(null)
      React.useEffect(() => {
        let active = true
        rpc('mm.getEnabled', {}).then(result => { if (!active) return; if (!result.ok) throw new Error(result.error?.message); setEnabled(result.value.enabled) }).catch(error => { if (active) setError(String(error.message || error)) })
        return () => { active = false }
      }, [rpc])
      async function toggle() {
        setBusy(true)
        try { const result = await rpc('mm.setEnabled', { enabled: !enabled }); if (!result.ok) throw new Error(result.error?.message); setEnabled(result.value.enabled); setError(null); window.dispatchEvent(new Event('mmwb-settings-change')) }
        catch (error) { setError(String(error.message || error)) }
        finally { setBusy(false) }
      }
      return h('section', { className: 'mmwb mmwb-settings' }, h('div', { className: 'mmwb-row' }, h('div', null, h('h3', null, '数学建模项目看板'), h('p', { className: 'mmwb-muted' }, '对已初始化的项目显示状态、证据与运行记录；支持自定义预设名称。')), h('button', { className: 'mmwb-btn', role: 'switch', 'aria-checked': enabled === true, disabled: busy || enabled === null, onClick: toggle }, enabled ? '已开启' : '已关闭')), error ? h('p', { role: 'alert', className: 'mmwb-warning mmwb-error' }, error) : null)
    }
    function apply(ctx) {
      const tag = document.createElement('style')
      tag.dataset.mmui = 'dsh-math-modeling-ui'; tag.textContent = CSS; document.head.append(tag)
      ctx.on?.('dispose', () => tag.remove())
      const rpc = (endpoint, payload) => ctx.connection.rpc.call(CHANNEL, endpoint, payload)
      ctx.slots.inject('shell.overlay', () => ctx.slots.register({ name: 'shell.overlay', id: 'mathmodeling-board', order: 50 }, () => h(Dock, { ctx, rpc })))
      ctx.slots.inject('settings.section', () => ctx.slots.register({ name: 'settings.section', id: 'math-modeling', order: 11, label: () => '数学建模', inject: () => ({ rpc }) }, Settings))
    }
    return { name: 'dsh-math-modeling-ui', inject: ['slots', 'connection', 'sessions'], apply }
  },
})
