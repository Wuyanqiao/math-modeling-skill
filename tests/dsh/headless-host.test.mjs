import test from 'node:test'
import assert from 'node:assert/strict'
import * as fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const modules = process.env.DSH_TEST_NODE_MODULES
const repo = fileURLToPath(new URL('../../', import.meta.url))

test('official DSH 0.1.7 services mount workbench and execute shared CLI', { skip: !modules, timeout: 120000 }, async t => {
  const load = name => import(pathToFileURL(path.join(modules, '@deepseek-ai', name, 'lib/index.js')))
  const { Context } = await load('cordis')
  const base = await fs.mkdtemp(path.join(os.tmpdir(), 'mathmodel-real-host-'))
  t.after(async () => {
    assert.equal(path.dirname(path.resolve(base)), path.resolve(os.tmpdir()))
    assert.ok(path.basename(base).startsWith('mathmodel-real-host-'))
    await fs.rm(base, { recursive: true, force: true })
  })
  const cwd = path.join(base, 'workspace')
  const custom = path.join(base, 'custom 中文')
  await fs.mkdir(cwd); await fs.mkdir(custom)
  const ctx = new Context()
  const fibers = []
  t.after(async () => { for (const fiber of fibers.reverse()) await fiber.dispose() })
  const mount = async (name, config = {}) => {
    const module = await load(name)
    const fiber = await ctx.plugin(module.default || module, config)
    fibers.push(fiber)
    return fiber
  }
  await mount('dsh-fs-local', { cwd })
  await mount('dsh-subprocess-local')
  await mount(process.platform === 'win32' ? 'dsh-pwsh-local' : 'dsh-bash-local', { cwd })
  await mount('dsh-system-prompt', { includeHarnessIdentity: false })
  await mount('dsh-tools')
  await mount('dsh-session')
  await mount('dsh-agent')
  await mount('dsh-skill')
  const session = ctx.sessions.create('isolated-real-session', { meta: { cwd } })
  const plugin = await import(new URL('../../dsh-plugin/math-modeling-agent/plugins/math-modeling.js', import.meta.url))
  fibers.push(await ctx.plugin(plugin))
  assert.ok(ctx.tools.get('mm_project_init'))
  assert.ok(ctx.skills.get('math-modeling'))
  const call = (name, args = {}) => ctx.agents.withInitiator({ id: 'isolated-real-author', session }, () => ctx.tools.get(name).execute(args))
  const initialized = await call('mm_project_init', { projectRoot: custom, skillRoot: repo, title: "真实 DSH ' & $(echo should-not-run)", scope: 'modeling' })
  assert.equal(initialized.ok, true, JSON.stringify(initialized))
  assert.equal(initialized.project.projectRoot, await fs.realpath(custom))
  assert.equal(initialized.project.authorId, 'isolated-real-author')
  assert.match(initialized.bindingNotice, /当前进程/)
  const state = await call('mm_state')
  assert.equal(state.project.projectRoot, await fs.realpath(custom))
  const phase = await call('mm_phase_enter', { phase: 'modeling' })
  assert.equal(phase.ok, true, JSON.stringify(phase))
  assert.match(phase.skillMd, /建模/)
  const incomplete = await call('mm_complete')
  assert.equal(incomplete.done, false)
  assert.ok(incomplete.blockers.length)
  assert.equal((await fs.readdir(cwd)).length, 0)
  const otherSession = ctx.sessions.create('isolated-second-session', { meta: { cwd } })
  const otherCall = (name, args = {}) => ctx.agents.withInitiator({ id: 'second-author', session: otherSession }, () => ctx.tools.get(name).execute(args))
  assert.equal((await otherCall('mm_project_init', { skillRoot: repo, title: 'Second', scope: 'modeling' })).ok, true)
  assert.equal((await otherCall('mm_state')).project.title, 'Second')
  assert.equal((await call('mm_state')).project.title, initialized.project.title)
  await fibers.pop().dispose()
  fibers.push(await ctx.plugin(plugin))
  assert.equal((await otherCall('mm_state')).project.title, 'Second')
  // This minimal host has no persistent SettingsForms; explicit custom root is
  // therefore supplied on reattachment, as the init bindingNotice instructs.
  assert.equal((await call('mm_state', { projectRoot: custom, skillRoot: repo })).project.title, initialized.project.title)
  t.diagnostic(`Actual services: @deepseek-ai/dsh 0.1.7-alpha.1; Node ${process.version}; ${process.platform}; real fs + shell.execute(spec).result() + tools + sessions + initiator; no GUI/model/settings persistence asserted.`)
})

