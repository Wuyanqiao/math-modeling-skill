import test from 'node:test'
import assert from 'node:assert/strict'
import * as fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { randomUUID } from 'node:crypto'
import { TaskStartService } from '../../dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui/lib/task-start.js'

const modules = process.env.DSH_TEST_NODE_MODULES

test('Workbench start reaches the official SessionController and AgentLoop exactly once without a network model', { skip: !modules, timeout: 60000 }, async t => {
  const load = name => import(pathToFileURL(path.join(modules, '@deepseek-ai', name, 'lib/index.js')))
  const { Context } = await load('cordis')
  const { LlmAdapter } = await load('dsh-llm')
  const base = await fs.mkdtemp(path.join(os.tmpdir(), 'mathmodel-start-host-'))
  const ctx = new Context(), handles = [], calls = [], errors = []
  const finish = Promise.withResolvers(), entered = Promise.withResolvers()
  let selection = { provider: 'mathmodel-fixture', model: 'deterministic-test' }
  const network = t.mock.method(globalThis, 'fetch', async () => { throw new Error('Network use is forbidden in the start fixture') })
  t.after(async () => {
    finish.resolve()
    for (const handle of handles.reverse()) await handle.dispose()
    await ctx.fiber.dispose()
    assert.equal(path.dirname(path.resolve(base)), path.resolve(os.tmpdir()))
    assert.ok(path.basename(base).startsWith('mathmodel-start-host-'))
    await fs.rm(base, { recursive: true, force: true })
  })
  const mount = async (name, config = {}) => {
    const module = await load(name)
    return ctx.plugin(module.default || module, config)
  }
  for (const name of ['dsh-session', 'dsh-agent', 'dsh-session-projection', 'dsh-tools', 'dsh-system-prompt', 'dsh-llm', 'dsh-agent-loop']) await mount(name)
  await mount('dsh-fs-local', { cwd: base })
  ctx.on('agent/error', ({ error }) => errors.push(error?.stack || String(error)))
  class DeterministicAdapter extends LlmAdapter {
    async resolveModel(provider, model) { return { provider, id: model, name: model, context: { contextWindow: 8192 }, defaultMaxTokens: 64 } }
    async *stream(options) {
      assert.equal(options.provider, 'mathmodel-fixture')
      calls.push({ sessionId: options.sessionId, messages: options.messages })
      entered.resolve()
      await finish.promise
      options.signal?.throwIfAborted()
      yield { type: 'block-start', index: 0, blockType: 'text' }
      yield { type: 'text-delta', index: 0, text: 'Isolated submission accepted.' }
      yield { type: 'block-end', index: 0, block: { type: 'text', text: 'Isolated submission accepted.' } }
      yield { type: 'usage', usage: { inputTokens: 1, outputTokens: 1 } }
      yield { type: 'finish', reason: { kind: 'stop' } }
    }
  }
  ctx.llm.registerAdapter(['mathmodel-fixture'], new DeterministicAdapter())
  ctx.reflect.provide('agentDefaultModel', { currentSelection: () => selection })
  ctx.reflect.provide('attachments', {
    imageLimits: { maxBytes: 1024, maxImageDimension: 64, mediaTypes: ['image/png'] },
    admitPromptContent: async content => content,
  })
  ctx.reflect.provide('fileUploads', {
    registerAgentResolver: () => () => {},
    bindPrompt: () => ({ commit() {}, [Symbol.dispose]() {} }),
  })
  ctx.reflect.provide('typert', { lookups: { configure() {} }, contexts: { configureHost() {} } })
  ctx.reflect.provide('workspaceRegistry', { list: () => [], archivedSessionIds: [] })
  ctx.reflect.provide('sessionQuery', { listSessions: async () => ctx.sessions.list().map(session => ({ header: session.header })) })
  await mount('dsh-api-session-controller', { nativeOpen: false })
  for (const sessionId of ['start-target', 'untouched-session']) {
    const cwd = path.join(base, sessionId)
    await fs.mkdir(cwd)
    handles.push(await ctx.agents.create({ sessionId, meta: { cwd }, agentOptions: { provider: selection.provider, model: selection.model } }))
    await fs.writeFile(path.join(cwd, 'saved-state.json'), JSON.stringify({ initialized: true, revision: 3,
      project: { project_id: `project-${sessionId}`, projectRoot: cwd, scope: 'modeling' }, currentPhase: 'modeling',
      phases: { modeling: { tasks: [{ text: '核查附件与建模假设', done: false }] } }, gates: { M1: { status: 'pending' } } }))
  }
  const target = handles[0].agent, other = handles[1].agent
  const statePath = id => path.join(base, id, 'saved-state.json')
  const before = await fs.readFile(statePath(target.id))
  const bridge = {
    settings: { read: async () => ({ enabled: true }) },
    path: async value => path.resolve(value),
    context: async (_args, id) => ({ projectRoot: path.join(base, id), skillRoot: path.resolve('test-skill-root'),
      session: { id, cwd: path.join(base, id), value: ctx.sessions.get(id) } }),
    snapshot: async id => JSON.parse(await fs.readFile(statePath(id), 'utf8')),
  }
  const mathSessions = new Set([target.id, other.id])
  const taskContext = { get: name => name === 'agentPresets'
    ? { serviceFor: (agent, capability) => capability === 'mathModelWorkbench' && mathSessions.has(agent.id) ? { version: 2 } : undefined }
    : ctx.get(name) }
  const service = new TaskStartService(taskContext, bridge)
  const options = await service.options(target.id)
  assert.equal(options.available, true)
  assert.deepEqual(options.phases.map(item => item.id), ['modeling'])
  assert.equal((await ctx.sessionController.resolveAgent(target.id)).agent, target, 'public resolver returns an agent envelope')
  const payload = { sessionId: options.sessionId, projectId: options.projectId, projectRoot: options.projectRoot,
    revision: options.revision, requestId: randomUUID(), mode: 'task', phase: 'modeling', taskId: options.phases[0].tasks[0].id }
  await assert.rejects(service.start({ ...payload, requestId: randomUUID(), revision: 2 }), { code: 'stale-project' })
  await assert.rejects(service.start({ ...payload, requestId: randomUUID(), mode: 'stage', phase: 'paper', taskId: undefined }), { code: 'invalid-target' })
  assert.equal(target.session.snapshotEvents().some(event => event.type === 'user/message'), false)
  const [accepted, concurrentRetry] = await Promise.all([service.start(payload), service.start(payload)])
  assert.equal(accepted.accepted, true)
  assert.equal(accepted.sessionId, target.id)
  assert.deepEqual(concurrentRetry, accepted)
  let timer
  try {
    await Promise.race([entered.promise, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`AgentLoop did not enter adapter: ${errors.join('; ')}`)), 10000) })])
  } finally { clearTimeout(timer) }
  assert.equal(target.status, 'running')
  assert.equal(other.status, 'idle')
  assert.equal(calls.length, 1)
  assert.equal(calls[0].sessionId, target.id)
  const count = () => target.session.snapshotEvents().filter(event => event.type === 'user/message' && event.data.source.rpcId === payload.requestId).length
  assert.equal(count(), 1)
  assert.equal((await service.start(payload)).duplicate, true)
  assert.equal(count(), 1, 'same requestId is deduplicated against committed Session history')
  await assert.rejects(service.start({ ...payload, requestId: randomUUID() }), { code: 'session-busy' })
  assert.equal((await service.options(target.id)).busy, true)
  const prompt = target.session.snapshotEvents().find(event => event.type === 'user/message').data.content[0].text
  assert.match(prompt, /本次只执行 modeling 阶段中索引 0/)
  assert.match(prompt, /mm_phase_enter/)
  assert.match(prompt, /独立审查/)
  assert.match(prompt, /不扩展为整阶段或全流程/)
  assert.deepEqual(await fs.readFile(statePath(target.id)), before, 'submission does not mutate project scope, gates, tasks or revision')

  const advanced = JSON.parse(before)
  advanced.revision += 1
  await fs.writeFile(statePath(target.id), JSON.stringify(advanced))
  const { TaskStartService: ReloadedService } = await import(new URL('../../dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui/lib/task-start.js?host-reload', import.meta.url))
  const reloaded = new ReloadedService(taskContext, bridge)
  assert.equal((await reloaded.start(payload)).duplicate, true, 'durable official Session history survives a plugin reload and a later revision')
  assert.equal(count(), 1)
  await assert.rejects(reloaded.start({ ...payload, mode: 'full', phase: undefined, taskId: undefined }), { code: 'request-conflict' })
  assert.equal(other.session.snapshotEvents().some(event => event.type === 'user/message'), false)
  const list = await ctx.sessionController.list({}, new AbortController().signal)
  assert.equal(list.items.find(item => item.sessionId === target.id).running, true)
  selection = { provider: 'missing-fixture-provider', model: 'never-called' }
  const otherOptions = await service.options(other.id)
  const otherPayload = { sessionId: other.id, projectId: otherOptions.projectId, projectRoot: otherOptions.projectRoot,
    revision: otherOptions.revision, requestId: randomUUID(), mode: 'full' }
  await assert.rejects(service.start(otherPayload), error => error.code === 'session/model-unavailable')
  assert.equal(other.session.snapshotEvents().some(event => event.type === 'user/message'), false)
  selection = { provider: 'mathmodel-fixture', model: 'deterministic-test' }
  await other.runMaintenance(async () => {
    await ctx.sessionController.prompt({ sessionId: other.id, requestId: randomUUID(), mode: 'queue', content: [{ type: 'text', text: 'Existing user request.' }] }, new AbortController().signal)
    assert.equal(other.status, 'idle', 'official maintenance reports idle even while a user prompt is queued')
    assert.equal(other.inbox.nextTurn.length, 1)
    assert.equal((await service.options(other.id)).busy, true)
    await assert.rejects(service.start({ ...otherPayload, requestId: randomUUID() }), { code: 'session-busy' })
    await ctx.sessionController.cancel({ sessionId: other.id })
    assert.equal(other.inbox.nextTurn.length, 1, 'official user cancellation preserves queued requests')
    other.cancel({ kind: 'user' })
  })
  mathSessions.delete(other.id)
  assert.equal((await service.options(other.id)).available, false, 'an initialized project alone does not equip a standard agent with math tools')
  await assert.rejects(service.start({ ...otherPayload, requestId: randomUUID() }), { code: 'workbench-not-selected' })
  finish.resolve()
  await target.whenIdle()
  assert.equal(calls.length, 1)
  assert.deepEqual(errors, [])
  assert.equal(target.status, 'idle')
  assert.equal(network.mock.callCount(), 0)
  t.diagnostic('Actual TaskStartService → official SessionController → AgentRegistry/AgentLoop → deterministic in-memory LLM adapter, including the real maintenance/inbox semantics. Bridge reads isolated saved snapshots; capability eligibility, text-only attachments, query and RPC registration are peripheral fixtures. No math tool execution, runtime completion or gate passage is claimed; no profile, API key or network model is loaded.')
})
