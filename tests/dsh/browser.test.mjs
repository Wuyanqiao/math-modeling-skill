import test from 'node:test'
import assert from 'node:assert/strict'
import * as fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const modules = process.env.DSH_TEST_NODE_MODULES
const repo = fileURLToPath(new URL('../../', import.meta.url))

test('browser: project, evidence, checkpoints, keyboard tabs, settings and session races', { skip: !modules, timeout: 60000 }, async t => {
  const { chromium } = await import(pathToFileURL(path.join(modules, 'playwright/index.mjs')))
  const browser = await chromium.launch(process.platform === 'win32' ? { channel: 'msedge' } : {})
  t.after(() => browser.close())
  const page = await browser.newPage({ viewport: { width: 1100, height: 840 }, locale: 'zh-CN' })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.setContent('<html lang="zh-CN"><head><title>MathModel UI fixture</title></head><body style="margin:0;background:#eef0ed"><main style="padding:48px"><h1>研究工作区</h1><p>浏览器交互测试 · 模拟宿主 RPC</p><div id="settings"></div></main><div id="overlay"></div></body></html>')
  await page.addScriptTag({ path: path.join(modules, 'react/umd/react.development.js') })
  await page.addScriptTag({ path: path.join(modules, 'react-dom/umd/react-dom.development.js') })
  await page.evaluate(() => {
    const listeners = new Set()
    window.fixture = { sid: 'a', enabled: true, calls: [], delayA: 0, restoreDelayA: 0, restoreConflict: true, restoreRevision: 41,
      checkpoints: { a: [{ checkpoint_id: 'checkpoint_aaaaaaaaaaaaaaaa', name: '已验收基线', created_at: '2026-09-22T07:00:00Z', completed_when_created: true }], b: [{ checkpoint_id: 'checkpoint_bbbbbbbbbbbbbbbb', name: '项目 B 草稿', created_at: '2026-09-22T07:30:00Z', completed_when_created: false }] },
      change(id) { this.sid = id; listeners.forEach(fn => fn()) } }
    const fixture = window.fixture
    const state = sid => ({ initialized: true, stale: true, snapshotAt: '2026-09-22T08:00:00Z', project: { title: sid === 'a' ? '城市能源调度研究' : '第二个独立项目', scope: 'programming' }, currentPhase: 'programming',
      completed: false, blockers: ['P2：结果表尚未关联实际运行'], progress: { steps: [{ key: 'programming', label: '编程求解', status: 'current' }], tasks: { programming: { done: 4, total: 6, pct: 67 } } },
      gates: { P1: { status: 'PASS' }, P2: { status: 'BLOCKED' } }, capabilities: { python: true }, artifacts: [{ id: 'a1', kind: 'table', question: 'q1', path: 'results/answer.csv', sha256: 'a'.repeat(64) }],
      claims: [{ id: 'c1', text: '方案 A 的成本最低', artifact_ids: ['a1'], locator: '第 2 行' }], runs: [{ run_id: 'r1', argv: ['python', 'solver.py'], exit_code: 0 }], checkpoints: fixture.checkpoints[sid], ledgerTail: [{ at: '2026-09-22T08:00:00Z', event: 'run.completed' }] })
    window.__ModuleLoader__ = { load({ factory }) {
      const plugin = factory(name => { if (name === 'react') return React; throw new Error(name) })
      const rpc = async (_channel, endpoint, payload) => {
        fixture.calls.push({ endpoint, payload })
        if (endpoint === 'mm.state') {
          if (payload.sessionId === 'a' && fixture.delayA) await new Promise(resolve => setTimeout(resolve, fixture.delayA))
          return { ok: true, value: fixture.enabled ? { ...state(payload.sessionId), stale: !payload.refresh } : { hidden: true } }
        }
        if (endpoint === 'mm.artifact') return { ok: true, value: { content: '方案,cost\nA,42\nB,67', path: payload.path } }
        if (endpoint === 'mm.runLog') return { ok: true, value: { content: 'solver finished: objective=42', truncated: false } }
        if (endpoint === 'mm.checkpointCreate') {
          const checkpoint = { checkpoint_id: 'checkpoint_cccccccccccccccc', name: '工作台新快照', created_at: '2026-09-22T08:30:00Z', completed_when_created: false }
          fixture.checkpoints[payload.sessionId].push(checkpoint)
          return { ok: true, value: { ok: true, checkpoint } }
        }
        if (endpoint === 'mm.checkpointRestore') {
          if (payload.sessionId === 'a' && fixture.restoreDelayA) await new Promise(resolve => setTimeout(resolve, fixture.restoreDelayA))
          if (!payload.apply) return { ok: true, value: { preview: true, checkpoint_id: payload.checkpoint_id, expected_revision: fixture.restoreRevision, changes: [{ path: 'restored.csv', operation: 'add' }, { path: 'solver.py', operation: 'replace' }, { path: 'draft.txt', operation: 'remove' }] } }
          if (fixture.restoreConflict) { fixture.restoreConflict = false; fixture.restoreRevision++; return { ok: false, error: { code: 'revision_conflict', message: 'Project or checkpoint changed since restore preview; preview again' } } }
          return { ok: true, value: { restored: payload.checkpoint_id } }
        }
        if (endpoint === 'mm.setEnabled') fixture.enabled = payload.enabled
        return { ok: true, value: { enabled: fixture.enabled, persistent: true } }
      }
      plugin.apply({
        on() {}, connection: { rpc: { call: rpc } },
        sessions: { list: { getSnapshot: () => ({ byId: { a: { id: 'a', retainedBy: { mainView: fixture.sid === 'a' ? 1 : 0 } }, b: { id: 'b', retainedBy: { mainView: fixture.sid === 'b' ? 1 : 0 } } } }), subscribe: fn => { listeners.add(fn); return () => listeners.delete(fn) } } },
        slots: { inject: (_name, callback) => callback(), register: (definition, Component) => {
          const target = document.getElementById(definition.name === 'shell.overlay' ? 'overlay' : 'settings')
          ReactDOM.createRoot(target).render(React.createElement(Component, definition.inject?.() || {}))
        } },
      })
    } }
  })
  await page.addScriptTag({ path: path.join(repo, 'dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui/client/client.js') })
  await page.getByRole('button', { name: '展开项目看板' }).click()
  await page.getByRole('heading', { name: '城市能源调度研究' }).waitFor()
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
  assert.equal(await page.getByRole('button', { name: '确认恢复', exact: true }).count(), 0)
  await page.getByRole('button', { name: '创建快照', exact: true }).click()
  await page.getByText('快照已创建。', { exact: true }).waitFor()
  await page.getByText('工作台新快照', { exact: true }).waitFor()
  await page.getByRole('button', { name: '预览恢复 已验收基线', exact: true }).click()
  const restorePreview = page.getByRole('region', { name: '恢复预览' })
  await restorePreview.waitFor()
  assert.match(await restorePreview.innerText(), /新增 \(add\).*restored.csv/s)
  assert.match(await restorePreview.innerText(), /替换 \(replace\).*solver.py/s)
  assert.match(await restorePreview.innerText(), /删除 \(remove\).*draft.txt/s)
  assert.equal(await page.evaluate(() => fixture.calls.filter(call => call.endpoint === 'mm.checkpointRestore' && call.payload.apply).length), 0, 'preview must never apply restoration')
  if (process.env.DSH_CHECKPOINT_SCREENSHOT) await page.screenshot({ path: process.env.DSH_CHECKPOINT_SCREENSHOT, fullPage: true })
  await page.getByRole('button', { name: '确认恢复', exact: true }).click()
  await page.getByRole('alert').filter({ hasText: 'revision_conflict: Project or checkpoint changed since restore preview; preview again' }).waitFor()
  assert.equal(await page.getByRole('button', { name: '确认恢复', exact: true }).count(), 0, 'conflict requires another preview')
  await page.getByRole('button', { name: '预览恢复 已验收基线', exact: true }).click()
  await page.getByRole('button', { name: '确认恢复', exact: true }).click()
  await page.getByRole('status').filter({ hasText: 'mm_complete 重新验收' }).waitFor()
  assert.deepEqual(await page.evaluate(() => fixture.calls.filter(call => call.endpoint === 'mm.checkpointRestore' && call.payload.apply).map(call => call.payload)), [
    { sessionId: 'a', checkpoint_id: 'checkpoint_aaaaaaaaaaaaaaaa', apply: true, expected_revision: 41 },
    { sessionId: 'a', checkpoint_id: 'checkpoint_aaaaaaaaaaaaaaaa', apply: true, expected_revision: 42 },
  ])
  await page.getByRole('button', { name: '预览恢复 已验收基线', exact: true }).click()
  await restorePreview.waitFor()
  await page.evaluate(() => fixture.change('b'))
  await page.getByRole('heading', { name: '第二个独立项目' }).waitFor()
  assert.equal(await page.getByRole('button', { name: '确认恢复', exact: true }).count(), 0)
  await page.getByText('项目 B 草稿', { exact: true }).waitFor()
  await page.evaluate(() => { fixture.change('a'); fixture.restoreDelayA = 180 })
  await page.getByRole('button', { name: '预览恢复 已验收基线', exact: true }).click()
  await page.evaluate(() => fixture.change('b'))
  await page.getByRole('heading', { name: '第二个独立项目' }).waitFor()
  await page.waitForTimeout(250)
  assert.equal(await page.getByRole('button', { name: '确认恢复', exact: true }).count(), 0, 'late preview from another session must be discarded')
  assert.equal(await page.evaluate(() => fixture.calls.filter(call => call.endpoint === 'mm.checkpointRestore' && call.payload.apply).length), 2)
  await page.evaluate(() => { fixture.restoreDelayA = 0; fixture.change('a') })
  await page.getByRole('heading', { name: '城市能源调度研究' }).waitFor()
  await page.getByRole('tab', { name: '项目', exact: true }).click()
  if (process.env.DSH_UI_SCREENSHOT) await page.screenshot({ path: process.env.DSH_UI_SCREENSHOT, fullPage: true })
  await page.evaluate(() => { fixture.delayA = 180 })
  await page.getByRole('button', { name: '重新验证' }).click()
  await page.evaluate(() => fixture.change('b'))
  await page.getByRole('heading', { name: '第二个独立项目' }).waitFor()
  await page.waitForTimeout(250)
  assert.equal(await page.getByRole('heading', { name: '城市能源调度研究' }).count(), 0)
  await page.setViewportSize({ width: 390, height: 780 })
  const box = await page.getByRole('complementary').boundingBox()
  assert.ok(box.x >= 0 && box.x + box.width <= 390)
  await page.getByRole('button', { name: '收起项目看板' }).click()
  await page.getByRole('switch').click()
  assert.equal(await page.getByRole('switch').getAttribute('aria-checked'), 'false')
  await page.getByRole('complementary').waitFor({ state: 'hidden' })
  assert.deepEqual(errors, [])
  t.diagnostic('Real Edge + React render; host RPC/session fixture, not a full DSH desktop E2E test.')
})
