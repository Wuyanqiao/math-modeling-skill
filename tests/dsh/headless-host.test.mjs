import test from 'node:test'
import assert from 'node:assert/strict'
import * as fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createHash } from 'node:crypto'

const modules = process.env.DSH_TEST_NODE_MODULES
const repo = fileURLToPath(new URL('../../', import.meta.url))

test('official host: preset projection, lazy init, saved context and 20MiB upload through fs/shell', { skip: !modules, timeout: 120000 }, async t => {
  const load = name => import(pathToFileURL(path.join(modules, '@deepseek-ai', name, 'lib/index.js')))
  const { Context } = await load('cordis')
  const base = await fs.mkdtemp(path.join(os.tmpdir(), 'mathmodel-host-upload-'))
  const ctx = new Context(), fibers = []
  t.after(async () => {
    await ctx.fiber.dispose()
    assert.equal(path.dirname(path.resolve(base)), path.resolve(os.tmpdir()))
    assert.ok(path.basename(base).startsWith('mathmodel-host-upload-'))
    await fs.rm(base, { recursive: true, force: true })
  })
  const mount = async name => { const module = await load(name); const fiber = await ctx.plugin(module.default || module, { cwd: base }); fibers.push(fiber); return fiber }
  await mount('dsh-fs-local'); await mount('dsh-subprocess-local'); await mount(process.platform === 'win32' ? 'dsh-pwsh-local' : 'dsh-bash-local')
  await mount('dsh-system-prompt'); await mount('dsh-tools'); await mount('dsh-session'); await mount('dsh-agent'); await mount('dsh-session-projection')
  const { agentPresetProjectionDefinition } = await load('dsh-agent-preset-registry')
  ctx.sessionProjections.register(agentPresetProjectionDefinition)
  const session = ctx.sessions.create('upload-session', { meta: { cwd: base, agentPreset: 'standard' } })
  let value = { enabled: true, bindings: { 'upload-session': { cwd: base, projectRoot: base, skillRoot: repo } } }
  let rpc
  ctx.reflect.provide('settings', { describe: () => [{ ns: 'dsh-math-modeling-ui', revision: 1, value }], update: async (_ns, patch) => { value = { ...value, ...patch } } })
  ctx.reflect.provide('agentPresets', { compositionInventory: async () => [{ id: 'native-renamed-math', name: '数学建模 Workbench', rows: [{ enabled: true, moduleName: 'dsh-math-modeling-ui/workbench', fiberState: 2 }] }] })
  ctx.reflect.provide('connection', { rpc: { handle: (_channel, callback) => { rpc = callback; return () => {} } } })
  await ctx.plugin(await import(new URL('../../dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui/lib/index.js', import.meta.url)))
  await ctx.plugin(await import(new URL('../../dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui/lib/workbench.js', import.meta.url)))
  assert.equal((await rpc('mm.context', { sessionId: session.id })).value.eligible, false)
  session.append('agent-preset/selected', { agentPreset: 'native-renamed-math' })
  assert.equal(session.header.agentPreset, 'standard', 'creation metadata stays unchanged')
  assert.equal((await rpc('mm.context', { sessionId: session.id })).value.eligible, true, 'actual projection observes the selection event')
  const initialized = await Promise.all([rpc('mm.ensureProject', { sessionId: session.id }), rpc('mm.ensureProject', { sessionId: session.id })])
  assert.ok(initialized.every(result => result.ok && result.value.initialized), JSON.stringify(initialized))
  assert.equal(initialized[0].value.project.project_id, initialized[1].value.project.project_id)
  const statePath = path.join(base, '.math-modeling/state.json')
  const legacy = JSON.parse(await fs.readFile(statePath, 'utf8'))
  legacy.project.paperRequirements = '旧项目保存的要求'
  delete legacy.project.graphicsTools; delete legacy.inputs; delete legacy.agent_context
  await fs.writeFile(statePath, JSON.stringify(legacy))
  const resumed = await rpc('mm.ensureProject', { sessionId: session.id })
  assert.equal(resumed.ok, true, JSON.stringify(resumed))
  assert.equal(resumed.value.project.project_id, legacy.project.project_id)
  assert.equal(resumed.value.project.paperRequirements.text, '旧项目保存的要求', 'opening an existing project runs the actual migration')
  const requirements = '用户要求保留公式推导' + '汉'.repeat(29990)
  assert.equal(requirements.length, 30000)
  const configured = await rpc('mm.configure', { sessionId: session.id, settings: { optional_collab: { literature: true, prototype: false }, graphics_tools: { drawio: true, seaborn: false }, paper_requirements: { text: requirements, source: 'user' } } })
  assert.equal(configured.ok, true, JSON.stringify(configured))
  const snapshot = (await rpc('mm.state', { sessionId: session.id })).value
  assert.equal(snapshot.project.optionalCollab.literature, true)
  assert.equal(snapshot.project.optionalCollab.prototype, false)
  assert.equal(snapshot.project.graphicsTools.drawio, true)
  assert.equal(snapshot.project.paperRequirements.text, requirements, '30000 Chinese characters survive the real shell stdin transport')
  const assembly = await ctx.systemPrompt.assemble({ agent: { session } })
  const context = assembly.contexts.find(item => item.name === 'math-modeling-project')
  assert.match(context.text, /用户要求保留公式推导/)
  assert.match(context.text, /mm_context/)
  assert.equal(assembly.sections.some(item => item.text.includes('用户要求保留公式推导')), false, 'uploaded user configuration is not elevated into system sections')

  const raw = Buffer.alloc(20 * 1024 * 1024, 0xa5)
  const begun = await rpc('mm.importBegin', { sessionId: session.id, kind: 'attachment', filename: "样本 ' $.bin", size: raw.length })
  assert.equal(begun.ok, true, JSON.stringify(begun))
  const { upload_id, chunk_bytes } = begun.value
  for (let offset = 0, index = 0; offset < raw.length; offset += chunk_bytes, index++) {
    const result = await rpc('mm.importChunk', { sessionId: session.id, upload_id, index, content_base64: raw.subarray(offset, offset + chunk_bytes).toString('base64') })
    assert.equal(result.ok, true, JSON.stringify(result))
    assert.equal(result.value.received_bytes, Math.min(raw.length, offset + chunk_bytes))
  }
  const imported = await rpc('mm.importCommit', { sessionId: session.id, upload_id })
  assert.equal(imported.ok, true, JSON.stringify(imported))
  assert.equal(imported.value.input.bytes, raw.length)
  assert.equal(imported.value.input.sha256, createHash('sha256').update(raw).digest('hex'))
  assert.deepEqual(await fs.readFile(path.join(base, imported.value.input.path)), raw)
  await assert.rejects(fs.stat(path.join(base, '.math-modeling/incoming', upload_id)), { code: 'ENOENT' })
  const canceled = await rpc('mm.importBegin', { sessionId: session.id, kind: 'attachment', filename: 'cancel.txt', size: 3 })
  await rpc('mm.importChunk', { sessionId: session.id, upload_id: canceled.value.upload_id, index: 0, content_base64: 'YWJj' })
  assert.equal((await rpc('mm.importCancel', { sessionId: session.id, upload_id: canceled.value.upload_id })).ok, true)
  await assert.rejects(fs.stat(path.join(base, '.math-modeling/incoming', canceled.value.upload_id)), { code: 'ENOENT' })
  t.diagnostic('Actual official fs.writeText(createIfAbsent), shell.execute/result and SessionProjection selection event; actual shared CLI; exact 20MiB hash verified. Preset inventory, settings and RPC transport are in-process fixtures. No personal profile mutated.')
})

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
  const stateBeforeEnvironment = await fs.readFile(path.join(custom, '.math-modeling/state.json'), 'utf8')
  const environment = await call('mm_environment')
  assert.equal(environment.ok, true, JSON.stringify(environment))
  assert.equal(typeof environment.ready, 'boolean')
  assert.ok(path.isAbsolute(environment.executable), 'the report must identify the actual Python executable')
  assert.ok((await fs.stat(environment.executable)).isFile())
  assert.match(environment.python, /^\d+\.\d+/)
  assert.equal(environment.platform, process.platform)
  assert.ok(Number.isFinite(Date.parse(environment.checked_at)))
  assert.ok(environment.items.length > 0)
  for (const item of environment.items) {
    assert.ok(['required', 'selected', 'optional'].includes(item.requirement))
    assert.ok(['ready', 'missing', 'error', 'manual'].includes(item.status))
    assert.equal(typeof item.agent_prompt, 'string')
    assert.ok(item.install_command === null || typeof item.install_command === 'string')
  }
  assert.equal(await fs.readFile(path.join(custom, '.math-modeling/state.json'), 'utf8'), stateBeforeEnvironment, 'environment detection must not rewrite project state')
  t.diagnostic(`Actual saved-project dependency report: Python ${environment.python}; ${environment.items.length} items; ready=${environment.ready}; no installation requested.`)
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
    assert.equal(path.dirname(path.resolve(base)), path.dirname(path.resolve(modules)))
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
