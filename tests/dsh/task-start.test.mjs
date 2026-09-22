import test from 'node:test'
import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { TaskStartService } from '../../dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui/lib/task-start.js'

function fixture({ scope = 'full' } = {}) {
  const states = new Map(), sessions = new Map(), agents = new Map(), prompts = [], resolutions = []
  let enabled = true, onResolve, onPrompt
  for (const id of ['sidebar', 'global-current']) {
    const root = `/projects/${id}`
    states.set(id, { initialized: true, revision: 7, project: { project_id: `project-${id}`, projectRoot: root, scope },
      currentPhase: scope === 'full' ? 'modeling' : scope, completed: false, gates: { M1: { status: 'passed', evidence: ['keep'] } },
      phases: Object.fromEntries(['modeling', 'programming', 'paper'].map(phase => [phase, { tasks: [{ text: `${phase} 已完成任务`, done: true }, { text: `${phase} 待执行任务`, done: false }] }])) })
    const events = []
    const session = { id, header: { cwd: root }, snapshotEvents: () => events }
    sessions.set(id, session)
    agents.set(id, { id, session, status: 'idle', inbox: { nextTurn: [], nextStep: [] }, maintenance: false,
      ctx: { get: key => key === 'mathModelWorkbench' ? { version: 2 } : undefined },
      async runMaintenance(task) {
        if (this.maintenance || this.status !== 'idle') throw new Error('agent is not idle for maintenance')
        this.maintenance = true
        try { return await task(new AbortController().signal) } finally { this.maintenance = false }
      },
    })
  }
  const bridge = {
    settings: { read: async () => ({ enabled }) },
    async context(_args, id) {
      const session = sessions.get(id)
      if (!session) throw Object.assign(new Error('Session not found'), { code: 'session/not-found' })
      return { session: { id, cwd: session.header.cwd, value: session }, projectRoot: states.get(id).project.projectRoot, skillRoot: '/readonly/Skill 中文' }
    },
    snapshot: async id => structuredClone(states.get(id)), path: async value => value,
  }
  const controller = {
    async resolveAgent(id) { resolutions.push(id); await onResolve?.(id); return { agent: agents.get(id) } },
    async prompt(request, signal) {
      signal.throwIfAborted()
      prompts.push(request)
      if (onPrompt) return onPrompt(request)
      sessions.get(request.sessionId).snapshotEvents().push({ type: 'user/message', data: { content: request.content, source: { kind: 'user', rpcId: request.requestId } } })
      return { accepted: true }
    },
  }
  const services = { sessions: { get: id => sessions.get(id) }, agents: { get: id => agents.get(id) }, sessionController: controller }
  const ctx = { get: key => services[key] }
  const service = new TaskStartService(ctx, bridge)
  return { service, ctx, services, bridge, states, sessions, agents, prompts, resolutions,
    enable: value => { enabled = value }, resolveWith: callback => { onResolve = callback }, promptWith: callback => { onPrompt = callback },
    async request(extra = {}, sessionId = 'sidebar') {
      const value = await service.options(sessionId)
      return { sessionId, projectId: value.projectId, projectRoot: value.projectRoot, revision: value.revision, mode: 'full', requestId: randomUUID(), ...extra }
    },
  }
}

test('start choices use saved scope and task labels, never alter workflow state', async () => {
  const h = fixture({ scope: 'paper' })
  const before = JSON.stringify([...h.states])
  const options = await h.service.options('sidebar')
  assert.equal(options.available, true)
  assert.deepEqual(options.phases.map(item => item.id), ['paper'])
  assert.equal(options.phases[0].tasks[0].done, true, 'completed tasks can be deliberately revisited')
  const payload = await h.request()
  const receipt = await h.service.start(payload)
  assert.equal(receipt.accepted, true)
  assert.deepEqual(receipt.target.phases, ['paper'])
  assert.equal(h.prompts[0].sessionId, 'sidebar', 'the sidebar session wins over any globally selected chat')
  assert.equal(h.prompts[0].mode, 'queue')
  assert.match(h.prompts[0].content[0].text, /scope=paper/)
  assert.match(h.prompts[0].content[0].text, /mm_complete/)
  assert.equal(JSON.stringify([...h.states]), before, 'launching neither resets scope nor rewrites gates or progress')
})

test('phase/task launches bind the exact task and explicitly stop at missing prerequisites', async () => {
  for (const mode of ['stage', 'task']) {
    const h = fixture()
    const options = await h.service.options('sidebar')
    const task = options.phases.find(item => item.id === 'programming').tasks[1]
    const request = await h.request({ mode, phase: 'programming', ...(mode === 'task' ? { taskId: task.id } : {}) })
    await h.service.start(request)
    const prompt = h.prompts[0].content[0].text
    assert.match(prompt, /mm_phase_enter/)
    assert.match(prompt, /停止并报告，不自动执行其他阶段/)
    assert.match(prompt, /不得调用初始化、重置清单或更改配置/)
    if (mode === 'task') {
      assert.match(prompt, /programming 待执行任务/)
      assert.match(prompt, /索引 1/)
      assert.match(prompt, /不扩展为整阶段或全流程/)
    }
  }
})

