import test from 'node:test'
import assert from 'node:assert/strict'
import * as fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const modules = process.env.DSH_TEST_NODE_MODULES
const repo = fileURLToPath(new URL('../../', import.meta.url))

test('browser: project, evidence, keyboard tabs, settings and session races', { skip: !modules, timeout: 60000 }, async t => {
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
    window.fixture = { sid: 'a', enabled: true, calls: [], delayA: 0, change(id) { this.sid = id; listeners.forEach(fn => fn()) } }
    const fixture = window.fixture
    const state = sid => ({ initialized: true, stale: true, snapshotAt: '2026-09-22T08:00:00Z', project: { title: sid === 'a' ? '城市能源调度研究' : '第二个独立项目', scope: 'programming' }, currentPhase: 'programming',
      completed: false, blockers: ['P2：结果表尚未关联实际运行'], progress: { steps: [{ key: 'programming', label: '编程求解', status: 'current' }], tasks: { programming: { done: 4, total: 6, pct: 67 } } },
      gates: { P1: { status: 'PASS' }, P2: { status: 'BLOCKED' } }, capabilities: { python: true }, artifacts: [{ id: 'a1', kind: 'table', question: 'q1', path: 'results/answer.csv', sha256: 'a'.repeat(64) }],
      claims: [{ id: 'c1', text: '方案 A 的成本最低', artifact_ids: ['a1'], locator: '第 2 行' }], runs: [{ run_id: 'r1', argv: ['python', 'solver.py'], exit_code: 0 }], ledgerTail: [{ at: '2026-09-22T08:00:00Z', event: 'run.completed' }] })
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
