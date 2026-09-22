// Isolated behavioral probes for the unmodified DSH plugin. No real DSH install
// is loaded: host fs and shell services are simulated; files live in OS temp.
import * as fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { apply } from '../../dsh-plugin/math-modeling-agent/plugins/math-modeling.js';
import { apply as applyUi } from '../../dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui/lib/index.js';

const repo = fileURLToPath(new URL('../../', import.meta.url));
const temporaryRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'math-modeling-dsh-audit-'));
const observations = [];
async function write(root, relative, content = '') {
  const target = path.join(root, relative);
  await fs.mkdir(path.dirname(target), { recursive: true });
  await fs.writeFile(target, content);
}
async function harness(label, settings) {
  const root = path.join(temporaryRoot, label);
  await fs.mkdir(root, { recursive: true });
  let cwd = root;
  let pythonExitCode = 0;
  const commands = [];
  const registry = new Map();
  const serviceFs = {
    resolve: async value => path.resolve(cwd, value),
    processPath: value => value,
    contains: (a, b) => { const r = path.relative(a, b); return r === '' || (!r.startsWith('..') && !path.isAbsolute(r)); },
    stat: async target => {
      const s = await fs.stat(target);
      return { type: s.isDirectory() ? 'directory' : 'file', size: s.size,
        version: s.isFile() ? createHash('sha256').update(await fs.readFile(target)).digest('hex') : 'directory' };
    },
    readText: target => fs.readFile(target, 'utf8'),
    writeText: async (target, content) => { await fs.mkdir(path.dirname(target), { recursive: true }); await fs.writeFile(target, content); },
    listDir: async target => Promise.all((await fs.readdir(target, { withFileTypes: true })).map(async e => ({ name: e.name, ...(await serviceFs.stat(path.join(target, e.name))) }))),
  };
  const services = {
    fs: serviceFs,
    settings,
    shell: { resolve: request => request, run: async request => { commands.push(request.command); return { exitCode: request.command === 'python --version' ? pythonExitCode : 0, stdout: pythonExitCode ? '' : 'Python 3.mock', stderr: '' }; } },
    agents: { currentInitiator: () => ({ session: { header: { cwd } } }) },
    tools: { register: definition => registry.set(definition.name, definition) },
  };
  await apply({ get: key => services[key] });
  return { root, commands, registry, fs: serviceFs,
    setCwd: value => { cwd = value; }, setPythonExitCode: value => { pythonExitCode = value; },
    call: (name, args = {}) => registry.get(name).execute(args),
    init: (args = {}) => registry.get('mm_project_init').execute({ skillRoot: repo, ...args }),
  };
}
const receipt = { scope: 'audit probe only', inputSnapshot: '', status: 'PASS', evidence: ['unverified placeholder'], findings: [], rework: '' };

const gates = await harness('gates');
await gates.init();
const unprepared = await gates.call('mm_gate', { gate: 'W2', mode: 'record', receipt: { ...receipt, findings: [{ level: 'P0', text: 'Unresolved critical defect' }] } });
observations.push({ id: 'GATE_RECORD_BYPASSES_PREREQUISITES_AND_P0', result: unprepared,
  state: (await gates.call('mm_state')).gates, observedDefect: unprepared.ok && unprepared.status === 'pass' });

const optional = await harness('optional');
const opted = await optional.init({ optionalCollab: 'literature,prototype' });
observations.push({ id: 'OPTIONAL_COLLAB_STRING_IGNORED', configured: opted.project.optionalCollab,
  observedDefect: opted.project.optionalCollab.literature === false && opted.project.optionalCollab.prototype === false });

const driftGate = await harness('early-drift');
await driftGate.init();
await write(driftGate.root, '题目分析报告.md', 'model A');
await write(driftGate.root, '术语表格.md', 'original');
await driftGate.call('mm_gate', { gate: 'M1', mode: 'record', receipt });
await write(driftGate.root, '题目分析报告.md', 'different model B');
const afterModelChanged = await driftGate.call('mm_phase_enter', { phase: 'programming' });
observations.push({ id: 'MODEL_CHANGE_DOES_NOT_INVALIDATE_PHASE_ENTRY', phaseEntryOk: afterModelChanged.ok,
  gateStatus: (await driftGate.call('mm_state')).gates.M1.status, observedDefect: afterModelChanged.ok });

