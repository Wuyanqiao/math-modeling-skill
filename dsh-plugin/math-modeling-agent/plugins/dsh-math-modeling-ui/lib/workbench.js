import { RuntimeBridge, createSettings, toolDefinition } from './bridge.js'

export const name = 'math-modeling-workbench'
export const inject = ['tools', 'fs', 'shell']
const text = (description, extra = {}) => ({ type: 'string', description, ...extra })
const choices = (description, values) => text(description, { enum: values })
const object = description => ({ type: 'object', additionalProperties: true, description })
const strings = description => ({ type: 'array', items: { type: 'string' }, description })
const rolePaths = { modeling: 'references/roles/建模手/SKILL.md', programming: 'references/roles/编程手/SKILL.md', paper: 'references/roles/论文手/SKILL.md' }

export async function apply(ctx) {
  const registry = ctx.get('tools')
  if (!registry || !ctx.get('fs') || !ctx.get('shell')) return
  const bridge = new RuntimeBridge(ctx)
  const settings = createSettings(ctx)
  const common = { projectRoot: text('项目目录；默认当前会话绑定的项目或工作目录'), skillRoot: text('可选完整 Skill 根目录；默认内置运行时或本地源码仓库') }
  function register(name, description, parameters, run, required = []) {
    registry.register(toolDefinition(name, description, { ...common, ...parameters }, run, required))
  }
  const invoke = (action, transform = args => args) => (args, execution) => bridge.request(action, transform(args), undefined, execution)
  register('mm_project_init', '初始化或续接项目，并绑定当前会话。通用运行时负责验证、迁移和流程规则。', {
    title: text('项目名称'), competition: text('目标竞赛'), edition: text('届次'),
    scope: choices('任务范围', ['full', 'modeling', 'programming', 'paper']), profile: choices('质量配置', ['balanced', 'short', 'competition']),
    paperFormat: choices('用户要求的论文格式', ['word', 'latex', 'word+latex']),
    rules: object('用户或当届官方规则的明确硬约束及来源'),
    subproblems: { oneOf: [{ type: 'array', items: { type: 'string' } }, { type: 'string' }], description: '子问题数组或逗号分隔的 q1,q2' },
    optionalCollab: { oneOf: [{ type: 'array', items: { type: 'string' } }, { type: 'string' }], description: '用户明确启用的额外协作类别' },
  }, invoke('init', args => ({ ...args, subproblems: list(args.subproblems), optional_collab: list(args.optionalCollab), paper_format: args.paperFormat })))
  register('mm_state', '读取并重新核验项目状态；产物变更会使相关门禁和完成状态失效。', {}, invoke('state'))
  register('mm_doctor', '检查当前任务的运行时、依赖和能力，返回修复建议。', { features: strings('可选能力列表') }, invoke('doctor'))
  register('mm_phase_enter', '通过运行时门禁后进入阶段并加载完整角色 Skill。', { phase: choices('目标阶段', Object.keys(rolePaths)) }, async (args, execution) => {
    const result = await bridge.request('phase', args, undefined, execution)
    if (result.ok === false) return result
    const role = await bridge.readSkill(rolePaths[args.phase], args)
    return role.ok ? { ...result, skillMd: role.content, skillMdPath: role.path } : { ...role, phase: args.phase }
  }, ['phase'])
  register('mm_skill_read', '只读加载 Skill 内的规范或工具说明；拒绝越界路径。', { path: text('Skill 内相对或绝对路径') }, args => bridge.readSkill(args.path, args), ['path'])
  register('mm_gate', 'prepare 创建绑定快照的审核任务；record 提交独立回执。reviewer_id 是声明身份，不能据此声称宿主已认证。', {
    gate: choices('门禁', ['M1', 'P1', 'P2', 'W1', 'W2']), mode: choices('动作', ['prepare', 'record']),
    receipt: object('包含 task_id、reviewer_id、review_source、snapshot_hash、status、evidence[{path,sha256}]、findings、scope、rework'),
  }, (args, execution) => bridge.request(args.mode === 'record' ? 'gate-record' : 'gate-prepare', args, undefined, execution), ['gate'])
  register('mm_check_deliverables', '运行统一产物验证器，检查文件结构、复现清单、图表和阶段合同。', { phase: choices('可选目标阶段', Object.keys(rolePaths)) }, invoke('validate'))
  register('mm_complete', '重新验证当前范围的门禁、运行证据和产物；失败则撤销完成标记并报告阻塞。', {}, invoke('complete'))
  register('mm_todo', '读取、勾选或重置清单，返回运行时最新状态。', {
    action: choices('清单动作', ['list', 'check', 'uncheck', 'add', 'reset']), phase: choices('目标阶段', Object.keys(rolePaths)), index: { type: 'integer', description: '从0开始' }, text: text('新增任务'), note: text('备注'),
  }, invoke('todo', args => ({ ...args, operation: args.action || 'list' })))
  register('mm_log', '追加决策或返工记录。', { event: text('事件名'), details: text('详细说明') }, invoke('log', args => ({ ...args, detail: args.details })), ['event'])
  register('mm_run', '通过宿主授权 shell 运行参数数组并登记真实退出码与日志。', {
    argv: { type: 'array', items: { type: 'string' }, description: '非空命令参数数组' }, timeout: { type: 'number', description: '正数超时秒数' },
    inputs: strings('项目内输入文件'), outputs: strings('项目内输出文件'), code: strings('运行的源码文件'), seed: { type: 'integer' }, parameters: object('关键参数'), phase: choices('所属阶段', Object.keys(rolePaths)),
  }, invoke('run'), ['argv'])
  register('mm_run_log_read', '读取已登记运行的 stdout 或 stderr；由运行时限制日志路径与大小。', { run_id: text('已登记运行 id'), stream: choices('日志', ['stdout', 'stderr']), max_bytes: { type: 'integer', description: '预览字节上限，最大262144' } }, invoke('run-log-read'), ['run_id', 'stream'])
  register('mm_artifact_add', '登记产物、类型、子问题与来源；运行时计算内容哈希。', {
    path: text('项目内路径'), kind: choices('产物类型', ['model', 'terms', 'code', 'table', 'figure', 'document', 'pdf', 'manifest', 'outline', 'other']), question: text('子问题'), run_id: text('来源运行 id'),
    role: choices('图表用途', ['raw', 'process', 'result', 'flow', 'render']), logical_id: text('同一逻辑图的多格式共用 id'), source_artifact_id: text('渲染图对应的原始文档 id'),
  }, invoke('artifact-add'), ['path', 'kind'])
  register('mm_claim_add', '将主张关联到已登记产物 id，并标明证据位置。', { text: text('主张'), question: text('子问题'), artifact_ids: strings('已登记产物 id'), locator: text('页码、表格或行号'), claim_id: text('可选已有主张 id') }, invoke('claim-add'), ['text', 'artifact_ids'])
  register('mm_checkpoint', '恢复默认只预览变更；检查预览后用 apply=true 与 expected_revision 应用恢复。', {
    mode: choices('动作', ['create', 'list', 'restore']), name: text('名称'), checkpoint_id: text('检查点 id'), apply: { type: 'boolean', default: false }, expected_revision: { type: 'integer' },
  }, (args, execution) => bridge.request(`checkpoint-${args.mode || 'list'}`, args, undefined, execution))
  register('mm_artifact_read', '预览项目内产物，返回受限文本或元数据，拒绝越界文件。', { path: text('项目内文件路径') }, invoke('artifact-read'), ['path'])
  register('mm_ui_toggle', '通过与桌面 UI 共用的 DSH settings 开关看板。', { action: choices('动作', ['get', 'on', 'off']) }, async args => {
    if (args.action === 'get' || !args.action) return { ok: true, ...await settings.read() }
    await settings.update({ enabled: args.action === 'on' })
    return { ok: true, ...await settings.read() }
  })
  ctx.get('systemPrompt')?.section({ name, order: 5000, text: [
    '## 数学建模工作台',
    '用 mm_project_init 绑定当前项目并选择 full/modeling/programming/paper 范围。先运行 mm_doctor，按需用 mm_phase_enter 读取角色规范。',
    '通用运行时是流程、证据和完成状态的唯一来源。先用 mm_gate prepare 创建快照审核任务，再派发未参与编写的只读审核者，最后原样记录回执。',
    'reviewer_id 与 review_source 是身份声明，并不等于宿主认证；没有独立审核能力时如实报告限制。',
    '用 mm_run 登记真实命令结果，用 mm_artifact_add 和 mm_claim_add 建立证据。不得用口头成功、空文件或手填状态替代验证。',
    '按 blockers 修复失败；宣称完成前必须执行 mm_complete。Skill 根目录只读，宿主文件与 shell 的授权策略始终有效。',
  ].join('\n') })
  const skill = await bridge.readSkill('SKILL.md').catch(() => null)
  if (skill?.ok) ctx.get('skills')?.register({ name: 'math-modeling', description: '通用数学建模 Skill 与共享验证运行时', whenToUse: '数学建模、求解、验证及论文生成', source: skill.path, path: skill.path, provider: name, content: skill.content })
}

function list(value) { return value === undefined ? undefined : Array.isArray(value) ? value.map(String) : String(value).split(/[,，\s]+/).filter(Boolean) }
