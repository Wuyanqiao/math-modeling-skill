import test from 'node:test'
import assert from 'node:assert/strict'
import * as fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'
import { execFile } from 'node:child_process'
import { apply } from '../../dsh-plugin/math-modeling-agent/plugins/math-modeling.js'
import { apply as applyUi } from '../../dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui/lib/index.js'
import { RuntimeBridge } from '../../dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui/lib/bridge.js'

const execute = promisify(execFile)
const repo = fileURLToPath(new URL('../../', import.meta.url))

async function harness(t, { real = false, skillName = "skill ' 中文" } = {}) {
  const base = await fs.mkdtemp(path.join(os.tmpdir(), 'mathmodel-adapter-'))
  t.after(async () => {
    assert.equal(path.dirname(path.resolve(base)), path.resolve(os.tmpdir()))
    assert.ok(path.basename(base).startsWith('mathmodel-adapter-'))
    await fs.rm(base, { recursive: true, force: true })
  })
  const cwd = path.join(base, 'workspace')
  const custom = path.join(base, 'custom-project')
  const skill = real ? repo : path.join(base, skillName)
  await fs.mkdir(cwd); await fs.mkdir(custom)
  if (!real) {
    await fs.mkdir(path.join(skill, 'scripts'), { recursive: true })
    await fs.writeFile(path.join(skill, 'SKILL.md'), '# Shared Skill')
    await fs.writeFile(path.join(skill, 'scripts/mathmodel.py'), '# mocked runtime')
    const role = path.join(skill, 'references/roles/建模手')
    await fs.mkdir(role, { recursive: true }); await fs.writeFile(path.join(role, 'SKILL.md'), '# Complete role\nSecond line\nThird line\nFourth line')
  }
  const sessions = new Map([['a', { id: 'a', header: { cwd }, agentPreset: 'my-renamed-workbench' }], ['b', { id: 'b', header: { cwd: custom }, agentPreset: 'another-name' }]])
  let selected = 'a'
  let settingsValue = { enabled: true, bindings: {} }
  const settings = { get: () => settingsValue, update: async (_name, value) => { settingsValue = value }, register: () => ({ get: () => settingsValue, update: async value => { settingsValue = value } }) }
  const requests = [], shellRequests = [], tools = new Map()
  const projects = new Map()
  let responder = async request => {
    if (request.action === 'init') {
      const state = { ok: true, initialized: true, project: { projectRoot: request.project_root, skillRoot: request.skill_root, title: request.title || 'Project', scope: request.scope || 'full' }, currentPhase: 'modeling', completed: false, gates: {}, blockers: [], updated_at: new Date().toISOString() }
      projects.set(request.project_root, state)
      await fs.mkdir(path.join(request.project_root, '.math-modeling'), { recursive: true })
      await fs.writeFile(path.join(request.project_root, '.math-modeling/state.json'), JSON.stringify(state))
      return { exitCode: 0, stdout: JSON.stringify(state) }
    }
    return { exitCode: 0, stdout: JSON.stringify({ ok: true, ...projects.get(request.project_root), request }) }
  }
  const hostFs = {
    resolve: async value => path.resolve(sessions.get(selected).header.cwd, value), processPath: value => value,
    contains: (root, target) => { const rel = path.relative(root, target); return !rel || (!rel.startsWith('..') && !path.isAbsolute(rel)) },
    stat: async target => { const value = await fs.stat(target); return { type: value.isDirectory() ? 'directory' : 'file', size: value.size } },
    readText: target => fs.readFile(target, 'utf8'),
  }
  const services = { fs: hostFs, settings, sessions: { get: id => sessions.get(id) }, agents: { currentInitiator: () => ({ session: sessions.get(selected), agent: { id: `author-${selected}` } }) },
    tools: { register: definition => tools.set(definition.name, definition) },
    shell: { resolve: request => { shellRequests.push(request); return request }, run: async shellRequest => {
      const encoded = shellRequest.command.match(/--request-base64 '([A-Za-z0-9+/=]+)'$/)?.[1]
      assert.ok(encoded, 'JSON must be carried as one base64 argument')
      const request = JSON.parse(Buffer.from(encoded, 'base64').toString('utf8')); requests.push(request)
      assert.equal(shellRequest.workdir, request.project_root)
      assert.equal('sandbox_permissions' in shellRequest, false)
      if (!real) return responder(request)
      try { const output = await execute('python', [path.join(repo, 'scripts/mathmodel.py'), '--request-base64', encoded], { cwd: request.project_root, env: { ...process.env, PYTHONIOENCODING: 'utf-8' } }); return { exitCode: 0, ...output } }
      catch (error) { return { exitCode: error.code, stdout: error.stdout, stderr: error.stderr } }
    } },
  }
  const ctx = { get: key => services[key], settings }
  await apply(ctx)
  return { base, cwd, custom, skill, requests, shellRequests, tools, sessions, ctx, services,
    select: value => { selected = value }, respond: value => { responder = value },
    call: (name, args = {}) => tools.get(name).execute(args),
    init: args => tools.get('mm_project_init').execute({ skillRoot: skill, ...args }),
    ui() { let handler; applyUi({ ...ctx, connection: { rpc: { handle: (_channel, callback) => { handler = callback; return () => {} } } } }); return (endpoint, payload) => handler(endpoint, payload) },
  }
}