const explicit = await harness('explicit-root');
const nested = path.join(explicit.root, 'custom-project');
await fs.mkdir(nested);
const initialized = await explicit.init({ projectRoot: nested });
const lost = await explicit.call('mm_state');
observations.push({ id: 'EXPLICIT_PROJECT_ROOT_LOST_NEXT_CALL', initOk: initialized.ok, stateInitialized: lost.initialized,
  observedDefect: initialized.ok && !lost.initialized });

const sessions = await harness('session-a');
await sessions.init({ title: 'Session A' });
const sessionB = path.join(temporaryRoot, 'session-b');
await fs.mkdir(sessionB);
sessions.setCwd(sessionB);
const sessionState = await sessions.call('mm_state');
observations.push({ id: 'WORKSPACE_CACHE_CROSSES_SESSIONS', currentCwd: sessionB, returnedProject: sessionState.project,
  observedDefect: sessionState.project.title === 'Session A' });

const redirected = await harness('state-root');
await redirected.init();
const savedPath = path.join(redirected.root, '.math-modeling/state.json');
const changedState = JSON.parse(await fs.readFile(savedPath, 'utf8'));
const redirectedRoot = path.join(temporaryRoot, 'different-target');
changedState.project.projectRoot = redirectedRoot;
await fs.writeFile(savedPath, JSON.stringify(changedState));
await redirected.call('mm_log', { event: 'root-boundary-probe' });
observations.push({ id: 'STORED_PROJECT_ROOT_REDIRECTS_WRITE_REQUEST', requestedWorkspaceRoot: redirectedRoot,
  stateCreatedElsewhere: !!(await fs.stat(path.join(redirectedRoot, '.math-modeling/state.json')).catch(() => null)),
  note: 'Plugin trusts the stored projectRoot; actual host policy enforcement is not evaluated by this simulation.' });

const complete = await harness('complete');
await complete.init();
for (const filename of ['题目分析报告.md', '术语表格.md', 'main.py', 'old.py', 'results/table.csv', '完整论文.docx']) await write(complete.root, filename);
await write(complete.root, 'results/复现清单.json', JSON.stringify({ seed: null, hash: null, version: null, params: null, command: null }));
for (const category of ['raw', 'process', 'result']) for (let i = 1; i <= 3; i++) await write(complete.root, `figures/${category}_q1_${i}.png`);
for (const gate of ['M1', 'P1', 'P2', 'W1', 'W2']) await complete.call('mm_gate', { gate, mode: 'record', receipt });
const paperWhileModeling = await complete.call('mm_check_deliverables', { phase: 'paper' });
const emptyComplete = await complete.call('mm_complete');
observations.push({ id: 'EMPTY_ARTIFACTS_COMPLETE_WITH_ONLY_THREE_RESULT_FIGURES', done: emptyComplete.done,
  checks: emptyComplete.deliverableChecks, paperCheckItems: paperWhileModeling.items,
  observedDefect: emptyComplete.done === true });

await fs.unlink(path.join(complete.root, 'old.py'));
await write(complete.root, 'new.py', 'changed code after P2');
const changed = await complete.call('mm_complete');
observations.push({ id: 'ADDED_AND_DELETED_ARTIFACTS_NOT_DRIFT', done: changed.done, drift: changed.drift,
  observedDefect: changed.done === true && changed.drift.length === 0 });

complete.setPythonExitCode(1);
const noPython = await complete.call('mm_complete');
const stateAfterNoPython = await complete.call('mm_state');
observations.push({ id: 'PYTHON_FAILURE_BLOCKS_BUT_COMPLETED_STATE_STALE', done: noPython.done, blockers: noPython.blockers,
  checks: noPython.deliverableChecks, persistedCompleted: stateAfterNoPython.completed,
  observedDefect: noPython.done === false && stateAfterNoPython.completed === true });
complete.setPythonExitCode(0);

await complete.call('mm_phase_enter', { phase: 'paper' });
const paperWhilePaper = await complete.call('mm_check_deliverables', { phase: 'paper' });
observations.push({ id: 'FORMAL_FIGURE_CHECK_USES_CURRENT_PHASE_NOT_REQUESTED_PHASE',
  whileModeling: paperWhileModeling.overall, whilePaper: paperWhilePaper.overall,
  observedDefect: paperWhileModeling.overall === 'ok' && paperWhilePaper.overall === 'missing' });