test('invalid, cross-scope and stale choices cannot submit even if client invents labels or paths', async () => {
  const h = fixture({ scope: 'paper' })
  const payload = await h.request()
  const bad = [
    [{ mode: 'stage', phase: 'programming' }, 'invalid-target'],
    [{ mode: 'task', phase: 'paper', taskId: 'invented' }, 'invalid-target'],
    [{ projectRoot: '/projects/global-current' }, 'project-changed'],
    [{ projectId: 'project-global-current' }, 'project-changed'],
    [{ revision: 6 }, 'stale-project'],
    [{ mode: 'shell', command: 'anything' }, 'invalid-target'],
  ]
  for (const [patch, code] of bad) await assert.rejects(async () => h.service.start({ ...payload, ...patch }), { code })
  assert.equal(h.prompts.length, 0)
  assert.equal(h.resolutions.length, 0, 'malformed/stale requests cannot activate an Agent')
})

test('running, queued, maintenance and disabled sessions reject launch', async () => {
  const h = fixture()
  const payload = await h.request()
  const agent = h.agents.get('sidebar')
  agent.status = 'running'
  assert.equal((await h.service.options('sidebar')).busy, true)
  await assert.rejects(h.service.start(payload), { code: 'session-busy' })
  agent.status = 'idle'; agent.inbox.nextStep.push({})
  await assert.rejects(h.service.start(payload), { code: 'session-busy' })
  agent.inbox.nextStep.length = 0; agent.maintenance = true
  await assert.rejects(h.service.start(payload), { code: 'session-busy' })
  agent.maintenance = false; h.enable(false)
  await assert.rejects(h.service.start(payload), { code: 'workbench-disabled' })
  assert.equal(h.prompts.length, 0)
})

test('project switch while resolving the Agent is caught before submission', async () => {
  const h = fixture()
  const payload = await h.request()
  h.resolveWith(() => { h.states.get('sidebar').project.project_id = 'new-project' })
  await assert.rejects(h.service.start(payload), { code: 'project-changed' })
  assert.equal(h.prompts.length, 0)
})

test('an initialized project cannot start under an ordinary preset without mathematical tools', async () => {
  const h = fixture()
  const payload = await h.request()
  h.agents.get('sidebar').ctx.get = () => undefined
  assert.equal((await h.service.options('sidebar')).available, false)
  await assert.rejects(h.service.start(payload), { code: 'workbench-not-selected' })
  assert.equal(h.prompts.length, 0)
  h.agents.get('sidebar').ctx.get = () => ({ version: 2 })
  h.services.agentPresets = { serviceFor: () => undefined }
  await assert.rejects(h.service.start(payload), { code: 'workbench-not-selected' })
  assert.equal(h.prompts.length, 0, 'the official preset capability registry takes precedence over ambient services')
})

test('double clicks share admission and a conflicting pending request is rejected', async () => {
  const h = fixture()
  const payload = await h.request()
  let release
  const waiting = new Promise(resolve => { release = resolve })
  h.promptWith(async () => { await waiting; return { accepted: true } })
  const first = h.service.start(payload)
  const duplicate = h.service.start({ ...payload })
  await assert.rejects(async () => h.service.start({ ...payload, requestId: randomUUID() }), { code: 'session-busy' })
  assert.equal((await h.service.options('sidebar')).busy, true)
  release()
  assert.deepEqual(await first, await duplicate)
  assert.equal(h.prompts.length, 1)
  assert.equal((await h.service.start(payload)).duplicate, true)
  await assert.rejects(h.service.start({ ...payload, mode: 'stage', phase: 'modeling' }), { code: 'request-conflict' })
  assert.equal(h.prompts.length, 1)
})

test('durable request identity deduplicates after service restart and progress changes', async () => {
  const h = fixture()
  const payload = await h.request()
  await h.service.start(payload)
  h.states.get('sidebar').revision++
  const restarted = new TaskStartService({ get: key => key === 'sessions' ? { get: id => h.sessions.get(id) } : h.services[key] }, h.bridge)
  const repeated = await restarted.start(payload)
  assert.equal(repeated.duplicate, true)
  assert.equal(repeated.accepted, true)
  assert.equal(h.prompts.length, 1)
  const another = await h.request({ requestId: payload.requestId }, 'global-current')
  await h.service.start(another)
  assert.deepEqual(h.prompts.map(request => request.sessionId), ['sidebar', 'global-current'])
})

test('missing host/model and cancelled requests fail without pretending work was accepted', async () => {
  const h = fixture()
  const payload = await h.request()
  const controller = h.services.sessionController
  delete h.services.sessionController
  assert.equal((await h.service.options('sidebar')).available, false)
  await assert.rejects(h.service.start(payload), { code: 'agent-unavailable' })
  h.services.sessionController = controller
  h.promptWith(() => { throw Object.assign(new Error('select a model'), { code: 'session/model-unavailable' }) })
  await assert.rejects(h.service.start(payload), { code: 'session/model-unavailable' })
  h.promptWith(undefined)
  const signal = AbortSignal.abort()
  await assert.rejects(h.service.start(payload, { signal }), { name: 'AbortError' })
  assert.equal(h.sessions.get('sidebar').snapshotEvents().length, 0)
  assert.equal((await h.service.start(payload)).accepted, true, 'explicit retry can succeed after fixing the route')
})

test('an uncertain admission error stays honest and the same request recovers its durable receipt', async () => {
  const h = fixture()
  const payload = await h.request()
  h.promptWith(request => {
    h.sessions.get('sidebar').snapshotEvents().push({ type: 'user/message', data: { source: { kind: 'user', rpcId: request.requestId }, content: request.content } })
    h.agents.get('sidebar').status = 'running'
    throw new Error('receipt transport failed after admission')
  })
  await assert.rejects(h.service.start(payload), error => !error.code && error.message === 'receipt transport failed after admission')
  assert.equal((await h.service.start(payload)).duplicate, true)
  assert.equal(h.prompts.length, 1)
})