test('custom project remains bound across tools and sessions remain isolated', async t => {
  const h = await harness(t)
  assert.equal((await h.init({ projectRoot: h.custom, title: 'A custom' })).ok, true)
  const stateA = await h.call('mm_state')
  assert.equal(stateA.project.projectRoot, h.custom)
  h.select('b')
  await h.init({ projectRoot: h.cwd, title: 'B other' })
  assert.equal((await h.call('mm_state')).project.projectRoot, h.cwd)
  h.select('a')
  assert.equal((await h.call('mm_state')).project.title, 'A custom')
  const reloaded = new RuntimeBridge(h.ctx)
  assert.equal((await reloaded.request('state')).project.projectRoot, h.custom)
})

test('payload encoding preserves Unicode, quotes and shell metacharacters without interpolation', async t => {
  const h = await harness(t, { skillName: "skill ' 中文 $(echo path-injected) &;" })
  const title = '中文 \' " ` $(throw "BAD") $(echo INJECTED > payload-injected.txt) ; & test'
  const result = await h.init({ title, optionalCollab: 'literature,prototype', subproblems: 'q1，q2', paperFormat: 'latex' })
  assert.equal(result.ok, true)
  assert.equal(h.requests[0].title, title)
  assert.deepEqual(h.requests[0].optional_collab, ['literature', 'prototype'])
  assert.deepEqual(h.requests[0].subproblems, ['q1', 'q2'])
  assert.equal(h.requests[0].paper_format, 'latex')
  assert.equal(h.shellRequests[0].command.includes('throw'), false)
  assert.equal(h.shellRequests[0].command.includes('payload-injected.txt'), false)

  const script = path.join(h.skill, 'scripts/mathmodel.py')
  await fs.writeFile(script, [
    'import base64, json, sys',
    'from pathlib import Path',
    "assert sys.argv[1] == '--request-base64' and len(sys.argv) == 3",
    "request = json.loads(base64.b64decode(sys.argv[2]).decode('utf-8'))",
    "Path('shell-roundtrip.json').write_text(json.dumps({'request': request, 'script': str(Path(__file__).resolve())}, ensure_ascii=False), encoding='utf-8')",
  ].join('\n'))
  const request = h.shellRequests[0]
  const shell = process.platform === 'win32' ? 'pwsh.exe' : '/bin/sh'
  const argv = process.platform === 'win32' ? ['-NoProfile', '-NonInteractive', '-Command', request.command] : ['-c', request.command]
  await execute(shell, argv, { cwd: request.workdir, env: { ...process.env, ...request.env }, timeout: 15000 })
  const observed = JSON.parse(await fs.readFile(path.join(h.cwd, 'shell-roundtrip.json'), 'utf8'))
  assert.deepEqual(observed.request, h.requests[0], 'the real shell must preserve the entire decoded request')
  assert.equal(await fs.realpath(observed.script), await fs.realpath(script), 'the real shell must preserve the quoted script path')
  await assert.rejects(fs.stat(path.join(h.cwd, 'payload-injected.txt')), { code: 'ENOENT' })
})

test('nonzero runtime JSON remains inspectable and shell denial is not bypassed', async t => {
  const h = await harness(t)
  await h.init({})
  h.respond(async () => ({ exitCode: 1, stdout: JSON.stringify({ ok: false, error: 'review denied', code: 'gate-blocked' }) }))
  assert.deepEqual(await h.call('mm_gate', { mode: 'record', gate: 'W2', receipt: {} }), { ok: false, error: 'review denied', code: 'gate-blocked' })
  h.services.shell.run = async () => { throw new Error('host approval denied') }
  assert.match((await h.call('mm_state')).error, /host approval denied/)
})

