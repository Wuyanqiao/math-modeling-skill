import test from 'node:test'
import assert from 'node:assert/strict'
import * as fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath, pathToFileURL } from 'node:url'

const modules = process.env.DSH_TEST_NODE_MODULES
const repo = fileURLToPath(new URL('../../', import.meta.url))

test('official Windows workspace-write sandbox: dependency probes inherit private TEMP ACL and clean up', {
  skip: process.platform !== 'win32' || !modules,
  timeout: 60000,
}, async t => {
  const load = name => import(pathToFileURL(path.join(modules, '@deepseek-ai', name, 'lib/index.js')))
  const { Context } = await load('cordis')
  const sandbox = await load('dsh-sandbox-local')
  const discovery = spawnSync(process.env.PYTHON || 'python', ['-B', '-c', 'import sys; print(sys.executable)'], { encoding: 'utf8', windowsHide: true, timeout: 10000 })
  assert.equal(discovery.status, 0, discovery.stderr)
  const python = discovery.stdout.trim()
  assert.ok(path.isAbsolute(python))
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), 'mathmodel-sandbox-environment-'))
  const ctx = new Context()
  t.after(async () => {
    await ctx.fiber.dispose()
    assert.equal(path.dirname(path.resolve(workspace)), path.resolve(os.tmpdir()))
    assert.ok(path.basename(workspace).startsWith('mathmodel-sandbox-environment-'))
    await fs.rm(workspace, { recursive: true, force: true })
  })
  const script = `
import json, os, pathlib, sys, tempfile, time, uuid
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from mathmodel_runtime.environment import _run_probe, probe_package, probe_command, _reason
root = pathlib.Path(tempfile.gettempdir())
report = {'python': sys.version.split()[0], 'temp_is_private': root.name.startswith('dsh-')}
legacy = root / ('legacy-0700-' + uuid.uuid4().hex)
os.mkdir(legacy, 0o700)
try:
    (legacy / 'probe.txt').write_text('probe')
    report['legacy_0700'] = {'writable': True}
except PermissionError as error:
    report['legacy_0700'] = {'writable': False, 'errno': error.errno}
before = {p.name for p in root.iterdir() if p.name.startswith('mathmodel-environment-')}
report['packages'] = {name: probe_package(name, time.monotonic() + 15) for name in ('numpy', 'matplotlib')}
report['command'] = probe_command((pathlib.Path(sys.executable).stem,), project_root=sys.argv[2], deadline=time.monotonic() + 8)
with patch('mathmodel_runtime.environment.tempfile.TemporaryFile', side_effect=PermissionError('DO_NOT_RETURN_RAW_EXCEPTION')):
    report['temp_denied'] = _run_probe([sys.executable, '-B', '-c', 'print(1)'], 4)
report['temp_denied_detail'] = _reason(report['temp_denied']['reason'])
after = {p.name for p in root.iterdir() if p.name.startswith('mathmodel-environment-')}
report['probe_directories_cleaned'] = before == after
print(json.dumps(report))
`
  await ctx.plugin(sandbox.default)
  const confined = await ctx.sandbox.confine([python, '-B', '-c', script, repo, workspace], {
    mode: 'workspace-write', workspaceRoot: workspace, sessionId: 'mathmodel-environment-regression',
  })
  assert.equal(confined.enforcement, 'partial', 'the actual official Windows ACL backend reports partial enforcement')
  const result = spawnSync(confined.argv[0], confined.argv.slice(1), { cwd: workspace, encoding: 'utf8', timeout: 45000, windowsHide: true })
  assert.equal(result.status, 0, result.stderr || result.error?.message)
  const report = JSON.parse(result.stdout)
  assert.match(report.python, /^3\.13\./, 'run this Windows compatibility regression with Python 3.13')
  assert.equal(report.temp_is_private, true, 'the official runner must supply its session-private TEMP')
  assert.deepEqual(report.legacy_0700, { writable: false, errno: 13 }, 'reproduce the original restricted-token ACL failure')
  for (const [name, item] of Object.entries(report.packages)) assert.equal(item.status, 'ready', `${name}: ${JSON.stringify(item)}`)
  assert.equal(report.command.status, 'ready', JSON.stringify(report.command))
  assert.match(report.command.version, /^3\.13\./)
  assert.deepEqual(report.temp_denied, { status: 'error', reason: 'temp_failed' })
  assert.match(report.temp_denied_detail, /临时目录/)
  assert.equal(result.stdout.includes('DO_NOT_RETURN_RAW_EXCEPTION'), false)
  assert.equal(report.probe_directories_cleaned, true, 'success and temporary-file denial both clean their owned probe directories')
  assert.deepEqual(await fs.readdir(workspace), [], 'dependency checks must not create project files')
  t.diagnostic(`Actual official Windows restricted-token workspace-write sandbox; Python ${report.python}; NumPy ${report.packages.numpy.version}; Matplotlib ${report.packages.matplotlib.version}; Python version command ready; temporary directories cleaned. Original mkdir(0700) denial reproduced. Only the temporary-file failure branch is injected; no user profile or sandbox mode changed.`)
})