test('official Loader + SettingsForms persist shared UI and project bindings across boot', { skip: !modules, timeout: 120000 }, async t => {
  const load = name => import(pathToFileURL(path.join(modules, '@deepseek-ai', name, 'lib/index.js')))
  const { boot, readProfilePatches } = await load('dsh-app-boot')
  const base = await fs.mkdtemp(path.join(path.dirname(modules), 'mathmodel-profile-'))
  const packageRoot = path.join(base, 'node_modules/dsh-math-modeling-ui')
  await fs.cp(path.join(repo, 'dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui'), packageRoot, { recursive: true })
  const workspace = path.join(base, 'workspace'), custom = path.join(base, 'custom')
  await fs.mkdir(workspace); await fs.mkdir(custom)
  const bundle = path.join(base, 'node_modules/dsh-test-bundle')
  await fs.mkdir(bundle, { recursive: true })
  const entry = (id, name, config = {}) => ({ id, name: pathToFileURL(path.join(modules, '@deepseek-ai', name, 'lib/index.js')).href, config })
  const rows = [entry('fs', 'dsh-fs-local', { cwd: workspace }), entry('subprocess', 'dsh-subprocess-local'), entry('shell', process.platform === 'win32' ? 'dsh-pwsh-local' : 'dsh-bash-local', { cwd: workspace }),
    entry('system-prompt', 'dsh-system-prompt'), entry('tools', 'dsh-tools'), entry('sessions', 'dsh-session'), entry('agents', 'dsh-agent'), entry('config-editor', 'dsh-config-editor'), entry('settings', 'dsh-settings'),
    { id: 'dsh-math-modeling-ui', name: pathToFileURL(path.join(packageRoot, 'lib/index.js')).href },
    { id: 'mathmodel-tools', name: pathToFileURL(path.join(packageRoot, 'lib/workbench.js')).href }]
  await fs.writeFile(path.join(bundle, 'package.json'), JSON.stringify({ name: 'dsh-test-bundle', version: '1.0.0', dsh: { bundle: { patch: './cordis.patch.json' } } }))
  await fs.writeFile(path.join(bundle, 'cordis.patch.json'), JSON.stringify([{ insert: rows }]))
  await fs.writeFile(path.join(base, 'package.json'), JSON.stringify({ name: 'dsh-profile-test', private: true, dsh: { profile: { bundles: ['dsh-test-bundle'] } } }))
  await fs.writeFile(path.join(base, 'cordis.yml'), '[]\n')
  const profile = { name: 'test', dir: base, patchPath: path.join(base, 'cordis.patch.yml'), installAnchor: path.join(modules, '@deepseek-ai/dsh/package.json'), cwd: workspace, home: path.join(base, 'isolated-home'), startedBundles: ['dsh-test-bundle'], overlays: [] }
  let ctx, rpc
  t.after(async () => {
    if (ctx) await ctx.fiber.dispose()
    assert.equal(path.dirname(base), path.dirname(modules))
    assert.ok(path.basename(base).startsWith('mathmodel-profile-'))
    await fs.rm(base, { recursive: true, force: true })
  })
  async function open() {
    ctx = await boot('mathmodel-test', path.join(base, 'cordis.yml'), readProfilePatches('mathmodel-test', profile), context => {
      context.provide('profileContext', profile)
      context.provide('connection', { rpc: { handle: (_channel, callback) => { rpc = callback; return () => {} } } })
    }, pathToFileURL(path.join(modules, '@deepseek-ai/dsh/package.json')).href)
    const session = ctx.sessions.create('persisted-session', { meta: { cwd: workspace } })
    return (name, args = {}) => ctx.agents.withInitiator({ id: 'persisted-author', session }, () => ctx.tools.get(name).execute(args))
  }
  let call = await open()
  assert.ok(ctx.settings.describe().some(item => item.ns === 'dsh-math-modeling-ui'))
  const initialized = await call('mm_project_init', { projectRoot: custom, skillRoot: repo, title: 'Persistent custom', scope: 'modeling' })
  assert.equal(initialized.ok, true, JSON.stringify(initialized))
  const toggled = await rpc('mm.setEnabled', { enabled: false })
  assert.equal(toggled.ok, true, JSON.stringify(toggled))
  assert.equal((await call('mm_ui_toggle', { action: 'get' })).enabled, false)
  assert.match(await fs.readFile(profile.patchPath, 'utf8'), /persisted-session/)
  await ctx.fiber.dispose(); ctx = null
  call = await open()
  assert.equal((await call('mm_state')).project.title, 'Persistent custom')
  assert.equal((await rpc('mm.getEnabled')).value.enabled, false)
  assert.equal((await call('mm_ui_toggle', { action: 'on' })).ok, true)
  assert.equal((await rpc('mm.state', { sessionId: 'persisted-session' })).value.project.title, 'Persistent custom')
  t.diagnostic('Real Loader, Config, config-editor, SettingsForms and profile patch persistence; RPC transport is an in-process fixture.')
})