test('skill content is returned in full and traversal is rejected', async t => {
  const h = await harness(t)
  await h.init({})
  const result = await h.call('mm_phase_enter', { phase: 'modeling' })
  assert.match(result.skillMd, /Fourth line/)
  const rendered = h.tools.get('mm_phase_enter').output.render({}, result)[0].text
  assert.match(rendered, /Fourth line/)
  assert.equal((await h.call('mm_skill_read', { path: '../../outside.txt' })).ok, false)
})

test('UI reads renamed preset projects, uses explicit binding and shares tool settings', async t => {
  const h = await harness(t)
  await h.init({ projectRoot: h.custom, title: 'Renamed preset project' })
  const rpc = h.ui()
  const snapshot = (await rpc('mm.state', { sessionId: 'a' })).value
  assert.equal(snapshot.project.title, 'Renamed preset project')
  assert.equal(snapshot.stale, true)
  assert.equal(h.requests.length, 1, 'snapshot polling must not launch shell commands')
  assert.equal((await rpc('mm.state', { sessionId: 'a', refresh: true })).value.stale, false)
  await rpc('mm.setEnabled', { enabled: false })
  assert.equal((await h.call('mm_ui_toggle', { action: 'get' })).enabled, false)
  await h.call('mm_ui_toggle', { action: 'on' })
  assert.equal((await rpc('mm.getEnabled', {})).value.enabled, true)
  assert.equal((await rpc('mm.state', { sessionId: 'unknown' })).value.hidden, true)
})

test('UI retains an explicitly stale snapshot when host cannot authorize refresh', async t => {
  const h = await harness(t)
  await h.init({})
  const rpc = h.ui()
  h.services.shell.run = async () => { throw new Error('approval needed') }
  const result = await rpc('mm.state', { sessionId: 'a', refresh: true })
  assert.equal(result.value.stale, true)
  assert.match(result.value.refreshError, /approval needed/)
})

test('project roots from state are never followed by the adapter', async t => {
  const h = await harness(t)
  await h.init({})
  const file = path.join(h.cwd, '.math-modeling/state.json')
  const state = JSON.parse(await fs.readFile(file, 'utf8'))
  state.project.projectRoot = h.custom
  await fs.writeFile(file, JSON.stringify(state))
  await h.call('mm_state')
  assert.equal(h.requests.at(-1).project_root, h.cwd)
})

test('DSH 0.1.7 execute/result and CollectedOutput inherit the session sandbox unchanged', async t => {
  const h = await harness(t)
  const standing = { mode: 'read-only', workspaceRoot: h.cwd }
  h.services.sandboxPolicy = { resolve: request => {
    assert.deepEqual(Object.keys(request), ['session'])
    assert.equal(request.session.id, 'a')
    return standing
  } }
  h.services.shell.sandboxMode = 'read-only'
  const run = h.services.shell.run
  h.services.shell.execute = async spec => {
    assert.equal(spec.sandboxPolicy, standing)
    const raw = await run(spec)
    return { result: async () => ({ ...raw, stdout: { text: raw.stdout, truncated: false }, stderr: { text: '', truncated: false }, aborted: false, timedOut: false, signal: null }) }
  }
  delete h.services.shell.run
  assert.equal((await h.init({ projectRoot: h.custom })).ok, true)
  assert.equal(h.shellRequests[0].sandboxPolicy.workspaceRoot, h.cwd)
  assert.equal(h.shellRequests[0].workdir, h.custom)
})

test('interrupted, denied and truncated runs never become successful JSON responses', async t => {
  const h = await harness(t)
  await h.init({})
  for (const facts of [{ timedOut: true }, { aborted: true }, { sandbox: { denied: true } }, { stdout: { text: '{"ok":true}', truncated: true } }]) {
    h.services.shell.execute = async () => ({ result: async () => ({ exitCode: 0, stdout: { text: '{"ok":true}', truncated: false }, ...facts }) })
    assert.equal((await h.call('mm_state')).ok, false)
  }
})

