import test from 'node:test'
import assert from 'node:assert/strict'
import * as fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { RuntimeBridge } from '../../dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui/lib/bridge.js'

const modules = process.env.DSH_TEST_NODE_MODULES
const repo = fileURLToPath(new URL('../../', import.meta.url))

test('official Windows sandbox: prepared parent enables fresh workspace auto-init and stable project identity', {
  skip: process.platform !== 'win32' || !modules,
  timeout: 120000,
}, async t => {
  const load = name => import(pathToFileURL(path.join(modules, '@deepseek-ai', name, 'lib/index.js')))
  const { Context } = await load('cordis')
  const { agentPresetProjectionDefinition } = await load('dsh-agent-preset-registry')
  const discovery = spawnSync('python', ['-B', '-c', 'import sys; print(sys.executable)'], { encoding: 'utf8', windowsHide: true, timeout: 10000 })
  assert.equal(discovery.status, 0, discovery.stderr)
  const python = discovery.stdout.trim()
  assert.ok(path.isAbsolute(python))
  const base = await fs.mkdtemp(path.join(os.tmpdir(), 'mathmodel-workspace-init-'))
  const parent = path.join(base, 'workspace parent')
  await fs.mkdir(parent)
  const ctx = new Context()
  t.after(async () => {
    await ctx.fiber.dispose()
    assert.equal(path.dirname(path.resolve(base)), path.resolve(os.tmpdir()))
    assert.ok(path.basename(base).startsWith('mathmodel-workspace-init-'))
    await fs.rm(base, { recursive: true, force: true })
  })
  const fixtureSecurity = (action, target = parent) => {
    const script = `
import ctypes, json, pathlib, runpy, sys, tempfile
helper, base, root = (pathlib.Path(value).resolve() for value in sys.argv[1:4])
assert base.parent == pathlib.Path(tempfile.gettempdir()).resolve()
assert base.name.startswith('mathmodel-workspace-init-') and root == base / 'workspace parent'
target = pathlib.Path(sys.argv[5]).resolve()
assert target == root or target.is_relative_to(root)
security = runpy.run_path(str(helper))['WindowsSecurity']()
if sys.argv[4] == 'setup':
    user = security.current_user_sid()
    sddl = 'O:' + user + 'D:P(A;OICI;0x1301bf;;;' + user + ')(A;OICI;FA;;;SY)'
    sd, acl, owner = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    present, defaulted = security.w.BOOL(), security.w.BOOL()
    if not security.api.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(sd), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        security.api.GetSecurityDescriptorOwner.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(security.w.BOOL)]
        if not security.api.GetSecurityDescriptorOwner(sd, ctypes.byref(owner), ctypes.byref(defaulted)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not security.api.GetSecurityDescriptorDacl(sd, ctypes.byref(present), ctypes.byref(acl), ctypes.byref(defaulted)):
            raise ctypes.WinError(ctypes.get_last_error())
        result = security.api.SetNamedSecurityInfoW(str(root), 1, 1 | 4 | 0x80000000, owner, None, acl, None)
        if result:
            raise OSError(result, 'Cannot construct isolated test ACL')
    finally:
        security.kernel.LocalFree(sd)
print(json.dumps({'sddl': security.read(target), 'access': security.access(target)}))
`
    const result = spawnSync(python, ['-B', '-c', script, path.join(repo, 'scripts/prepare_dsh_windows_workspace.py'), base, parent, action, target], {
      encoding: 'utf8', windowsHide: true, timeout: 15000,
    })
    assert.equal(result.status, 0, result.stderr || result.error?.message)
    return JSON.parse(result.stdout)
  }
  // Fixture-only ACL: owner may change the DACL, but neither their account nor an
  // enabled Administrators group receives WRITE_OWNER. No real workspace is used.
  const original = fixtureSecurity('setup')
  assert.equal(original.access.WRITE_DAC.granted, true)
  assert.equal(original.access.WRITE_OWNER.granted, false)
  const acl = () => fixtureSecurity('read').sddl
  const prepare = args => {
    const result = spawnSync(python, ['-B', path.join(repo, 'scripts/prepare_dsh_windows_workspace.py'), '--workspace-parent', parent, ...args], {
      encoding: 'utf8', windowsHide: true, timeout: 30000, env: { ...process.env, PYTHONUTF8: '1' },
    })
    assert.equal(result.status, 0, result.stderr || result.stdout || result.error?.message)
    return JSON.parse(result.stdout)
  }
  const mount = async (name, config = {}) => {
    const module = await load(name)
    return ctx.plugin(module.default || module, config)
  }
  await mount('dsh-session')
  await mount('dsh-session-projection')
  ctx.sessionProjections.register(agentPresetProjectionDefinition)
  await mount('dsh-sandbox-policy', { mode: 'workspace-write', workspaceRoot: parent })
  await mount('dsh-subprocess-local')
  await mount('dsh-sandbox-local')
  await mount('dsh-fs-sandbox', { cwd: parent })
  await mount('dsh-pwsh-sandbox', { cwd: parent })
  let settings = { enabled: true, bindings: {} }
  ctx.reflect.provide('settings', {
    describe: () => [{ ns: 'dsh-math-modeling-ui', revision: 1, value: settings }],
    update: async (_namespace, patch) => { settings = { ...settings, ...patch, bindings: { ...settings.bindings, ...patch.bindings } } },
  })
  ctx.reflect.provide('agentPresets', { compositionInventory: async () => [{
    id: 'math-workspace-regression', rows: [{ enabled: true, fiberState: 2, moduleName: 'dsh-math-modeling-ui/workbench' }],
  }] })
  const bridge = new RuntimeBridge(ctx)
  const requests = [], executions = []
  const execute = ctx.shell.execute.bind(ctx.shell)
  ctx.shell.execute = async spec => {
    const encoded = /--request-base64 '([A-Za-z0-9+/=]+)'$/.exec(spec.command)?.[1]
    assert.ok(encoded, 'the real bridge must invoke the shared CLI protocol')
    const request = JSON.parse(Buffer.from(encoded, 'base64').toString('utf8'))
    assert.ok(['init', 'state'].includes(request.action), 'opening the workbench must not run models, solvers or other actions')
    assert.equal(spec.sandboxPolicy.mode, 'workspace-write')
    assert.equal(await fs.realpath(spec.sandboxPolicy.workspaceRoot), await fs.realpath(spec.workdir))
    requests.push(request)
    const operation = await execute(spec)
    return { result: async () => {
      const result = await operation.result()
      executions.push(result.sandbox)
      return result
    } }
  }
  const sessionAt = (id, cwd) => {
    const session = ctx.sessions.create(id, { meta: { cwd, agentPreset: 'math-workspace-regression' } })
    settings.bindings[id] = { cwd, projectRoot: cwd, skillRoot: repo }
    return session
  }
  const deniedRoot = path.join(parent, 'unprepared')
  await fs.mkdir(deniedRoot)
  const existingDeep = path.join(deniedRoot, 'existing nested directory')
  const existingFile = path.join(existingDeep, 'original.txt')
  await fs.mkdir(existingDeep)
  await fs.writeFile(existingFile, 'Unchanged existing project input.\n')
  const deepBefore = fixtureSecurity('read', existingDeep).sddl
  const fileBefore = fixtureSecurity('read', existingFile).sddl
  const deniedSession = sessionAt('unprepared', deniedRoot)
  const before = await bridge.ensureProject(deniedSession.id)
  assert.equal(before.ok, false, 'reproduce the missing WRITE_OWNER failure before explicit preparation')
  assert.equal(before.code, 'sandbox-workspace-authorization-failed', 'the baseline must fail because the actual sandbox cannot grant workspace access')
  assert.equal((await bridge.presentationContext(deniedSession.id)).eligible, true, 'a workspace permission failure does not deselect the math preset')
  await assert.rejects(fs.stat(path.join(deniedRoot, '.math-modeling')), { code: 'ENOENT' })
  const deniedAcl = fixtureSecurity('read', deniedRoot).sddl
  prepare([])
  assert.equal(acl(), original.sddl, 'the preparation helper defaults to read-only inspection')
  assert.equal(fixtureSecurity('read', deniedRoot).sddl, deniedAcl, 'read-only inspection must not prepare existing projects implicitly')
  const backup = path.join(base, 'workspace-permissions-backup.json')
  prepare(['--apply', '--backup', backup])
  assert.ok((await fs.stat(backup)).size > 0)
  assert.match(acl(), /\(A;CINPIO;WO;;;CO\)/, 'the helper must prepare only immediate future workspace directories')
  assert.equal(fixtureSecurity('read', existingDeep).sddl, deepBefore, 'preparation must not change existing deeper directory ACLs')
  assert.equal(fixtureSecurity('read', existingFile).sddl, fileBefore, 'preparation must not change existing file ACLs')
  const retried = await bridge.ensureProject(deniedSession.id)
  assert.equal(retried.ok, true, JSON.stringify(retried))
  assert.equal(retried.initialized, true, 'the previously blocked existing immediate workspace initializes on retry')
  assert.equal(await fs.readFile(existingFile, 'utf8'), 'Unchanged existing project input.\n')

  const projectIds = []
  for (const name of ['first project', 'second sibling']) {
    const cwd = path.join(parent, name)
    await fs.mkdir(cwd)
    assert.deepEqual(await fs.readdir(cwd), [], 'a fresh inherited directory has no model project files')
    const nested = path.join(cwd, 'unsupported nested workspace')
    await fs.mkdir(nested)
    assert.equal(fixtureSecurity('read', nested).access.WRITE_OWNER.granted, false, 'the parent preparation rule must stop after one directory level')
    const session = sessionAt(name, cwd)
    const context = await bridge.presentationContext(session.id)
    assert.equal(context.eligible, true)
    assert.equal(context.initialized, false)
    const initialized = await bridge.ensureProject(session.id)
    assert.equal(initialized.ok, true, JSON.stringify(initialized))
    assert.equal(initialized.initialized, true)
    const statePath = path.join(cwd, '.math-modeling/state.json')
    const state = JSON.parse(await fs.readFile(statePath, 'utf8'))
    assert.equal(state.project.project_id, initialized.project.project_id)
    assert.equal(state.project.projectRoot, await fs.realpath(cwd))
    assert.equal(state.project.scope, 'full')
    assert.equal(state.completed, false)
    assert.equal(Object.keys(state.runs).length, 0, 'automatic initialization must not solve or generate results')
    const reopened = await bridge.ensureProject(session.id)
    assert.equal(reopened.ok, true, JSON.stringify(reopened))
    assert.equal(reopened.project.project_id, initialized.project.project_id)
    assert.equal(JSON.parse(await fs.readFile(statePath, 'utf8')).project.project_id, state.project.project_id)
    projectIds.push(state.project.project_id)
    assert.deepEqual(requests.filter(request => request.session_id === session.id).map(request => request.action), ['init', 'state'])
  }
  assert.notEqual(projectIds[0], projectIds[1], 'independent workspaces keep separate project identities')
  assert.equal(executions.length, 5)
  for (const sandbox of executions) {
    assert.equal(sandbox.mode, 'workspace-write')
    assert.equal(sandbox.enforcement, 'partial')
    assert.equal(sandbox.denied, false)
  }
  assert.equal(ctx.get('llm'), undefined, 'this regression never mounts or calls a model provider')
  t.diagnostic('Actual official Windows restricted-token shell, sandbox policy, filesystem and session projection; actual RuntimeBridge.ensureProject and shared Python CLI. Explicit permission preparation only in owned temporary fixtures; first access denied before preparation, two fresh sibling projects initialized and reopened. Preset inventory/settings are fixtures; execution observation delegates to the real sandbox unchanged; no model request, solver or personal profile change.')
})
