window.__ModuleLoader__.load({
  id: 'dsh-math-modeling-ui',
  factory(require) {
    const React = require('react')
    const h = React.createElement
    const CHANNEL = '/math-modeling-ui'
    const names = { modeling: '建模', programming: '求解', paper: '论文' }
    const scopes = { full: '完整流程', modeling: '建模任务', programming: '求解任务', paper: '论文任务' }
    const statuses = { pass: '通过', fail: '未通过', blocked: '阻塞', pending: '待审', invalidated: '需复验', stale: '需复验', done: '完成', current: '进行中', inprogress: '进行中', skipped: '不适用' }
    const gateNames = { M1: '模型审查', P1: '最小求解', P2: '结果审查', W1: '证据大纲', W2: '论文验收' }
    const records = value => Array.isArray(value) ? value : Object.entries(value || {}).map(([id, item]) => ({ id, ...item }))
    const message = value => typeof value === 'string' ? value : value?.message || value?.text || value?.reason || JSON.stringify(value)
    const timestamp = value => value ? new Date(value).toLocaleString() : '时间未记录'
    const CSS = `
.mmwb{--paper:var(--dsw-alias-bg-layer-1,#fff);--ink:var(--dsw-alias-label-primary,#17191c);--muted:var(--dsw-alias-label-secondary,#72777f);--line:var(--dsw-alias-border-l3,#e7e8eb);--hover:var(--dsw-alias-interactive-bg-hover,#f1f2f4);--accent:var(--dsw-alias-link,#4176e6);--focus:var(--dsw-alias-brand-primary,#0f1115);--code:var(--dsw-alias-bg-layer-2,#f7f8fa);--good:var(--dsw-alias-state-success-primary,#32835b);--bad:var(--dsw-alias-state-error-primary,#c45555);--thumb:var(--dsh-scrollbar-thumb,#b9bec666);color:var(--ink);background:var(--paper);font-family:var(--dsw-font-family,inherit);font-size:var(--dsh-content-font-size-secondary,13px);line-height:1.55;box-sizing:border-box}
body[data-ds-dark-theme] .mmwb{--paper:var(--dsw-alias-bg-layer-1,#1b1b1d);--ink:var(--dsw-alias-label-primary,#ebebed);--muted:var(--dsw-alias-label-secondary,#a0a0a7);--line:var(--dsw-alias-border-l3,#38383d);--hover:var(--dsw-alias-interactive-bg-hover,#303034);--accent:var(--dsw-alias-link,#7b9aef);--focus:var(--dsw-alias-brand-primary,#ebebed);--code:var(--dsw-alias-bg-layer-2,#242427);--good:var(--dsw-alias-state-success-primary,#88c5a4);--bad:var(--dsw-alias-state-error-primary,#ef9494);--thumb:var(--dsh-scrollbar-thumb,#a5a5ae66)}
.mmwb *{box-sizing:border-box}
.mmwb button{font:inherit;color:inherit;cursor:pointer}
.mmwb button:disabled{opacity:.4;cursor:not-allowed}
.mmwb button:focus-visible,.mmwb summary:focus-visible,.mmwb [tabindex]:focus-visible{outline:2px solid var(--focus);outline-offset:-2px}
.mmwb svg{flex:none}
.mmwb p{margin:6px 0}
.mmwb h2,.mmwb h3{font:inherit;margin:0}
.mmwb-panel{width:100%;height:100%;min-width:0;min-height:0;display:flex;flex-direction:column;overflow:hidden}
.mmwb-head{padding:18px 18px 10px;flex:none}
.mmwb-heading{flex:1;min-width:0}
.mmwb h2{font-size:var(--dsh-content-font-size,14px);font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mmwb-meta{color:var(--muted);font-size:12px;margin-top:5px}
.mmwb-icon-btn{width:28px;height:28px;padding:6px;border:0;border-radius:28px;background:transparent;display:inline-flex;align-items:center;justify-content:center;flex:none}
.mmwb-icon-btn:hover:not(:disabled),.mmwb-btn:hover:not(:disabled){background:var(--hover)}
.mmwb-tabs{display:flex;flex:none;margin:0 16px 16px;padding:3px;gap:2px;border-radius:9px;background:var(--hover)}
.mmwb-tab{flex:1;height:28px;border:0;border-radius:7px;background:transparent;padding:0 8px;color:var(--muted)!important;font-size:13px!important;line-height:20px;font-weight:500;white-space:nowrap}
.mmwb-tab:hover{color:var(--ink)!important}
.mmwb-tab[aria-selected=true]{background:var(--paper);color:var(--ink)!important;box-shadow:var(--dsw-elevation-soft,0 1px 3px #0f111510)}
.mmwb-content{flex:1;min-height:0;min-width:0;overflow:auto;padding:0 16px 16px}
.mmwb-scroll{scrollbar-width:thin;scrollbar-color:transparent transparent}
.mmwb-scroll:hover,.mmwb-scroll[data-scrolling=true]{scrollbar-color:var(--thumb) transparent}
.mmwb-scroll::-webkit-scrollbar{width:var(--dsh-scrollbar-width,5px);height:var(--dsh-scrollbar-width,5px)}
.mmwb-scroll::-webkit-scrollbar-corner,.mmwb-scroll::-webkit-scrollbar-track{background:transparent}
.mmwb-scroll::-webkit-scrollbar-thumb{background:transparent;border:0;border-radius:999px;corner-shape:round}
.mmwb-scroll:hover::-webkit-scrollbar-thumb,.mmwb-scroll[data-scrolling=true]::-webkit-scrollbar-thumb{background-color:var(--thumb)}
.mmwb-scroll::-webkit-scrollbar-thumb:hover{background-color:var(--dsh-scrollbar-thumb-hover,var(--muted))}
.mmwb-section{margin:0 0 12px;border:.5px solid var(--line);border-radius:12px}
.mmwb-section:last-child{margin-bottom:0}
.mmwb-section>summary{display:flex;align-items:center;gap:8px;min-height:40px;padding:10px 12px;list-style:none;font-size:13px;font-weight:500;cursor:pointer;user-select:none;border-radius:12px}
.mmwb-section>summary::-webkit-details-marker{display:none}
.mmwb-section>summary:hover{background:var(--hover)}
.mmwb-chevron{color:var(--muted);transform:rotate(-90deg)}
.mmwb-section[open]>summary .mmwb-chevron{transform:rotate(0)}
.mmwb-section-body{padding:0 12px 12px}
.mmwb-list{list-style:none;margin:0;padding:0}
.mmwb-list>li{padding:8px 0}
.mmwb-list>li+li{border-top:.5px solid var(--line)}
.mmwb-row{display:flex;align-items:center;justify-content:space-between;gap:10px;min-width:0}
.mmwb-row>span:first-child{min-width:0}
.mmwb-muted,.mmwb-path{color:var(--muted);font-size:12px}
.mmwb-path,.mmwb-checkpoint-name{overflow-wrap:anywhere}
.mmwb-badge{display:inline-flex;gap:6px;align-items:center;color:var(--muted);font-size:12px;white-space:nowrap;flex:none}
.mmwb-badge:before{content:'';width:5px;height:5px;border-radius:50%;background:currentColor}
.mmwb-badge[data-status=pass],.mmwb-badge[data-status=done]{color:var(--good)}
.mmwb-badge[data-status=fail],.mmwb-badge[data-status=blocked],.mmwb-badge[data-status=invalidated]{color:var(--bad)}
.mmwb-badge[data-status=current]{color:var(--accent)}
.mmwb-counts{display:flex;gap:14px;padding:0 18px 14px;color:var(--muted);font-size:12px}
.mmwb-counts strong{font-weight:500;color:var(--ink);padding-right:5px}
.mmwb-warning,.mmwb-error,.mmwb-success{padding:10px 12px;margin:8px 0;border:.5px solid var(--line);border-radius:10px;background:var(--code);font-size:12px;overflow-wrap:anywhere}
.mmwb-error{color:var(--bad)}
.mmwb-success{color:var(--good)}
.mmwb-notice{margin:8px 0}
.mmwb-empty{color:var(--muted);font-size:12px;padding:5px 0}
.mmwb-progress{height:3px;border-radius:3px;background:var(--hover);margin-top:8px;overflow:hidden}
.mmwb-progress>span{display:block;height:100%;background:var(--accent);border-radius:3px}
.mmwb-btn{display:inline-flex;align-items:center;justify-content:center;background:transparent;border:.5px solid var(--line);border-radius:18px;padding:4px 12px;min-height:32px;white-space:nowrap}
.mmwb-btn-danger{color:var(--bad)!important}
.mmwb code,.mmwb pre{font-family:var(--ds-font-family-code,Consolas),monospace;font-size:12px;line-height:1.6}
.mmwb pre{margin:8px 0 0;padding:12px;border-radius:10px;background:var(--code);white-space:pre;max-height:240px;overflow:auto}
.mmwb-preview{border:.5px solid var(--line);border-radius:12px;padding:12px;margin:12px 0}
.mmwb-preview h3{font-size:13px;font-weight:500;margin-bottom:8px}
.mmwb details>summary{cursor:pointer;overflow-wrap:anywhere}
.mmwb details:not(.mmwb-section)>summary{padding:8px 0}
.mmwb details:not(.mmwb-section)>summary:hover{color:var(--accent)}
.mmwb summary>.mmwb-row{display:inline-flex;width:calc(100% - 16px);vertical-align:middle}
.mmwb summary code{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.mmwb-foot{display:flex;align-items:center;justify-content:space-between;gap:8px;flex:none;padding:9px 18px;color:var(--muted);font-size:11px;min-height:34px;border-top:.5px solid var(--line)}
.mmwb-foot time{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mmwb-actions{display:flex;gap:8px;align-items:center;margin-top:10px}
.mmwb-settings{padding:16px;max-width:580px}
.mmwb-guide{width:380px;max-width:100%;min-height:56px;display:flex;align-items:center;gap:14px;padding:14px 20px;border:.5px solid var(--line);border-radius:24px;text-align:left;cursor:pointer}
.mmwb-guide:hover{background:var(--hover)}
.mmwb-guide>svg{color:var(--muted)}
.mmwb-guide>span{font-size:14px;line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mmwb-spinner{animation:mmwb-spin 1s linear infinite}
@keyframes mmwb-spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.mmwb-spinner{animation:none}}
`
    function Badge({ status }) {
      const key = String(status || 'pending').toLowerCase()
      return h('span', { className: 'mmwb-badge', 'data-status': key }, statuses[key] || key)
    }
    function Section({ title, children, open = true }) { return h('details', { className: 'mmwb-section', open }, h('summary', null, h(Icon, { name: 'chevron', size: 12, className: 'mmwb-chevron' }), title), h('div', { className: 'mmwb-section-body' }, children)) }
    function Empty({ children }) { return h('p', { className: 'mmwb-empty' }, children) }
    function Icon({ name, size = 16, className }) {
      const paths = {
        board: 'M3 3h18v18H3z M3 9h18 M9 9v12 M13 13h4 M13 17h4',
        refresh: 'M20 7v5h-5 M4 17v-5h5 M6.1 6.1A8 8 0 0 1 20 12 M4 12a8 8 0 0 0 13.9 5.9',
        chevron: 'm6 9 6 6 6-6',
        eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12 M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
        restore: 'M3 4v6h6 M3 10a9 9 0 1 1 1 8 M12 7v5l3 2',
      }
      return h('svg', { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true, className }, h('path', { d: paths[name] || paths.board }))
    }
    function useScrollbars(ref) {
      React.useEffect(() => {
        const element = ref.current
        if (!element) return
        const timers = new Map()
        const reveal = event => {
          const target = event.target
          if (!target.classList?.contains('mmwb-scroll')) return
          target.dataset.scrolling = 'true'
          clearTimeout(timers.get(target))
          timers.set(target, setTimeout(() => { delete target.dataset.scrolling; timers.delete(target) }, 900))
        }
        element.addEventListener('scroll', reveal, { capture: true, passive: true })
        return () => { element.removeEventListener('scroll', reveal, true); for (const timer of timers.values()) clearTimeout(timer) }
      }, [ref])
    }
    function GuideEntry({ sessionId, useTabInfo, rpc }) {
      const { tab } = useTabInfo()
      const [project, setProject] = React.useState(null)
      React.useEffect(() => {
        if (!tab.visible || !sessionId) return
        let live = true
        let pending = false
        const read = async () => {
          if (pending || document.visibilityState === 'hidden') return
          pending = true
          try {
            const result = await rpc('mm.state', { sessionId, refresh: false })
            if (live) setProject({ sessionId, visible: result.ok && result.value?.initialized && !result.value?.hidden })
          } catch { if (live) setProject({ sessionId, visible: false }) }
          finally { pending = false }
        }
        read()
        const timer = setInterval(read, 2000)
        window.addEventListener('mmwb-settings-change', read)
        window.addEventListener('focus', read)
        document.addEventListener('visibilitychange', read)
        return () => {
          live = false; clearInterval(timer)
          window.removeEventListener('mmwb-settings-change', read)
          window.removeEventListener('focus', read)
          document.removeEventListener('visibilitychange', read)
        }
      }, [sessionId, tab.visible, rpc])
      if (project?.sessionId !== sessionId || !project.visible) return null
      return h('button', { type: 'button', className: 'mmwb mmwb-guide', 'data-sidebar-right-guide-entry': 'math-modeling', title: '数学建模 Workbench — 查看当前项目的阶段、证据、运行与快照', onClick: () => tab.actions.openTab('math-modeling', { replaceTab: true }) },
        h(Icon, { name: 'board', size: 24 }), h('span', null, '数学建模 Workbench'))
    }
    function Overview({ data }) {
      const blockers = data.blockers || []
      const steps = data.progress?.steps || []
      const gates = records(data.gates)
      return h(React.Fragment, null,
        data.refreshError ? h('p', { className: 'mmwb-warning mmwb-error', role: 'alert' }, data.refreshError) : null,
        data.completed ? h('div', { className: 'mmwb-success' }, data.stale ? '上次验证已完成' : '当前任务验证完成', h('div', { className: 'mmwb-muted' }, timestamp(data.completedAt))) : null,
        h(Section, { title: '当前阻塞' }, blockers.length ? h('ul', { className: 'mmwb-list' }, blockers.map((item, index) => h('li', { key: index }, message(item)))) : h(Empty, null, data.completed ? '无阻塞项' : '无阻塞记录')),
        h(Section, { title: '阶段进度' }, h('ul', { className: 'mmwb-list' }, steps.map(step => {
          const task = data.progress?.tasks?.[step.key]
          return h('li', { key: step.key }, h('div', { className: 'mmwb-row' }, h('span', null, step.label || names[step.key]), h(Badge, { status: step.status })),
            task ? h('div', { className: 'mmwb-muted' }, `${task.done ?? 0} / ${task.total ?? 0} 项`, h('div', { className: 'mmwb-progress', role: 'progressbar', 'aria-label': `${step.label || step.key}任务进度`, 'aria-valuenow': task.pct || 0, 'aria-valuemin': 0, 'aria-valuemax': 100 }, h('span', { style: { width: `${Math.max(0, Math.min(100, task.pct || 0))}%` } }))) : null)
        }))),
        h(Section, { title: '审核门禁' }, gates.map(gate => h('details', { key: gate.id }, h('summary', null, h('span', { className: 'mmwb-row' }, h('span', null, `${gate.id} · ${gate.title || gateNames[gate.id] || '审查'}`), h(Badge, { status: gate.status }))),
          gate.invalidation_reason ? h('p', { className: 'mmwb-warning' }, gate.invalidation_reason) : null,
          gate.receipt ? h(React.Fragment, null, h('p', { className: 'mmwb-muted' }, `审核来源：${gate.receipt.review_source || '未记录'}；身份为审计声明`), h('pre', { className: 'mmwb-scroll', tabIndex: 0 }, JSON.stringify(gate.receipt, null, 2))) : h(Empty, null, '暂无回执')))),
        data.progress?.nextAction ? h('p', { className: 'mmwb-muted' }, data.progress.nextAction) : null,
        h(Section, { title: '运行能力', open: false }, h('pre', { className: 'mmwb-scroll', tabIndex: 0 }, JSON.stringify(data.capabilities || {}, null, 2))))
    }
    function Evidence({ data, preview, openPreview, busy }) {
      return h(React.Fragment, null,
        h(Section, { title: '已登记产物' }, records(data.artifacts).length ? h('ul', { className: 'mmwb-list' }, records(data.artifacts).map(item => h('li', { key: item.id || item.path },
          h('div', { className: 'mmwb-row' }, h('span', null, `${item.kind || '文件'}${item.question ? ` · ${item.question}` : ''}`), h('button', { className: 'mmwb-icon-btn', disabled: busy, title: '预览 — 读取已登记产物', onClick: () => openPreview(item.path), 'aria-label': `预览 ${item.path}` }, h(Icon, { name: 'eye' }))),
          h('div', { className: 'mmwb-path' }, item.path), h('div', { className: 'mmwb-muted' }, item.sha256 ? `SHA-256 ${item.sha256.slice(0, 16)}…` : '未记录哈希')))) : h(Empty, null, '暂无产物')),
        preview ? h('div', { className: 'mmwb-preview', role: 'region', 'aria-label': '产物预览' }, h('h3', null, '文件预览'), h('pre', { className: 'mmwb-scroll', tabIndex: 0 }, preview.content ?? JSON.stringify(preview, null, 2))) : null,
        h(Section, { title: '主张与证据' }, records(data.claims).length ? h('ul', { className: 'mmwb-list' }, records(data.claims).map(item => h('li', { key: item.id || item.claim_id }, h('p', null, item.text), h('div', { className: 'mmwb-path' }, (item.artifact_ids || []).join(' · ')), item.locator ? h('div', { className: 'mmwb-muted' }, item.locator) : null))) : h(Empty, null, '暂无主张')),
        h(Section, { title: '审核任务', open: false }, h('pre', { className: 'mmwb-scroll', tabIndex: 0 }, JSON.stringify(data.review_tasks || {}, null, 2))))
    }
    function Checkpoints({ data, busy, preview, notice, error, create, previewRestore, confirmRestore, cancelRestore }) {
      const checkpoints = records(data.checkpoints).slice().reverse()
      const operations = { add: '新增 (add)', replace: '替换 (replace)', remove: '删除 (remove)' }
      return h(Section, { title: '项目快照' },
        h('button', { className: 'mmwb-btn', disabled: busy, title: '创建快照 — 保存项目文件与工作状态', onClick: create }, '创建快照'),
        notice ? h('p', { className: 'mmwb-success', role: 'status' }, notice) : null,
        error ? h('p', { className: 'mmwb-warning mmwb-error', role: 'alert' }, error) : null,
        checkpoints.length ? h('ul', { className: 'mmwb-list' }, checkpoints.map(item => h('li', { key: item.checkpoint_id },
          h('div', { className: 'mmwb-checkpoint-name' }, item.name || item.checkpoint_id),
          h('div', { className: 'mmwb-muted' }, timestamp(item.created_at)),
          h('div', { className: 'mmwb-row' }, h('span', { className: 'mmwb-badge', 'data-status': item.completed_when_created ? 'pass' : 'pending' }, item.completed_when_created ? '创建时已验收' : '创建时未验收'),
            h('button', { className: 'mmwb-icon-btn', disabled: busy, 'aria-label': `预览恢复 ${item.name || item.checkpoint_id}`, title: '预览恢复 — 查看变更清单，确认前不改写文件', onClick: () => previewRestore(item.checkpoint_id) }, h(Icon, { name: 'restore' })))))) : h(Empty, null, '暂无快照'),
        preview ? h('section', { className: 'mmwb-preview', 'aria-label': '恢复预览' },
          h('h3', null, '恢复变更清单'),
          h('p', { className: 'mmwb-checkpoint-name' }, checkpoints.find(item => item.checkpoint_id === preview.checkpoint_id)?.name || preview.checkpoint_id),
          preview.changes.length ? h('ul', { className: 'mmwb-list' }, preview.changes.map(change => h('li', { key: `${change.operation}:${change.path}` },
            h('span', { className: 'mmwb-badge' }, operations[change.operation] || change.operation), ' ', h('span', { className: 'mmwb-path' }, change.path)))) : h('p', null, '文件内容没有变化；确认后仍会恢复工作状态。'),
          h('p', { className: 'mmwb-warning' }, '将改写上述文件。恢复前自动备份，恢复后需重新验收。'),
          h('div', { className: 'mmwb-actions' }, h('button', { className: 'mmwb-btn mmwb-btn-danger', disabled: busy, title: '确认恢复 — 应用当前预览的文件与状态变更', onClick: confirmRestore }, '确认恢复'), h('button', { className: 'mmwb-btn', disabled: busy, title: '取消恢复 — 放弃当前预览', onClick: cancelRestore }, '取消恢复'))) : null)
    }
    function Runs({ data, preview, openLog, busy }) {
      const runs = records(data.runs).slice(-20).reverse()
      return h(React.Fragment, null,
        h(Section, { title: '运行记录' }, runs.length ? runs.map(run => h('details', { key: run.id || run.run_id }, h('summary', null, h('span', { className: 'mmwb-row' }, h('code', null, (run.argv || []).join(' ') || run.id), h('span', { className: 'mmwb-badge' }, `退出码 ${run.exit_code ?? run.exitCode ?? '未知'}`))),
          h('div', { className: 'mmwb-row' }, ['stdout', 'stderr'].map(stream => h('button', { key: stream, className: 'mmwb-btn', disabled: busy, title: `读取 ${stream} — 查看本次运行原始日志`, onClick: () => openLog(run.run_id || run.id, stream) }, `读取 ${stream}`))),
          h('pre', { className: 'mmwb-scroll', tabIndex: 0 }, JSON.stringify(run, null, 2)))) : h(Empty, null, '暂无运行')),
        preview ? h('section', { className: 'mmwb-preview', 'aria-label': '运行日志' }, h('h3', null, '运行日志'), preview.truncated ? h('p', { className: 'mmwb-warning' }, '日志过长，当前显示受限预览。') : null, h('pre', { className: 'mmwb-scroll', tabIndex: 0 }, preview.content || '（空日志）')) : null,
        h(Section, { title: '最近活动' }, h('ul', { className: 'mmwb-list' }, (data.ledgerTail || []).slice().reverse().map((entry, index) => h('li', { key: `${entry.at}-${index}` }, h('div', null, entry.event), h('div', { className: 'mmwb-muted' }, timestamp(entry.at)), entry.detail ? h('pre', { className: 'mmwb-scroll', tabIndex: 0 }, typeof entry.detail === 'string' ? entry.detail : JSON.stringify(entry.detail, null, 2)) : null)))))
    }
    function Workbench({ sessionId: sid, useTabInfo, rpc }) {
      const { tab: hostTab } = useTabInfo()
      const root = React.useRef(null)
      const instanceId = React.useId()
      useScrollbars(root)
      const [snapshot, setSnapshot] = React.useState(null)
      const data = snapshot?.sessionId === sid ? snapshot.data : null
      const [error, setError] = React.useState(null)
      const [tab, setTab] = React.useState('overview')
      const [busy, setBusy] = React.useState(false)
      const [preview, setPreview] = React.useState(null)
      const [logPreview, setLogPreview] = React.useState(null)
      const [restorePreview, setRestorePreview] = React.useState(null)
      const [checkpointBusy, setCheckpointBusy] = React.useState(false)
      const [checkpointNotice, setCheckpointNotice] = React.useState(null)
      const [checkpointError, setCheckpointError] = React.useState(null)
      const sequence = React.useRef(0)
      const statePending = React.useRef(false)
      const previewSequence = React.useRef(0)
      const checkpointSequence = React.useRef(0)
      const projectIdentity = React.useRef(null)
      const currentSession = React.useRef(sid)
      currentSession.current = sid
      const clearOperations = React.useCallback(() => {
        previewSequence.current++; checkpointSequence.current++
        setPreview(null); setLogPreview(null); setRestorePreview(null)
        setCheckpointNotice(null); setCheckpointError(null); setCheckpointBusy(false); setBusy(false)
      }, [])
      const refresh = React.useCallback(async (verify = false, forceRead = false) => {
        if (!sid || (!verify && !forceRead && statePending.current)) return
        const request = ++sequence.current
        statePending.current = true
        if (verify) { setBusy(true); setRestorePreview(null) }
        try {
          const result = await rpc('mm.state', { sessionId: sid, refresh: verify })
          if (sequence.current !== request || currentSession.current !== sid) return
          if (!result.ok) throw new Error(result.error?.message || '无法读取项目')
          const identity = result.value?.initialized && !result.value.hidden ? JSON.stringify([sid, result.value.project?.project_id, result.value.project?.projectRoot]) : null
          if (projectIdentity.current !== identity) { clearOperations(); projectIdentity.current = identity }
          setSnapshot({ sessionId: sid, data: result.value }); setError(null)
        } catch (error) { if (sequence.current === request && currentSession.current === sid) setError(String(error.message || error)) }
        finally { if (sequence.current === request && currentSession.current === sid) { statePending.current = false; if (verify) setBusy(false) } }
      }, [sid, rpc, clearOperations])
      React.useEffect(() => {
        statePending.current = false
        setError(null); setPreview(null); setLogPreview(null); setBusy(false)
        setRestorePreview(null); setCheckpointBusy(false); setCheckpointNotice(null); setCheckpointError(null)
        if (!hostTab.visible) return
        const changed = () => { if (document.visibilityState !== 'hidden') refresh() }
        const settingsChanged = () => { clearOperations(); if (document.visibilityState !== 'hidden') refresh(false, true) }
        changed()
        const timer = setInterval(changed, 5000)
        window.addEventListener('mmwb-settings-change', settingsChanged)
        window.addEventListener('focus', changed)
        document.addEventListener('visibilitychange', changed)
        return () => { clearInterval(timer); window.removeEventListener('mmwb-settings-change', settingsChanged); window.removeEventListener('focus', changed); document.removeEventListener('visibilitychange', changed); sequence.current++; statePending.current = false; previewSequence.current++; checkpointSequence.current++ }
      }, [refresh, hostTab.visible, clearOperations])
      async function openPreview(path) {
        const request = ++previewSequence.current
        setBusy(true)
        try {
          const result = await rpc('mm.artifact', { sessionId: sid, path })
          if (previewSequence.current !== request || currentSession.current !== sid) return
          if (!result.ok) throw new Error(result.error?.message || '无法预览')
          setPreview({ ...result.value, sessionId: sid }); setError(null)
        } catch (error) { if (previewSequence.current === request && currentSession.current === sid) setError(String(error.message || error)) }
        finally { if (previewSequence.current === request && currentSession.current === sid) setBusy(false) }
      }
      async function openLog(runId, stream) {
        const request = ++previewSequence.current
        setBusy(true)
        try {
          const result = await rpc('mm.runLog', { sessionId: sid, run_id: runId, stream })
          if (previewSequence.current !== request || currentSession.current !== sid) return
          if (!result.ok) throw new Error(result.error?.message || '无法读取日志')
          setLogPreview({ ...result.value, sessionId: sid }); setError(null)
        } catch (error) { if (previewSequence.current === request && currentSession.current === sid) setError(String(error.message || error)) }
        finally { if (previewSequence.current === request && currentSession.current === sid) setBusy(false) }
      }
      const activeRestorePreview = restorePreview?.sessionId === sid ? restorePreview : null
      async function checkpoint(mode, checkpointId) {
        if (!sid || checkpointBusy || busy) return
        if (mode === 'apply' && !activeRestorePreview) return
        const request = ++checkpointSequence.current
        const sessionId = sid
        const current = () => checkpointSequence.current === request && currentSession.current === sessionId
        const payload = mode === 'create' ? { sessionId } : { sessionId, checkpoint_id: checkpointId, apply: mode === 'apply',
          ...(mode === 'apply' ? { expected_revision: activeRestorePreview.expected_revision } : {}) }
        setCheckpointBusy(true); setCheckpointError(null); setCheckpointNotice(null); setRestorePreview(null)
        try {
          const result = await rpc(mode === 'create' ? 'mm.checkpointCreate' : 'mm.checkpointRestore', payload)
          if (!current()) return
          if (!result.ok) throw new Error(`${result.error?.code || 'checkpoint_error'}: ${result.error?.message || '快照操作失败'}`)
          if (mode === 'preview') {
            const value = result.value
            if (value?.preview !== true || value.checkpoint_id !== checkpointId || !Number.isSafeInteger(value.expected_revision) || !Array.isArray(value.changes)) throw new Error('运行时未返回有效恢复预览；请重新预览。')
            setRestorePreview({ ...value, sessionId })
          } else {
            setCheckpointNotice(mode === 'create' ? '快照已创建。' : '已恢复，待重新验收')
            await refresh(false, true)
          }
        } catch (error) { if (current()) setCheckpointError(String(error.message || error)) }
        finally { if (current()) setCheckpointBusy(false) }
      }
      const initialized = data?.initialized && !data.hidden
      const title = initialized ? data.project?.title || '数学建模项目' : '数学建模 Workbench'
      const tabs = [['overview', '项目', '阶段、阻塞与审核'], ['evidence', '证据', '产物与结论来源'], ['runs', '运行', '执行记录与日志'], ['checkpoints', '快照', '创建与恢复项目版本']]
      return h('section', { ref: root, className: 'mmwb mmwb-panel', 'aria-label': '数学建模 Workbench' },
        h('header', { className: 'mmwb-head' }, h('div', { className: 'mmwb-row' }, h('div', { className: 'mmwb-heading' }, h('h2', { title }, title),
          initialized ? h('div', { className: 'mmwb-meta' }, (scopes[data.project?.scope] || '项目') + ' · ' + (names[data.currentPhase] || '未开始')) : null),
          h('button', { type: 'button', className: 'mmwb-icon-btn', 'aria-label': '重新验证', title: '重新验证 — 检查产物变化与审核状态', disabled: busy || checkpointBusy, onClick: () => refresh(true) }, h(Icon, { name: 'refresh', className: busy ? 'mmwb-spinner' : undefined })))),
        initialized ? h(React.Fragment, null,
          h('div', { className: 'mmwb-counts' }, [['阻塞', (data.blockers || []).length], ['产物', records(data.artifacts).length], ['运行', records(data.runs).length]].map(([label, count]) => h('span', { key: label }, h('strong', null, count), label))),
          h('div', { className: 'mmwb-tabs', role: 'tablist', 'aria-label': '项目详情' }, tabs.map(([id, label, hint], index) => h('button', {
            key: id, id: instanceId + '-tab-' + id, className: 'mmwb-tab', role: 'tab', tabIndex: tab === id ? 0 : -1, title: label + ' — ' + hint,
            'aria-selected': tab === id, 'aria-controls': instanceId + '-panel-' + id, onClick: () => setTab(id),
            onKeyDown: event => {
              const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length : null
              if (next === null) return
              event.preventDefault(); setTab(tabs[next][0]); event.currentTarget.parentElement.children[next].focus()
            },
          }, label)))) : null,
        h('div', { className: 'mmwb-content mmwb-scroll', 'data-testid': 'mmwb-content-scroll', id: instanceId + '-panel-' + tab, role: initialized ? 'tabpanel' : undefined, 'aria-labelledby': initialized ? instanceId + '-tab-' + tab : undefined, tabIndex: 0 },
          error ? h('p', { className: 'mmwb-error mmwb-notice', role: 'alert' }, error) : null,
          initialized ? tab === 'overview' ? h(Overview, { data }) : tab === 'evidence' ? h(Evidence, { data, preview: preview?.sessionId === sid ? preview : null, openPreview, busy: busy || checkpointBusy }) : tab === 'runs' ? h(Runs, { data, preview: logPreview?.sessionId === sid ? logPreview : null, openLog, busy: busy || checkpointBusy }) :
            h(Checkpoints, { data, busy: busy || checkpointBusy, preview: activeRestorePreview, notice: checkpointNotice, error: checkpointError, create: () => checkpoint('create'), previewRestore: id => checkpoint('preview', id), confirmRestore: () => activeRestorePreview && checkpoint('apply', activeRestorePreview.checkpoint_id), cancelRestore: () => setRestorePreview(null) }) :
            h('p', { className: 'mmwb-empty mmwb-notice' }, data?.hidden ? data.reason === 'no-project' ? '当前会话未初始化数学建模项目' : '看板已关闭' : error ? '项目读取失败' : '正在读取项目')),
        initialized ? h('footer', { className: 'mmwb-foot' }, h('span', { title: data.stale ? '磁盘中的上次状态；重新验证可检查产物变化' : '已调用运行时核验' }, data.stale ? '已保存状态' : '已核验'), h('time', { title: timestamp(data.snapshotAt || data.updated_at) }, timestamp(data.snapshotAt || data.updated_at))) : null)
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
      return h('section', { className: 'mmwb mmwb-settings' }, h('div', { className: 'mmwb-row' }, h('span', null, '数学建模 Workbench'), h('button', { className: 'mmwb-btn', role: 'switch', 'aria-label': '数学建模 Workbench', title: '控制已初始化项目的侧边栏入口与看板显示', 'aria-checked': enabled === true, disabled: busy || enabled === null, onClick: toggle }, enabled ? '已开启' : '已关闭')), error ? h('p', { role: 'alert', className: 'mmwb-warning mmwb-error' }, error) : null)
    }
    function apply(ctx) {
      ctx.effect(() => {
        const tag = document.createElement('style')
        tag.dataset.mmui = 'dsh-math-modeling-ui'; tag.textContent = CSS; document.head.append(tag)
        return () => tag.remove()
      })
      const rpc = (endpoint, payload) => ctx.connection.rpc.call(CHANNEL, endpoint, payload)
      ctx.effect(() => ctx.sidebarRightTabs.register({
        id: 'dsh-math-modeling-ui', kind: 'math-modeling', title: () => '数学建模 Workbench',
        guide: [{ id: 'workbench', order: 30, title: () => '数学建模 Workbench', icon: props => h(Icon, { ...props, name: 'board' }) }],
      }))
      ctx.effect(() => ctx.slots.inject('sidebar.right.tab.guide.entry', () => ctx.slots.register({
        name: 'sidebar.right.tab.guide.entry', key: 'dsh-math-modeling-ui', inject: () => ({ rpc }),
      }, GuideEntry)))
      ctx.effect(() => ctx.slots.inject('sidebar.right.pane.tab', () => ctx.slots.register({
        name: 'sidebar.right.pane.tab', key: 'dsh-math-modeling-ui', inject: () => ({ rpc }),
      }, Workbench)))
      ctx.effect(() => ctx.slots.inject('settings.section', () => ctx.slots.register({
        name: 'settings.section', id: 'math-modeling', order: 11, label: () => '数学建模', inject: () => ({ rpc }),
      }, Settings)))
    }
    return { name: 'dsh-math-modeling-ui', inject: ['slots', 'connection', 'sidebarRightTabs'], apply }
  },
})