test('modern Config-derived settings share one namespace without legacy register/get APIs', async t => {
  const h = await harness(t)
  let value = { enabled: true, bindings: {} }, revision = 0
  const settings = {
    describe: () => [{ ns: 'dsh-math-modeling-ui', value, revision }],
    update: async (id, patch, expected) => { assert.equal(id, 'dsh-math-modeling-ui'); assert.equal(expected, revision); value = { ...value, ...patch, bindings: { ...value.bindings, ...patch.bindings } }; revision++ },
  }
  h.services.settings = settings; h.ctx.settings = settings
  await apply(h.ctx)
  assert.equal((await h.init({ projectRoot: h.custom })).ok, true)
  assert.equal(value.bindings.a.projectRoot, h.custom)
  const rpc = h.ui()
  await rpc('mm.setEnabled', { enabled: false })
  assert.equal((await h.call('mm_ui_toggle', { action: 'get' })).enabled, false)
  await h.call('mm_ui_toggle', { action: 'on' })
  assert.equal((await rpc('mm.getEnabled', {})).value.enabled, true)
})

test('real Python CLI: init, manifest-safe state, todo, gate refusal and incomplete completion', async t => {
  const h = await harness(t, { real: true })
  const initial = await h.init({ scope: 'modeling', profile: 'short', subproblems: ['q1'], projectRoot: h.custom })
  assert.equal(initial.ok, true, JSON.stringify(initial))
  assert.equal((await h.call('mm_state')).project.scope, 'modeling')
  const todo = await h.call('mm_todo', { action: 'list' })
  assert.equal(todo.ok, true, JSON.stringify(todo))
  const gate = await h.call('mm_gate', { gate: 'W2', mode: 'record', receipt: { status: 'PASS' } })
  assert.equal(gate.ok, false)
  const complete = await h.call('mm_complete')
  assert.equal(complete.done, false, JSON.stringify(complete))
  assert.equal((await h.call('mm_state')).completed, false)
})

test('real Python CLI: execution provenance, claim evidence, review receipt and drift invalidation', async t => {
  const h = await harness(t, { real: true })
  assert.equal((await h.init({ scope: 'programming', profile: 'short', subproblems: ['q1'] })).ok, true)
  await fs.writeFile(path.join(h.cwd, 'input.csv'), 'value\n2\n3\n')
  await fs.writeFile(path.join(h.cwd, 'solve.py'), "from pathlib import Path\nPath('results').mkdir(exist_ok=True)\nPath('results/answer.csv').write_text('total\\n5\\n', encoding='utf-8')\nprint('total=5')\n")
  const run = await h.call('mm_run', { argv: ['python', 'solve.py'], inputs: ['input.csv'], code: ['solve.py'], outputs: ['results/answer.csv'], seed: 7 })
  assert.equal(run.ok, true, JSON.stringify(run))
  const state = await h.call('mm_state')
  const execution = Object.values(state.runs)[0]
  assert.equal(execution.exit_code, 0)
  const log = await h.call('mm_run_log_read', { run_id: execution.run_id, stream: 'stdout' })
  assert.equal(log.ok, true, JSON.stringify(log))
  assert.match(log.content, /total=5/)
  assert.equal((await h.call('mm_run_log_read', { run_id: '../state', stream: 'stdout' })).ok, false)
  assert.equal((await h.call('mm_run_log_read', { run_id: execution.run_id, stream: '../state' })).ok, false)
  const artifact = await h.call('mm_artifact_add', { path: 'results/answer.csv', kind: 'table', question: 'q1', run_id: execution.run_id })
  assert.equal(artifact.ok, true, JSON.stringify(artifact))
  const claim = await h.call('mm_claim_add', { text: 'The test inputs sum to five.', question: 'q1', artifact_ids: [artifact.artifact.artifact_id], locator: 'row 2' })
  assert.equal(claim.ok, true, JSON.stringify(claim))
  const review = await h.call('mm_gate', { mode: 'prepare', gate: 'P1' })
  assert.equal(review.ok, true, JSON.stringify(review))
  const receipt = { task_id: review.task_id, snapshot_hash: review.snapshot_hash, reviewer_id: 'test-external-reviewer', review_source: 'external', status: 'PASS', scope: 'Test fixture execution only', evidence: [{ path: artifact.artifact.path, sha256: artifact.artifact.sha256 }], findings: [], rework: '' }
  const recorded = await h.call('mm_gate', { mode: 'record', gate: 'P1', receipt })
  assert.equal(recorded.ok, true, JSON.stringify(recorded))
  assert.equal(recorded.identity_assurance, 'declared')
  assert.equal((await h.call('mm_state')).gates.P1.status, 'pass')
  const preview = await h.call('mm_artifact_read', { path: artifact.artifact.path })
  assert.match(preview.content, /5/)
  await fs.appendFile(path.join(h.cwd, 'solve.py'), '# changed after review\n')
  assert.equal((await h.call('mm_state')).gates.P1.status, 'invalidated')
})
