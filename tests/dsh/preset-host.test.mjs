import test from 'node:test'
import assert from 'node:assert/strict'
import * as fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'

const modules = process.env.DSH_TEST_NODE_MODULES
const packageRoot = fileURLToPath(new URL('../../dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui/', import.meta.url))

test('official preset registry rejects leaked workbench service and creates isolated math sessions', { skip: !modules, timeout: 60000 }, async t => {
  const load = name => import(pathToFileURL(path.join(modules, '@deepseek-ai', name, 'lib/index.js')))
  const { boot } = await load('dsh-app-boot')
  const { entryListSchema } = await load('cordis-plugin-include')
  const { leakedServices, livePresetMounts } = await load('dsh-agent-preset-registry')
  const { scopeOf } = await load('dsh-scope')
  const yaml = createRequire(path.join(modules, '@deepseek-ai/dsh-app-boot/package.json'))('js-yaml')
  const patch = yaml.load(await fs.readFile(path.join(packageRoot, 'cordis.patch.yml'), 'utf8'), { schema: entryListSchema })
  const shippedPreset = patch[0].insert.find(row => row.id === 'preset-math-modeling').config
  const shippedWorkbench = shippedPreset.plugins.find(row => row.id === 'math-modeling')
  const workbench = { ...structuredClone(shippedWorkbench), name: pathToFileURL(path.join(packageRoot, 'lib/workbench.js')).href }
  const base = await fs.mkdtemp(path.join(os.tmpdir(), 'mathmodel-preset-host-'))
  let ctx, rpc
  const handles = [], releases = []
  t.after(async () => {
    for (const handle of handles.reverse()) await handle.dispose()
    for (const release of releases.reverse()) await release()
    if (ctx) await ctx.fiber.dispose()
    assert.equal(path.dirname(path.resolve(base)), path.resolve(os.tmpdir()))
    assert.ok(path.basename(base).startsWith('mathmodel-preset-host-'))
    await fs.rm(base, { recursive: true, force: true })
  })
  const entry = (name, config = {}) => ({ id: name, name: pathToFileURL(path.join(modules, '@deepseek-ai', name, 'lib/index.js')).href, config })
  const rows = [entry('dsh-fs-local', { cwd: base }), entry('dsh-subprocess-local'), entry(process.platform === 'win32' ? 'dsh-pwsh-local' : 'dsh-bash-local', { cwd: base }),
    entry('dsh-tools'), entry('dsh-system-prompt'), entry('dsh-session'), entry('dsh-agent'), entry('dsh-session-projection'), entry('dsh-llm'), entry('dsh-agent-loop'),
    entry('dsh-agent-preset-registry', { default: 'standard' }), { id: 'dsh-math-modeling-ui', name: pathToFileURL(path.join(packageRoot, 'lib/index.js')).href }]
  const configPath = path.join(base, 'cordis.json')
  await fs.writeFile(configPath, JSON.stringify(rows))
  ctx = await boot('mathmodel-preset-test', configPath, [], context => {
    context.provide('settings', { describe: () => [{ ns: 'dsh-math-modeling-ui', revision: 1, value: { enabled: true, bindings: {} } }] })
    context.provide('connection', { rpc: { handle: (_channel, callback) => { rpc = callback; return () => {} } } })
  }, pathToFileURL(path.join(modules, '@deepseek-ai/dsh/package.json')).href)

  const register = async (id, plugins) => {
    releases.push(await ctx.agentPresets.register({ id, name: id, plugins }))
    return ctx.agentPresets.resolve(id)
  }
  const create = (sessionId, presetId, cwd = base) => ctx.agents.create({ sessionId, meta: { cwd, agentPreset: presetId },
    setup: agentCtx => ctx.agentPresets.mount(agentCtx, presetId).then(() => {}) })
  const legacy = structuredClone(workbench)
  delete legacy.isolate
  const broken = await register('legacy-unisolated', [legacy])
  assert.match(broken.broken, /Preset services require isolate realms: mathModelWorkbench/)
  await assert.rejects(create('rejected-session', 'legacy-unisolated'), error => {
    assert.equal(error.code, 'agent-preset/invalid')
    assert.match(error.message, /Preset services require isolate realms: mathModelWorkbench/)
    return true
  })
  assert.equal(ctx.agents.get('rejected-session'), undefined)
  assert.equal(ctx.sessions.get('rejected-session'), undefined, 'invalid preset creation must not publish a session')
  assert.equal(ctx.get('mathModelWorkbench'), undefined, 'failed activation disposes the leaked provider')

  assert.equal(workbench.isolate?.mathModelWorkbench, true, 'the shipped YAML must declare the capability realm')
  assert.equal((await register('math-modeling', [workbench])).broken, undefined)
  assert.equal((await register('renamed-math', [workbench])).broken, undefined)
  assert.equal((await register('standard', [])).broken, undefined)
  const cases = [['math-a', 'math-modeling', true], ['math-b', 'math-modeling', true], ['math-renamed', 'renamed-math', true], ['plain', 'standard', false]]
  for (const [sessionId, presetId, eligible] of cases) {
    const cwd = path.join(base, sessionId)
    await fs.mkdir(cwd)
    const handle = await create(sessionId, presetId, cwd)
    handles.push(handle)
    const agent = handle.agent
    assert.equal(ctx.agents.get(sessionId), agent)
    assert.equal(ctx.sessions.get(sessionId), agent.session)
    assert.equal(ctx.agentPresets.composedPreset(agent.ctx), presetId)
    assert.equal(ctx.agentPresets.serviceFor(agent, 'mathModelWorkbench')?.version, eligible ? 2 : undefined)
    assert.equal(!!ctx.tools.get('mm_project_init', scopeOf(agent.ctx)), eligible, 'tools resolve only in the selected preset scope')
    const result = await rpc('mm.context', { sessionId })
    assert.equal(result.ok, true, JSON.stringify(result))
    assert.equal(result.value.eligible, eligible, JSON.stringify(result))
    assert.equal(result.value.initialized, false)
    assert.equal(result.value.session.hasWorkbench, eligible)
    assert.equal(result.value.session.id, sessionId)
    assert.equal(result.value.session.cwd, cwd)
  }
  assert.equal(ctx.get('mathModelWorkbench'), undefined, 'no math capability reaches the root realm')
  assert.equal(ctx.tools.get('mm_project_init'), undefined, 'no math tool reaches the host scope')
  for (const mount of livePresetMounts(ctx.fiber)) assert.deepEqual(leakedServices(ctx, mount.fiber), [])
  assert.notEqual(ctx.agentPresets.serviceFor(handles[0].agent, 'mathModelWorkbench'), ctx.agentPresets.serviceFor(handles[2].agent, 'mathModelWorkbench'), 'different presets own different provider objects')
  t.diagnostic('Actual official Loader, preset mount/leakedServices assertion, AgentLoop factory, session publication, scoped tools, registry.serviceFor and UI context RPC; no model request, user profile change or installation. Settings and RPC transport are in-process fixtures.')
})