await complete.call('mm_todo', { action: 'check', index: 0 });
const reset = await complete.call('mm_todo', { action: 'reset' });
const afterReset = await complete.call('mm_todo', { action: 'list' });
observations.push({ id: 'TODO_RESET_RETURNS_PRE_RESET_VALUES', returnedDone: reset.done, persistedDone: afterReset.done,
  observedDefect: reset.done !== afterReset.done });

await write(complete.root, 'probe-input.csv', 'x,y\n1,2\n2,4\n');
const manifestCommand = ['references/roles/编程手/scripts/repro_manifest.py', '--project-root', complete.root,
  '--input', path.join(complete.root, 'probe-input.csv'), '--seed', '42', '--command', 'python main.py', '--overwrite'];
const manifestStdout = execFileSync('python', manifestCommand, { cwd: repo, encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
const realManifest = JSON.parse(await fs.readFile(path.join(complete.root, 'results/复现清单.json'), 'utf8'));
const realManifestCheck = await complete.call('mm_check_deliverables', { phase: 'programming' });
const manifestItem = realManifestCheck.items.find(item => item.name === '复现清单.json');
observations.push({ id: 'OFFICIAL_REPRO_MANIFEST_REJECTED_BY_DSH', generatedBy: manifestCommand[0],
  generatorStdout: manifestStdout.trim(), topLevelKeys: Object.keys(realManifest), inputSha256: realManifest.input_files[0].sha256,
  dshCheck: manifestItem, observedDefect: manifestItem.ok === false && manifestItem.note.includes('SHA-256') });

let settingsValue = { enabled: true };
const settings = { get: () => settingsValue, update: async (_name, value) => { settingsValue = value; },
  register: () => ({ get: () => settingsValue, update: async value => { settingsValue = value; } }) };
const toggle = await harness('ui-toggle', settings);
const savedDshHome = process.env.DSH_HOME;
process.env.DSH_HOME = path.join(temporaryRoot, 'ui-settings-home');
let rpc;
applyUi({ get: key => ({ fs: toggle.fs, settings })[key], settings,
  connection: { rpc: { handle: (_channel, handler) => { rpc = handler; } } } });
await rpc('mm.setEnabled', { enabled: false });
const toolEnabled = await toggle.call('mm_ui_toggle', { action: 'on' });
const uiEnabled = await rpc('mm.getEnabled');
observations.push({ id: 'UI_FILE_SETTING_OVERRIDES_TOOL_TOGGLE', toolEnabled: toolEnabled.enabled,
  uiEnabled: uiEnabled.value.enabled, observedDefect: toolEnabled.enabled !== uiEnabled.value.enabled });
if (savedDshHome === undefined) delete process.env.DSH_HOME; else process.env.DSH_HOME = savedDshHome;

const bundleRoot = path.join(repo, 'dsh-plugin/math-modeling-agent/skills/math-modeling');
const expectedScripts = ['tools/figure/scripts/export_figure.py', 'tools/docx/scripts/paper_format.py', 'tools/latex/scripts/latex_paper.py', 'tools/paper_search/scripts/hybrid_scholar.py'];
const bundleFiles = await Promise.all(expectedScripts.map(async file => ({ file, presentInRoot: !!(await fs.stat(path.join(repo, file)).catch(() => null)), presentInBundle: !!(await fs.stat(path.join(bundleRoot, file)).catch(() => null)) })));
observations.push({ id: 'BUNDLE_EXECUTABLES_MISSING', files: bundleFiles, observedDefect: bundleFiles.every(f => f.presentInRoot && !f.presentInBundle) });

const result = { generatedAt: new Date().toISOString(), runtime: process.version, kind: 'isolated context simulation, not real DSH E2E',
  limitations: ['No DSH installation or user configuration modified; scratch files live in OS temp', 'The DSH shell service is simulated; the repro_manifest.py CLI is really executed via Python', 'Real DSH host lifecycle, dependencies and compilation are outside this probe', 'Artifact versions supplied as SHA-256 to avoid relying on host mtime behavior'],
  observations, shellCommands: complete.commands };
await fs.mkdir(path.join(repo, 'project-review/logs'), { recursive: true });
await fs.writeFile(path.join(repo, 'project-review/logs/dsh-probes.json'), JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));
