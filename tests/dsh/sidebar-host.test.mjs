import test from 'node:test'
import assert from 'node:assert/strict'
import * as fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const modules = process.env.DSH_TEST_NODE_MODULES
const repo = fileURLToPath(new URL('../../', import.meta.url))

// Optional integration environment: the published 0.1.7-alpha.1 browser bundles,
// their development dependencies, esbuild and Playwright. No DSH profile is used.
test('official sidebar registry and renderer: keyed session guide, body and disposal', { skip: !modules, timeout: 90000 }, async t => {
  const { build } = await import(pathToFileURL(path.join(modules, 'esbuild/lib/main.js')))
  const { chromium } = await import(pathToFileURL(path.join(modules, 'playwright/index.mjs')))
  for (const name of ['dsh-client-ui-sidebar-right', 'dsh-client-ui-renderer', 'dsh-client-ui-slots']) {
    const manifest = JSON.parse(await fs.readFile(path.join(modules, '@deepseek-ai', name, 'package.json'), 'utf8'))
    assert.equal(manifest.version, '0.1.7-alpha.1')
  }
  const dependencies = ['react', 'react-dom', 'react-dom/client', 'react/jsx-runtime', '@deepseek-ai/cordis',
    '@deepseek-ai/dsh-client-ui-slots', '@deepseek-ai/dsh-client-store', '@deepseek-ai/dsh-client-ui-primitives', '@deepseek-ai/dsh-client-ui-dockkit']
  const bundled = await build({
    stdin: { contents: dependencies.map((name, i) => `import * as dep${i} from ${JSON.stringify(name)};`).join('\n') +
      '\nwindow.officialDependencies = {' + dependencies.map((name, i) => `${JSON.stringify(name)}:dep${i}`).join(',') + '};', resolveDir: path.dirname(modules) },
    bundle: true, write: false, platform: 'browser', format: 'iife', logLevel: 'silent',
    loader: { '.module.css': 'empty', '.css': 'empty' }, define: { 'process.env.NODE_ENV': '"production"' },
  })
  const browser = await chromium.launch(process.platform === 'win32' ? { channel: 'msedge' } : {})
  const page = await browser.newPage({ viewport: { width: 680, height: 800 } })
  t.after(async () => { try { await page.evaluate(() => window.sidebarFixture?.dispose?.()) } finally { await browser.close() } })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', event => { if (event.type() === 'error') errors.push(event.text()) })
  await page.setContent('<html lang="zh-CN"><body><main id="root"></main></body></html>')
  await page.addScriptTag({ content: bundled.outputFiles[0].text })
  await page.evaluate(() => {
    window.officialPlugins = {}
    window.__ModuleLoader__ = { load({ id, factory }) {
      window.officialPlugins[id] = factory(name => {
        if (!(name in window.officialDependencies)) throw new Error(`Missing official dependency: ${name}`)
        return window.officialDependencies[name]
      })
    } }
  })
  for (const name of ['dsh-client-ui-renderer', 'dsh-client-ui-sidebar-right']) {
    await page.addScriptTag({ path: path.join(modules, '@deepseek-ai', name, 'lib/client.js') })
  }
  await page.addScriptTag({ path: path.join(repo, 'dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui/client/client.js') })
  const registration = await page.evaluate(async () => {
    const deps = window.officialDependencies
    const { Context } = deps['@deepseek-ai/cordis']
    const { createSnapshotStore } = deps['@deepseek-ai/dsh-client-store']
    const React = deps.react, h = React.createElement
    const renderer = window.officialPlugins['@deepseek-ai/dsh-client-ui-renderer']
    const sidebar = window.officialPlugins['@deepseek-ai/dsh-client-ui-sidebar-right']
    const plugin = window.officialPlugins['dsh-math-modeling-ui']
    const fixture = window.sidebarFixture = { calls: [], opens: [], selected: 'a', initialized: { a: true, b: false }, enabled: true }
    const rpc = async (_channel, endpoint, payload) => {
      fixture.calls.push({ endpoint, payload })
      if (endpoint === 'mm.context') return {ok:true,value:{enabled:fixture.enabled,eligible:fixture.enabled && fixture.initialized[payload.sessionId],initialized:fixture.initialized[payload.sessionId]}}
      if (endpoint === 'mm.state' || endpoint === 'mm.ensureProject') return { ok: true, value: fixture.enabled ? {
        initialized: fixture.initialized[payload.sessionId], project: { title: `项目 ${payload.sessionId}`, scope: 'modeling' },
        currentPhase: 'modeling', progress: { steps: [], tasks: {} }, gates: {}, blockers: [],
        artifacts: [], claims: [], runs: [], checkpoints: [], ledgerTail: [],
      } : { hidden: true } }
      if (endpoint === 'mm.getEnabled') return { ok: true, value: { enabled: fixture.enabled } }
      throw new Error(`Unexpected fixture RPC: ${endpoint}`)
    }
    // Mount the unchanged official sidebar with its real registry and SlotCore.
    // Frame services are inert fixtures: no app/session manager or docking UI.
    const registryCtx = new Context()
    await registryCtx.plugin(renderer)
    registryCtx.reflect.provide('layout', {})
    registryCtx.reflect.provide('resources', { pin() {} })
    registryCtx.reflect.provide('sessions', {})
    registryCtx.reflect.provide('uiSession', { adapter: { current: createSnapshotStore({ key: undefined }) } })
    registryCtx.reflect.provide('locale', { bind: () => key => key, register: () => () => {} })
    registryCtx.reflect.provide('connection', { rpc: { call: rpc } })
    await registryCtx.plugin({ inject: ['slots'], apply(ctx) {
      ctx.slots.register({ name: 'root', children: { rightbar: { kind: 'single', scope: 'root' }, 'settings.section': { kind: 'list', scope: 'root' } } }, () => null)
    } })
    await registryCtx.plugin(sidebar)
    const tabs = registryCtx.sidebarRightTabs
    // The published files/terminal definitions use these documented guide orders.
    tabs.register({ id: 'fixture.files', kind: 'files', title: () => '工作区文件', guide: [{ id: 'workspace', order: 10, title: () => '工作区文件' }] })
    tabs.register({ id: 'fixture.terminal', kind: 'terminal', title: () => '新建终端', guide: [{ id: 'new', order: 20, title: () => '新建终端' }] })
    const pluginFiber = await registryCtx.plugin(plugin)
    const definition = tabs.entries().find(item => item.id === 'dsh-math-modeling-ui')
    if (!definition) throw new Error('Workbench did not register an official sidebar tab type')
    const bodySpec = registryCtx.slots.spec('sidebar.right.pane.tab')
    const guideSpec = registryCtx.slots.spec('sidebar.right.tab.guide.entry')
    const guideDefinition = tabs.get('guide')
    const guideEntry = registryCtx.slots.entries('sidebar.right.pane.tab').find(entry => entry.options.key === guideDefinition.id)
    const result = {
      kind: definition.kind, providerId: definition.id,
      guideOrder: tabs.guide().map(entry => ({ kind: entry.kind, order: entry.order, providerId: entry.providerId })),
      body: { kind: bodySpec.kind, scope: bodySpec.scope }, guide: { kind: guideSpec.kind, scope: guideSpec.scope },
      bodyKeys: registryCtx.slots.entries('sidebar.right.pane.tab').map(entry => entry.options.key),
      guideKeys: registryCtx.slots.entries('sidebar.right.tab.guide.entry').map(entry => entry.options.key),
    }
    await pluginFiber.dispose()
    result.disposed = !tabs.get(definition.kind) && !registryCtx.slots.entries('sidebar.right.tab.guide.entry').some(entry => entry.options.key === definition.id)

    // Render the actual GuideBody and workbench through the actual slot renderer.
    // Only their parent frame, session binding and navigation actions are fixtures.
    const ctx = new Context()
    await ctx.plugin(renderer)
    ctx.reflect.provide('sidebarRightTabs', tabs)
    ctx.reflect.provide('connection', { rpc: { call: rpc } })
    const bindings = Object.fromEntries(['a', 'b'].map(sid => [sid, { key: sid, ctx: new Context(), hooks: {}, keyedHooks: {}, props: { sessionId: sid } }]))
    const current = createSnapshotStore(bindings.a)
    ctx.slots.installScope('session', { current, bindingSource: () => current, renderArea: (_binding, props) => props.children?.() })
    const selection = createSnapshotStore({ sessionId: 'a', kind: 'guide' })
    fixture.switchSession = sid => { fixture.selected = sid; current.set(bindings[sid]); selection.set({ sessionId: sid, kind: 'guide' }) }
    fixture.showGuide = () => selection.set({ sessionId: fixture.selected, kind: 'guide' })
    const signal = new AbortController().signal
    await ctx.plugin({ inject: ['slots'], apply(frame) {
      frame.slots.register({ name: 'root', children: { 'sidebar.right.pane.tab': bodySpec, 'settings.section': { kind: 'list', scope: 'root' } }, inject: () => ({ hooks: { selection } }) }, function Surface({ renderSlot, useSelection }) {
        const { sessionId, kind } = useSelection(value => value)
        const tabId = `tab-${sessionId}`
        const layout = { expanded: true, tabs: { [tabId]: { id: tabId, kind, title: kind, contentId: `sidebar://${kind}` } }, nodes: { p: { id: 'p', kind: 'pane', host: 'dock', tabs: [tabId], activeTabId: tabId } } }
        const hookContext = {
          tabId, title: false, fullscreen: false, active: true, signal,
          actions: {
            openTab(nextKind, options) { fixture.opens.push({ sessionId, kind: nextKind, options }); selection.set({ sessionId, kind: nextKind }) },
            close() { fixture.showGuide() },
          },
          useStore: selector => selector({ bySession: { [sessionId]: { layout } } }),
          useTabNavigation: () => ({ address: `sidebar://${kind}`, params: undefined, revision: 1 }),
        }
        return h('section', { style: { height: 700 }, 'data-fixture-session': sessionId }, renderSlot('sidebar.right.pane.tab', {}, { entryKey: tabs.get(kind)?.id, hookContext }))
      })
      frame.slots.register({ name: 'sidebar.right.pane.tab', key: guideDefinition.id, children: guideEntry.children, inject: guideEntry.inject }, guideEntry.component)
    } })
    const workbenchFiber = await ctx.plugin(plugin)
    const unmount = ctx.uiRenderer.mount(document.getElementById('root'))
    fixture.dispose = async () => { unmount(); await workbenchFiber.dispose(); await ctx.fiber.dispose(); await registryCtx.fiber.dispose() }
    fixture.registration = result
    return result
  })
  assert.deepEqual(registration.body, { kind: 'keyed', scope: 'session' })
  assert.deepEqual(registration.guide, { kind: 'keyed', scope: 'session' })
  assert.deepEqual(registration.guideOrder.map(entry => entry.order), [10, 20, 30])
  assert.equal(registration.guideOrder[2].providerId, registration.providerId)
  assert.ok(registration.bodyKeys.includes(registration.providerId))
  assert.ok(registration.guideKeys.includes(registration.providerId))
  assert.equal(registration.disposed, true)
  const card = page.getByRole('button', { name: /数学建模/ })
  await card.waitFor()
  assert.deepEqual((await page.getByRole('button').allTextContents()).map(value => value.trim()).slice(0, 2), ['工作区文件', '新建终端'])
  assert.equal(await card.count(), 1)
  await card.click()
  await page.getByRole('heading', { name: '项目 a' }).waitFor()
  const navigation = await page.evaluate(() => window.sidebarFixture.opens)
  assert.deepEqual(navigation, [{ sessionId: 'a', kind: registration.kind, options: { replaceTab: true } }])
  assert.equal(await page.locator('[data-slot="sidebar.right.pane.tab"]').getByRole('region', { name: '数学建模 Workbench', exact: true }).count(), 1)

  await page.evaluate(() => window.sidebarFixture.switchSession('b'))
  await page.waitForFunction(() => window.sidebarFixture.calls.some(call => call.endpoint === 'mm.context' && call.payload.sessionId === 'b'))
  assert.equal(await card.count(), 0, 'registered null-returning entry must not fall back to the shipped generic guide capsule')
  assert.equal(await page.getByRole('button', { name: '工作区文件' }).count(), 1)
  await page.evaluate(() => window.sidebarFixture.switchSession('a'))
  await card.waitFor()
  assert.equal(await card.count(), 1)
  assert.deepEqual(errors, [])
  t.diagnostic('Actual published @deepseek-ai/dsh-client-ui-sidebar-right + SlotRegistry/SlotCore/GuideBody/renderer/Cordis/React in Edge or Chromium. Frame, sessions, built-in guide definitions, navigation actions and RPC are fixtures; no full DSH GUI or model tested. CSS imports of primitive dependencies omitted for this contract test.')
})
