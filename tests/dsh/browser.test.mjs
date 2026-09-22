import test from 'node:test'
import assert from 'node:assert/strict'
import * as fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const modules = process.env.DSH_TEST_NODE_MODULES
const repo = fileURLToPath(new URL('../../', import.meta.url))

test('browser: scoped sidebar, session races, evidence, snapshots, themes and scrollbars', { skip: !modules, timeout: 60000 }, async t => {
  const { chromium } = await import(pathToFileURL(path.join(modules, 'playwright/index.mjs')))
  const browser = await chromium.launch(process.platform === 'win32' ? { channel: 'msedge' } : {})
  t.after(() => browser.close())
  const page = await browser.newPage({ viewport: { width: 1100, height: 840 }, locale: 'zh-CN' })
  page.setDefaultTimeout(7000)
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  const screenshots = path.join(repo, 'project-review/logs')
  await fs.mkdir(screenshots, { recursive: true })
  await page.setContent(`<html lang="zh-CN"><head><title>MathModel sidebar host fixture</title><style>
    body{--dsw-font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',sans-serif;margin:0;font:13px var(--dsw-font-family);color:#242424;background:#fff}
    #host{display:flex;height:100vh;min-width:0}main{flex:1;min-width:0;padding:28px}main h1{font-size:17px;font-weight:500}
    #sidebar{width:420px;max-width:100vw;min-width:0;display:flex;flex-direction:column;border-left:1px solid #e5e5e7;background:#fff}
    .host-title{display:flex;align-items:center;justify-content:space-between;padding:9px 12px;border-bottom:1px solid #dedede;font-size:12px}
    .host-title button{font:inherit;border:0;background:transparent;color:inherit;cursor:pointer}
    .host-pane{flex:1;min-height:0;display:flex;flex-direction:column}.host-guide{display:flex;flex-direction:column;align-items:center;gap:12px;padding:42px 20px}
    .host-guide-cell{width:380px;max-width:100%}.host-guide-button{width:100%;min-height:56px;text-align:left;padding:14px 20px;border:1px solid #dedede;border-radius:24px;background:#fff;color:inherit;font:inherit}
    body[data-ds-dark-theme]{color:#ccc;background:#161618}body[data-ds-dark-theme] #sidebar{background:#1b1b1d;border-color:#343437}
    body[data-ds-dark-theme] .host-title{border-color:#343437}body[data-ds-dark-theme] .host-guide-button{color:#ddd;background:#1b1b1d;border-color:#343437}
    @media(max-width:600px){main{display:none}#sidebar{width:100%;border-left:0}}
  </style></head><body><div id="host"></div></body></html>`)
  await page.addScriptTag({ path: path.join(modules, 'react/umd/react.development.js') })
  await page.addScriptTag({ path: path.join(modules, 'react-dom/umd/react-dom.development.js') })
  await page.evaluate(() => {
    const h = React.createElement, listeners = new Set(), definitions = new Map(), slots = new Map(), disposers = [], signals = new Map()
    const root = ReactDOM.createRoot(document.getElementById('host'))
    const fixture = window.fixture = {
      sid: 'a', mainSid: 'b', kind: 'guide', visible: true, enabled: true, initialized: { a: true, b: true, c: false },
      projectGeneration: { a: 1, b: 1, c: 1 },
      calls: [], openCalls: [], registrations: [], effects: [], longContent: false,
      holds: {}, pending: {}, restoreConflict: true, restoreRevision: 41,
      checkpoints: {
        a: [{ checkpoint_id: 'checkpoint_aaaaaaaaaaaaaaaa', name: '已验收基线', created_at: '2026-09-22T07:00:00Z', completed_when_created: true }],
        b: [{ checkpoint_id: 'checkpoint_bbbbbbbbbbbbbbbb', name: '项目 B 草稿', created_at: '2026-09-22T07:30:00Z', completed_when_created: false }], c: [],
      },
      change(id) { this.sid = id; render(); listeners.forEach(fn => fn()) },
      guide(id = this.sid) { this.kind = 'guide'; this.change(id) },
      setVisible(value) { this.visible = value; render() },
      release(key) { this.holds[key] = false; for (const resolve of this.pending[key] || []) resolve(); this.pending[key] = [] },
    }
    async function hold(key) {
      if (fixture.holds[key]) await new Promise(resolve => (fixture.pending[key] ||= []).push(resolve))
    }
    const state = sid => fixture.initialized[sid] ? {
      initialized: true, stale: true, snapshotAt: '2026-09-22T08:00:00Z',
      project: { title: { a: '城市能源调度研究', b: '第二个独立项目', c: '刚初始化的项目' }[sid], scope: 'programming',
        project_id: `project-${sid}-${fixture.projectGeneration[sid]}`, projectRoot: `D:/projects/${sid}-${fixture.projectGeneration[sid]}` },
      currentPhase: 'programming', completed: false,
      blockers: fixture.longContent ? Array.from({ length: 30 }, (_, i) => `待复核结果 ${i + 1}：检查输入与输出来源`) : ['P2：结果表尚未关联实际运行'],
      progress: { steps: [{ key: 'programming', label: '编程求解', status: 'current' }], tasks: { programming: { done: 4, total: 6, pct: 67 } } },
      gates: { P1: { status: 'PASS' }, P2: { status: 'BLOCKED' } }, capabilities: { python: true },
      artifacts: [{ id: 'a1', kind: 'table', question: 'q1', path: 'results/answer.csv', sha256: 'a'.repeat(64) }],
      claims: [{ id: 'c1', text: '方案 A 的成本最低', artifact_ids: ['a1'], locator: '第 2 行' }],
      runs: [{ run_id: 'r1', argv: ['python', 'solver.py'], exit_code: 0 }], checkpoints: fixture.checkpoints[sid],
      ledgerTail: [{ at: '2026-09-22T08:00:00Z', event: 'run.completed' }],
    } : { initialized: false }
    const rpc = async (_channel, endpoint, payload) => {
      fixture.calls.push({ endpoint, payload })
      if (endpoint === 'mm.state') {
        const value = structuredClone(fixture.enabled ? { ...state(payload.sessionId), stale: !payload.refresh } : { hidden: true })
        await hold(`state:${payload.sessionId}`)
        return { ok: true, value }
      }
      if (endpoint === 'mm.artifact') {
        await hold(`artifact:${payload.sessionId}`)
        return { ok: true, value: { content: `方案,cost\n${payload.sessionId.toUpperCase()},42\nB,67`, path: payload.path } }
      }
      if (endpoint === 'mm.runLog') {
        await hold(`log:${payload.sessionId}`)
        return { ok: true, value: { content: payload.stream === 'stdout' ? 'solver finished: objective=42' : 'solver stderr: no diagnostics', truncated: false } }
      }
      if (endpoint === 'mm.checkpointCreate') {
        const checkpoint = { checkpoint_id: 'checkpoint_cccccccccccccccc', name: '工作台新快照', created_at: '2026-09-22T08:30:00Z', completed_when_created: false }
        fixture.checkpoints[payload.sessionId].push(checkpoint)
        return { ok: true, value: { ok: true, checkpoint } }
      }
      if (endpoint === 'mm.checkpointRestore') {
        await hold(`restore:${payload.sessionId}`)
        if (!payload.apply) return { ok: true, value: { preview: true, checkpoint_id: payload.checkpoint_id, expected_revision: fixture.restoreRevision,
          changes: [{ path: 'restored.csv', operation: 'add' }, { path: 'solver.py', operation: 'replace' }, { path: 'draft.txt', operation: 'remove' }] } }
        if (fixture.restoreConflict) {
          fixture.restoreConflict = false; fixture.restoreRevision++
          return { ok: false, error: { code: 'revision_conflict', message: 'Project or checkpoint changed since restore preview; preview again' } }
        }
        fixture.checkpoints[payload.sessionId].push({ checkpoint_id: 'checkpoint_dddddddddddddddd', name: '恢复副本', created_at: '2026-09-22T08:35:00Z', completed_when_created: false })
        return { ok: true, value: { restored: payload.checkpoint_id } }
      }
      if (endpoint === 'mm.setEnabled') fixture.enabled = payload.enabled
      return { ok: true, value: { enabled: fixture.enabled, persistent: true } }
    }
    function tabInfo(sessionId, kind) {
      const occurrence = `${sessionId}:${kind}`
      if (!signals.has(occurrence)) signals.set(occurrence, new AbortController().signal)
      return { sidebar: { expanded: true, fullscreen: false }, panel: { id: 'right-panel' }, tab: {
        id: 'right-tab', kind, title: kind === 'guide' ? '开始' : '数学建模 Workbench', visible: fixture.visible,
        navigation: { address: {}, params: {}, revision: 0 }, signal: signals.get(occurrence),
        actions: { openTab(nextKind, options) {
          if (!definitions.has(nextKind)) throw new Error(`Unregistered sidebar kind: ${nextKind}`)
          fixture.openCalls.push({ sessionId, kind: nextKind, options }); fixture.kind = nextKind; fixture.sid = sessionId; render()
        } },
      } }
    }
    function Slot({ name, slotKey, sessionId, ownerProps = {} }) {
      const registration = slots.get(`${name}:${slotKey || ''}`)
      if (!registration) return null
      const { definition, Component } = registration
      // Official keyed seats inject the session, owner props and a tab hook bound to that occurrence.
      const injected = typeof definition.inject === 'function' ? definition.inject(sessionId) : definition.inject || {}
      return h(Component, { ...injected, ...ownerProps, sessionId, useTabInfo: () => tabInfo(sessionId, fixture.kind) })
    }
    function Host() {
      const sid = fixture.sid
      const entries = [...definitions.values()].flatMap(definition => (definition.guide || []).map(entry => ({ ...entry, providerId: definition.id, kind: definition.kind }))).sort((a, b) => a.order - b.order)
      return h(React.Fragment, null,
        h('main', null, h('h1', null, '会话工作区'), h('p', null, '当前会话：', sid), h(Slot, { name: 'settings.section', slotKey: 'math-modeling' })),
        h('aside', { id: 'sidebar', 'aria-label': '右侧栏' },
          h('div', { className: 'host-title' }, h('span', null, fixture.kind === 'guide' ? '开始' : '数学建模 Workbench'), h('button', { onClick: () => fixture.guide(), 'aria-label': '打开右侧栏开始页' }, '开始')),
          h('div', { className: 'host-pane' }, fixture.kind === 'guide' ? h('div', { className: 'host-guide', 'data-sidebar-right-guide': true }, entries.map(entry => {
            const name = 'sidebar.right.tab.guide.entry'
            return h('div', { className: 'host-guide-cell', key: JSON.stringify([entry.providerId, entry.id]), 'data-guide-kind': entry.kind },
              slots.has(`${name}:${entry.providerId}`) ? h(Slot, { name, slotKey: entry.providerId, sessionId: sid, ownerProps: { entryId: entry.id, kind: entry.kind, title: entry.title(), ...(entry.description ? { description: entry.description() } : {}) } }) :
                h('button', { className: 'host-guide-button', 'data-sidebar-right-guide-entry': entry.kind }, entry.title()))
          })) : h(Slot, { name: 'sidebar.right.pane.tab', slotKey: definitions.get(fixture.kind)?.id, sessionId: sid }))))
    }
    function render() { root.render(h(Host)) }
    definitions.set('files', { id: 'builtin-files', kind: 'files', guide: [{ id: 'workspace', order: 10, title: () => '工作区文件' }] })
    definitions.set('terminal', { id: 'builtin-terminal', kind: 'terminal', guide: [{ id: 'new', order: 20, title: () => '终端' }] })
    window.__ModuleLoader__ = { load({ factory }) {
      const plugin = factory(name => { if (name === 'react') return React; throw new Error(name) })
      fixture.inject = plugin.inject
      plugin.apply({
        on(event, callback) { if (event === 'dispose') disposers.push(callback); return () => {} },
        effect(callback, label) { fixture.effects.push(label); const dispose = callback(); if (dispose) disposers.push(dispose); return dispose },
        connection: { rpc: { call: rpc } },
        sessions: { list: { getSnapshot: () => ({ byId: Object.fromEntries(['a', 'b', 'c'].map(id => [id, { id, retainedBy: { mainView: fixture.mainSid === id ? 1 : 0 } }])) }), subscribe: fn => { listeners.add(fn); return () => listeners.delete(fn) } } },
        sidebarRightTabs: { register(definition) {
          if (!definition.id || !definition.kind || definitions.has(definition.kind)) throw new Error('Invalid or duplicate sidebar type')
          definitions.set(definition.kind, definition)
          fixture.definition = { id: definition.id, kind: definition.kind, guide: definition.guide.map(({ id, order }) => ({ id, order })) }
          return () => definitions.delete(definition.kind)
        } },
        slots: {
          inject(name, callback) { if (name === 'shell.overlay') throw new Error('The workbench must use the right sidebar, not shell.overlay'); return callback() },
          register(definition, Component) {
            if (!['sidebar.right.tab.guide.entry', 'sidebar.right.pane.tab', 'settings.section'].includes(definition.name)) throw new Error(`Unexpected slot: ${definition.name}`)
            if (definition.name !== 'settings.section' && definition.key !== 'dsh-math-modeling-ui') throw new Error('Keyed session seat must use the provider id')
            const key = `${definition.name}:${definition.key || definition.id || ''}`
            slots.set(key, { definition, Component }); fixture.registrations.push({ name: definition.name, key: definition.key, id: definition.id })
            return () => slots.delete(key)
          },
        },
      })
      render()
    } }
  })
  await page.addScriptTag({ path: path.join(repo, 'dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui/client/client.js') })
  const entry = page.getByRole('button', { name: '数学建模 Workbench', exact: true })
  const panel = page.locator('[aria-label="数学建模 Workbench"]').filter({ has: page.getByRole('tablist') })
  const settle = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
  const title = name => page.getByRole('heading', { name, exact: true })
  const refreshSnapshot = () => page.evaluate(() => window.dispatchEvent(new Event('mmwb-settings-change')))
  await entry.waitFor()
  const definition = await page.evaluate(() => fixture.definition)
  assert.equal(definition.id, 'dsh-math-modeling-ui')
  assert.equal(definition.kind, 'math-modeling')
  assert.equal(definition.guide.length, 1)
  assert.equal(definition.guide[0].order, 30)
  assert.deepEqual(await page.locator('.host-guide button').allTextContents(), ['工作区文件', '终端', '数学建模 Workbench'])
  assert.equal(await panel.count(), 0, 'guide entry must not render a floating workbench')
  assert.equal(await page.evaluate(() => fixture.calls.some(call => call.endpoint === 'mm.state' && call.payload.refresh)), false)
  await page.screenshot({ path: path.join(screenshots, 'sidebar-guide.png'), fullPage: true })
  await entry.click()
  await title('城市能源调度研究').waitFor()
  assert.deepEqual(await page.evaluate(() => fixture.openCalls), [{ sessionId: 'a', kind: 'math-modeling', options: { replaceTab: true } }])
  await page.evaluate(() => fixture.setVisible(false))
  await settle()
  const hiddenCalls = await page.evaluate(() => fixture.calls.filter(call => call.endpoint === 'mm.state').length)
  await page.evaluate(() => { window.dispatchEvent(new Event('focus')); document.dispatchEvent(new Event('visibilitychange')); window.dispatchEvent(new Event('mmwb-settings-change')) })
  await settle()
  assert.equal(await page.evaluate(() => fixture.calls.filter(call => call.endpoint === 'mm.state').length), hiddenCalls, 'hidden host tab must not read snapshots on focus/settings events')
  await page.evaluate(() => fixture.setVisible(true))
  await page.waitForFunction(count => fixture.calls.filter(call => call.endpoint === 'mm.state').length > count, hiddenCalls)
  assert.notEqual(await panel.evaluate(el => getComputedStyle(el).position), 'fixed')
  assert.equal(await panel.locator('.mmwb-kicker').count(), 0)
  assert.deepEqual(await panel.getByRole('tab').allTextContents(), ['项目', '证据', '运行', '快照'])
  assert.match(await page.getByRole('tabpanel').innerText(), /结果表尚未关联实际运行/)
  await page.getByRole('tab', { name: '项目', exact: true }).focus()
  await page.keyboard.press('ArrowRight')
  assert.equal(await page.getByRole('tab', { name: '证据', exact: true }).getAttribute('aria-selected'), 'true')
  await page.getByRole('button', { name: '预览 results/answer.csv' }).click()
  assert.match(await page.getByRole('region', { name: '产物预览' }).innerText(), /A,42/)
  await page.getByRole('tab', { name: '运行', exact: true }).click()
  await page.getByText('python solver.py', { exact: true }).click()
  await page.getByRole('button', { name: '读取 stdout' }).click()
  assert.match(await page.getByRole('region', { name: '运行日志' }).innerText(), /objective=42/)
  await page.getByRole('button', { name: '读取 stderr' }).click()
  assert.match(await page.getByRole('region', { name: '运行日志' }).innerText(), /no diagnostics/)

  await page.getByRole('tab', { name: '证据', exact: true }).click()
  await page.evaluate(() => { fixture.holds['artifact:a'] = true })
  await page.getByRole('button', { name: '预览 results/answer.csv' }).click()
  await page.waitForFunction(() => fixture.pending['artifact:a']?.length === 1)
  await page.evaluate(() => fixture.change('b'))
  await title('第二个独立项目').waitFor()
  await page.evaluate(() => fixture.release('artifact:a'))
  await settle()
  assert.equal(await page.getByRole('region', { name: '产物预览' }).count(), 0, 'late artifact response must not appear in another session')
  await page.evaluate(() => fixture.change('a'))
  await title('城市能源调度研究').waitFor()
  await page.getByRole('tab', { name: '运行', exact: true }).click()
  await page.getByText('python solver.py', { exact: true }).click()
  await page.evaluate(() => { fixture.holds['log:a'] = true })
  await page.getByRole('button', { name: '读取 stdout' }).click()
  await page.waitForFunction(() => fixture.pending['log:a']?.length === 1)
  await page.evaluate(() => fixture.change('b'))
  await title('第二个独立项目').waitFor()
  await page.evaluate(() => fixture.release('log:a'))
  await settle()
  assert.equal(await page.getByRole('region', { name: '运行日志' }).count(), 0, 'late log response must not appear in another session')
  await page.evaluate(() => fixture.change('a'))
  await title('城市能源调度研究').waitFor()

  await page.getByRole('tab', { name: '快照', exact: true }).click()
  assert.equal(await page.getByRole('button', { name: '确认恢复', exact: true }).count(), 0)
  await page.evaluate(() => { fixture.holds['state:a'] = true; window.dispatchEvent(new Event('focus')) })
  await page.waitForFunction(() => fixture.pending['state:a']?.length === 1)
  await page.evaluate(() => { fixture.holds['state:a'] = false })
  await page.getByRole('button', { name: '创建快照', exact: true }).click()
  await page.getByText('快照已创建。', { exact: true }).waitFor()
  await page.getByText('工作台新快照', { exact: true }).waitFor()
  await page.evaluate(() => fixture.release('state:a'))
  await settle()
  assert.equal(await page.getByText('工作台新快照', { exact: true }).count(), 1, 'creation must force a fresh read and discard the earlier frozen snapshot')
  await page.getByRole('button', { name: '预览恢复 已验收基线', exact: true }).click()
  const restorePreview = page.getByRole('region', { name: '恢复预览' })
  await restorePreview.waitFor()
  assert.match(await restorePreview.innerText(), /新增 \(add\).*restored.csv/s)
  assert.match(await restorePreview.innerText(), /替换 \(replace\).*solver.py/s)
  assert.match(await restorePreview.innerText(), /删除 \(remove\).*draft.txt/s)
  assert.equal(await page.evaluate(() => fixture.calls.filter(call => call.endpoint === 'mm.checkpointRestore' && call.payload.apply).length), 0)
  await page.getByRole('button', { name: '取消恢复', exact: true }).click()
  await restorePreview.waitFor({ state: 'hidden' })
  assert.equal(await page.evaluate(() => fixture.calls.filter(call => call.endpoint === 'mm.checkpointRestore' && call.payload.apply).length), 0, 'cancel must never apply restoration')
  await page.getByRole('button', { name: '预览恢复 已验收基线', exact: true }).click()
  await restorePreview.waitFor()
  if (process.env.DSH_CHECKPOINT_SCREENSHOT) await page.screenshot({ path: process.env.DSH_CHECKPOINT_SCREENSHOT, fullPage: true })
  await page.getByRole('button', { name: '确认恢复', exact: true }).click()
  await page.getByRole('alert').filter({ hasText: 'revision_conflict: Project or checkpoint changed since restore preview; preview again' }).waitFor()
  assert.equal(await page.getByRole('button', { name: '确认恢复', exact: true }).count(), 0)
  await page.getByRole('button', { name: '预览恢复 已验收基线', exact: true }).click()
  await restorePreview.waitFor()
  await page.evaluate(() => { fixture.holds['state:a'] = true; window.dispatchEvent(new Event('focus')) })
  await page.waitForFunction(() => fixture.pending['state:a']?.length === 1)
  await page.evaluate(() => { fixture.holds['state:a'] = false })
  await page.getByRole('button', { name: '确认恢复', exact: true }).click()
  await page.getByRole('status').filter({ hasText: '已恢复，待重新验收' }).waitFor()
  await page.getByText('恢复副本', { exact: true }).waitFor()
  await page.evaluate(() => fixture.release('state:a'))
  await settle()
  assert.equal(await page.getByText('恢复副本', { exact: true }).count(), 1, 'apply must force a fresh read and discard the earlier frozen snapshot')
  assert.deepEqual(await page.evaluate(() => fixture.calls.filter(call => call.endpoint === 'mm.checkpointRestore' && call.payload.apply).map(call => call.payload)), [
    { sessionId: 'a', checkpoint_id: 'checkpoint_aaaaaaaaaaaaaaaa', apply: true, expected_revision: 41 },
    { sessionId: 'a', checkpoint_id: 'checkpoint_aaaaaaaaaaaaaaaa', apply: true, expected_revision: 42 },
  ])
  await page.getByRole('button', { name: '预览恢复 已验收基线', exact: true }).click()
  await restorePreview.waitFor()
  await page.evaluate(() => fixture.change('b'))
  await title('第二个独立项目').waitFor()
  assert.equal(await page.getByRole('button', { name: '确认恢复', exact: true }).count(), 0)
  await page.getByRole('tab', { name: '快照', exact: true }).click()
  await page.getByText('项目 B 草稿', { exact: true }).waitFor()
  await page.evaluate(() => { fixture.change('a'); fixture.holds['restore:a'] = true })
  await title('城市能源调度研究').waitFor()
  await page.getByRole('tab', { name: '快照', exact: true }).click()
  await page.getByRole('button', { name: '预览恢复 已验收基线', exact: true }).click()
  await page.waitForFunction(() => fixture.pending['restore:a']?.length === 1)
  await page.evaluate(() => fixture.change('b'))
  await title('第二个独立项目').waitFor()
  await page.evaluate(() => fixture.release('restore:a'))
  await settle()
  assert.equal(await page.getByRole('button', { name: '确认恢复', exact: true }).count(), 0, 'late preview from another session must be discarded')
  assert.equal(await page.evaluate(() => fixture.calls.filter(call => call.endpoint === 'mm.checkpointRestore' && call.payload.apply).length), 2)

  await page.evaluate(() => fixture.change('a'))
  await title('城市能源调度研究').waitFor()
  await page.getByRole('tab', { name: '项目', exact: true }).click()
  await page.evaluate(() => { fixture.holds['state:a'] = true })
  await page.getByRole('button', { name: '重新验证', exact: true }).click()
  await page.waitForFunction(() => fixture.pending['state:a']?.length >= 1)
  await page.evaluate(() => fixture.change('b'))
  await title('第二个独立项目').waitFor()
  await page.evaluate(() => fixture.release('state:a'))
  await settle()
  assert.equal(await title('城市能源调度研究').count(), 0)
  assert.equal(await page.evaluate(() => fixture.calls.filter(call => call.endpoint === 'mm.state' && call.payload.refresh === true).length), 1, 'only the explicit revalidate gesture invokes runtime refresh')

  await page.evaluate(() => fixture.change('a'))
  await title('城市能源调度研究').waitFor()
  await page.getByRole('tab', { name: '证据', exact: true }).click()
  await page.getByRole('button', { name: '预览 results/answer.csv' }).click()
  await page.getByRole('region', { name: '产物预览' }).waitFor()
  await page.getByRole('tab', { name: '运行', exact: true }).click()
  await page.getByText('python solver.py', { exact: true }).click()
  await page.getByRole('button', { name: '读取 stdout' }).click()
  await page.getByRole('region', { name: '运行日志' }).waitFor()
  await page.getByRole('tab', { name: '快照', exact: true }).click()
  await page.getByRole('button', { name: '预览恢复 已验收基线', exact: true }).click()
  await restorePreview.waitFor()
  // A normal focus read discovers the new project; a settings event would mask this race by clearing previews itself.
  await page.evaluate(() => { fixture.projectGeneration.a++; window.dispatchEvent(new Event('focus')) })
  await settle()
  assert.equal(await restorePreview.count(), 0, 'reinitializing the same session clears cached recovery confirmation')
  await page.getByRole('tab', { name: '证据', exact: true }).click()
  assert.equal(await page.getByRole('region', { name: '产物预览' }).count(), 0)
  await page.getByRole('tab', { name: '运行', exact: true }).click()
  assert.equal(await page.getByRole('region', { name: '运行日志' }).count(), 0)
  for (const operation of [
    { key: 'artifact:a', tab: '证据', button: '预览 results/answer.csv', region: '产物预览' },
    { key: 'log:a', tab: '运行', button: '读取 stdout', region: '运行日志' },
    { key: 'restore:a', tab: '快照', button: '预览恢复 已验收基线', region: '恢复预览' },
  ]) {
    await page.getByRole('tab', { name: operation.tab, exact: true }).click()
    if (operation.key === 'log:a') await page.getByText('python solver.py', { exact: true }).click()
    await page.evaluate(key => { fixture.holds[key] = true }, operation.key)
    await page.getByRole('button', { name: operation.button, exact: true }).click()
    await page.waitForFunction(key => fixture.pending[key]?.length === 1, operation.key)
    await page.evaluate(() => { fixture.projectGeneration.a++; window.dispatchEvent(new Event('focus')) })
    await settle()
    await page.evaluate(key => fixture.release(key), operation.key)
    await settle()
    assert.equal(await page.getByRole('region', { name: operation.region }).count(), 0, `${operation.key} from the previous project identity must be discarded`)
  }

  await page.getByRole('button', { name: '预览恢复 已验收基线', exact: true }).click()
  await restorePreview.waitFor()
  await page.getByRole('switch').click()
  await panel.waitFor({ state: 'hidden' })
  await page.getByRole('switch').click()
  await title('城市能源调度研究').waitFor()
  assert.equal(await page.getByRole('button', { name: '确认恢复', exact: true }).count(), 0, 'reenabling settings must not revive a cached restore confirmation')
  await page.evaluate(() => { fixture.holds['restore:a'] = true })
  await page.getByRole('button', { name: '预览恢复 已验收基线', exact: true }).click()
  await page.waitForFunction(() => fixture.pending['restore:a']?.length === 1)
  await page.evaluate(() => { fixture.holds['state:a'] = true })
  await page.getByRole('switch').click()
  await page.waitForFunction(() => fixture.pending['state:a']?.length === 1)
  assert.equal(await page.getByRole('switch').getAttribute('aria-checked'), 'false')
  await page.evaluate(() => { fixture.holds['state:a'] = false })
  await page.evaluate(() => fixture.release('restore:a'))
  await settle()
  assert.equal(await page.getByRole('button', { name: '确认恢复', exact: true }).count(), 0, 'disable must invalidate preview immediately, before the hidden-state response returns')
  const beforeReenable = await page.evaluate(() => fixture.calls.filter(call => call.endpoint === 'mm.state').length)
  await page.getByRole('switch').click()
  await page.waitForFunction(count => fixture.calls.filter(call => call.endpoint === 'mm.state').length > count, beforeReenable)
  await settle()
  await page.evaluate(() => fixture.release('state:a'))
  await settle()
  await title('城市能源调度研究').waitFor()
  assert.equal(await page.getByRole('button', { name: '确认恢复', exact: true }).count(), 0, 'preview arriving while disabled must remain discarded after reenable')
  assert.equal(await page.evaluate(() => fixture.calls.filter(call => call.endpoint === 'mm.checkpointRestore' && call.payload.apply).length), 2)

  await page.evaluate(() => { fixture.holds['state:a'] = true; fixture.guide('a') })
  await page.waitForFunction(() => fixture.pending['state:a']?.length >= 1)
  await page.evaluate(() => fixture.guide('c'))
  await page.waitForFunction(() => fixture.calls.some(call => call.endpoint === 'mm.state' && call.payload.sessionId === 'c'))
  await page.evaluate(() => fixture.release('state:a'))
  await settle()
  assert.equal(await entry.count(), 0, 'uninitialized sessions must not show the workbench entry')
  await page.evaluate(() => { fixture.initialized.c = true; window.dispatchEvent(new Event('mmwb-settings-change')) })
  await entry.waitFor()
  await entry.click()
  await title('刚初始化的项目').waitFor()
  assert.deepEqual(await page.evaluate(() => fixture.openCalls.at(-1)), { sessionId: 'c', kind: 'math-modeling', options: { replaceTab: true } })

  await page.evaluate(() => fixture.change('a'))
  await title('城市能源调度研究').waitFor()
  await page.getByRole('tab', { name: '项目', exact: true }).click()
  await page.evaluate(() => { fixture.longContent = true })
  await refreshSnapshot()
  await page.getByText('待复核结果 30：检查输入与输出来源', { exact: true }).waitFor()
  const scroll = page.getByTestId('mmwb-content-scroll')
  assert.ok(await scroll.evaluate(el => el.scrollHeight > el.clientHeight), 'fixture must really overflow before scrollbar testing')
  await page.mouse.move(10, 10)
  const thumb = () => scroll.evaluate(el => getComputedStyle(el, '::-webkit-scrollbar-thumb').backgroundColor)
  await page.waitForFunction(() => getComputedStyle(document.querySelector('[data-testid="mmwb-content-scroll"]'), '::-webkit-scrollbar-thumb').backgroundColor === 'rgba(0, 0, 0, 0)')
  await scroll.hover()
  await page.waitForFunction(() => getComputedStyle(document.querySelector('[data-testid="mmwb-content-scroll"]'), '::-webkit-scrollbar-thumb').backgroundColor !== 'rgba(0, 0, 0, 0)')
  await page.mouse.wheel(0, 350)
  await page.waitForFunction(() => document.querySelector('[data-testid="mmwb-content-scroll"]').dataset.scrolling === 'true')
  await page.mouse.move(10, 10)
  assert.notEqual(await thumb(), 'rgba(0, 0, 0, 0)', 'recent scrolling should keep thumb visible after pointer exit')
  await page.waitForFunction(() => document.querySelector('[data-testid="mmwb-content-scroll"]').dataset.scrolling !== 'true', null, { timeout: 2500 })
  await page.waitForFunction(() => getComputedStyle(document.querySelector('[data-testid="mmwb-content-scroll"]'), '::-webkit-scrollbar-thumb').backgroundColor === 'rgba(0, 0, 0, 0)')

  await page.evaluate(() => { fixture.longContent = false })
  await refreshSnapshot()
  await page.getByText('P2：结果表尚未关联实际运行', { exact: true }).waitFor()
  await scroll.evaluate(el => { el.scrollTop = 0 })
  await page.mouse.move(10, 10)
  await page.waitForFunction(() => document.querySelector('[data-testid="mmwb-content-scroll"]').dataset.scrolling !== 'true')
  const lightBackground = await panel.evaluate(el => getComputedStyle(el).backgroundColor)
  await page.screenshot({ path: path.join(screenshots, 'sidebar-light.png'), fullPage: true })
  await panel.screenshot({ path: path.join(screenshots, 'sidebar-panel-light.png') })
  if (process.env.DSH_UI_SCREENSHOT) await page.screenshot({ path: process.env.DSH_UI_SCREENSHOT, fullPage: true })
  await page.evaluate(() => document.body.setAttribute('data-ds-dark-theme', ''))
  await settle()
  assert.notEqual(await panel.evaluate(el => getComputedStyle(el).backgroundColor), lightBackground)
  await page.screenshot({ path: path.join(screenshots, 'sidebar-dark.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 780 })
  const box = await panel.boundingBox()
  assert.ok(box.x >= 0 && box.x + box.width <= 390)
  assert.ok(await panel.evaluate(el => el.scrollWidth <= el.clientWidth + 1), 'narrow sidebar must not overflow horizontally')
  await page.screenshot({ path: path.join(screenshots, 'sidebar-narrow.png'), fullPage: true })

  await page.setViewportSize({ width: 1100, height: 840 })
  await page.getByRole('switch').click()
  assert.equal(await page.getByRole('switch').getAttribute('aria-checked'), 'false')
  await panel.waitFor({ state: 'hidden' })
  await page.evaluate(() => fixture.guide())
  await settle()
  assert.equal(await entry.count(), 0)
  await page.getByRole('switch').click()
  await entry.waitFor()
  await entry.click()
  await title('城市能源调度研究').waitFor()
  assert.deepEqual(errors, [])
  t.diagnostic('Real browser + React render with official session-scoped keyed guide/pane props and sidebar registry fixture; not a full DSH desktop E2E test.')
})
