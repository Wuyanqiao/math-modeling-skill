import { Buffer } from 'node:buffer'
import { fileURLToPath } from 'node:url'
import { Config } from './settings-schema.js'

const settingStores = new WeakMap()
const sessionStores = new WeakMap()
const bundledRoot = fileURLToPath(new URL('../../../skills/math-modeling/', import.meta.url))
const sourceRoot = fileURLToPath(new URL('../../../../../', import.meta.url))
const packageRoot = fileURLToPath(new URL('../skills/math-modeling/', import.meta.url))
const join = (root, tail) => `${root.replace(/[\\/]$/, '')}/${tail}`
const errorText = error => String(error?.message || error)

export function createSettings(ctx) {
  const service = ctx.get('settings')
  if (!service) return { read: async () => ({ enabled: true, bindings: {}, persistent: false }), update: async () => { throw new Error('DSH settings 服务不可用，无法持久化设置') } }
  if (settingStores.has(service)) return settingStores.get(service)
  if (typeof service.register !== 'function' && typeof service.describe === 'function') {
    const descriptor = () => service.describe().find(item => item.ns === 'dsh-math-modeling-ui')
    const store = {
      read: async () => {
        const item = descriptor()
        return { enabled: true, bindings: {}, ...(item?.value || {}), persistent: !!item }
      },
      update: async patch => {
        const item = descriptor()
        if (!item) throw new Error('DSH 0.1.7 需要安装工作台组合包以持久化设置；当前会话绑定仍可在进程内使用')
        await service.update(item.ns, patch, item.revision)
      },
    }
    settingStores.set(service, store)
    return store
  }
  let scope
  try {
    scope = service.register('math-modeling-ui', Config || { type: 'object', properties: {
      enabled: { type: 'boolean', default: true }, bindings: { type: 'object', additionalProperties: true, default: {} },
    }, additionalProperties: false }, { label: '数学建模', description: '看板显示与会话项目绑定' })
  } catch { /* A different adapter can own the shared namespace. */ }
  const read = async () => ({ enabled: true, bindings: {}, ...(await (scope?.get ? scope.get() : service.get('math-modeling-ui')) || {}), persistent: true })
  let pending = Promise.resolve()
  const store = { read, update(patch) {
    const update = pending.catch(() => {}).then(async () => {
      const current = await read()
      const next = { enabled: patch.enabled ?? current.enabled, bindings: { ...current.bindings, ...patch.bindings } }
      if (scope?.update) await scope.update(next)
      else await service.update('math-modeling-ui', next)
      return next
    })
    pending = update
    return update
  } }
  settingStores.set(service, store)
  return store
}

export class RuntimeBridge {
  constructor(ctx) {
    this.ctx = ctx
    this.fs = ctx.get('fs')
    this.shell = ctx.get('shell')
    this.settings = createSettings(ctx)
    const owner = ctx.get('settings') || this.fs
    if (!sessionStores.has(owner)) sessionStores.set(owner, new Map())
    this.bindings = sessionStores.get(owner)
  }
  async session(sessionId) {
    const initiator = this.ctx.get('agents')?.currentInitiator?.()
    let session = initiator?.session
    if (sessionId) {
      session = await this.ctx.get('sessions')?.get?.(sessionId)
      if (!session && (initiator?.session?.id === sessionId || initiator?.session?.header?.id === sessionId)) session = initiator.session
      if (!session) throw new Error('当前会话不可用；无法安全解析项目目录')
    }
    const cwd = session?.header?.cwd
    if (!cwd) throw new Error('缺少当前会话工作目录；请在会话内初始化项目')
    const id = sessionId || session.id || session.header?.id || `cwd:${cwd}`
    return { id, cwd, value: session, authorId: initiator?.id || initiator?.agent?.id || initiator?.agentId || id }
  }
  async path(value) { return this.fs.processPath(await this.fs.resolve(value)) }
  async exists(value) { try { return await this.fs.stat(await this.fs.resolve(value)) } catch { return null } }
  async skillRoot(explicit) {
    for (const root of explicit ? [explicit] : [packageRoot, bundledRoot, sourceRoot]) {
      if (await this.exists(join(root, 'SKILL.md')) && await this.exists(join(root, 'scripts/mathmodel.py'))) return this.path(root)
    }
    throw new Error('缺少完整 Skill 运行时 scripts/mathmodel.py；请安装完整发行包或显式指定 skillRoot')
  }
  async context(args = {}, sessionId) {
    const session = await this.session(sessionId)
    const saved = (await this.settings.read()).bindings[session.id] || this.bindings.get(session.id)
    const binding = saved?.cwd === session.cwd ? saved : null
    const projectRoot = await this.path(args.projectRoot || args.project_root || binding?.projectRoot || session.cwd)
    const skillRoot = await this.skillRoot(args.skillRoot || args.skill_root || binding?.skillRoot)
    const info = await this.exists(projectRoot)
    if (!info || info.type !== 'directory') throw new Error('项目目录不存在或不是目录')
    const projectTarget = await this.fs.resolve(projectRoot)
    const skillTarget = await this.fs.resolve(skillRoot)
    if (this.fs.contains(skillTarget, projectTarget) || this.fs.contains(projectTarget, skillTarget)) throw new Error('Skill 与项目目录必须不同且互不包含')
    return { session, projectRoot, skillRoot }
  }
  async readSkill(relative, args = {}) {
    try {
      if (!relative) throw new Error('缺少 Skill 文件路径')
      let root = args.skillRoot || args.skill_root
      if (!root) { try { root = (await this.context(args)).skillRoot } catch { root = await this.skillRoot() } }
      root = await this.path(root)
      const target = await this.fs.resolve(/^(?:[A-Za-z]:[\\/]|[\\/])/.test(relative) ? relative : join(root, relative))
      if (!this.fs.contains(await this.fs.resolve(root), target)) throw new Error('文件必须在 Skill 根目录内')
      return { ok: true, path: this.fs.processPath(target), content: await this.fs.readText(target) }
    } catch (error) { return { ok: false, error: errorText(error) } }
  }
  async request(action, args = {}, sessionId, execution) {
    try {
      if (!this.shell) throw new Error('宿主 shell 不可用；无法刷新验证状态')
      const { projectRoot, skillRoot, session } = await this.context(args, sessionId)
      const request = { ...args, action, project_root: projectRoot, skill_root: skillRoot, session_id: session.id, author_id: session.authorId }
      for (const key of ['projectRoot', 'skillRoot', 'optionalCollab', 'paperFormat', 'mode']) delete request[key]
      const encoded = Buffer.from(JSON.stringify(request), 'utf8').toString('base64')
      const script = join(skillRoot, 'scripts/mathmodel.py')
      const windows = /^[A-Za-z]:[\\/]|^\\\\/.test(script)
      const quote = value => windows ? `'${String(value).replace(/'/g, "''")}'` : `'${String(value).replace(/'/g, "'\\''")}'`
      const command = `${windows ? '& ' : ''}${quote('python')} ${quote(script)} --request-base64 ${quote(encoded)}`
      const description = action === 'run' ? `数学建模运行：${JSON.stringify(args.argv)}；项目 ${projectRoot}` : `数学建模 ${action}；项目 ${projectRoot}`
      // Inherit the selected session's standing policy unchanged. The project
      // binding never becomes a replacement sandbox root or an elevated mode.
      const policy = this.ctx.get('sandboxPolicy')
      if (this.shell.sandboxMode !== undefined && !policy?.resolve) throw new Error('受限 shell 缺少宿主 sandboxPolicy，拒绝执行')
      const shellRequest = { command, workdir: projectRoot, description,
        timeoutMs: action === 'run' ? (Number(args.timeout) || 120) * 1000 + 10000 : 120000,
        stdoutMaxBytes: 4 * 1024 * 1024,
        env: { PYTHONUTF8: '1', PYTHONDONTWRITEBYTECODE: '1' },
        ...(policy?.resolve ? { sandboxPolicy: policy.resolve({ session: session.value }) } : {}),
        ...(execution?.signal ? { signal: execution.signal } : {}),
        ...(execution?.agent && this.ctx.get('shellEnv')?.collect ? { dshEnv: this.ctx.get('shellEnv').collect(execution) } : {}),
      }
      const spec = this.shell.resolve(shellRequest)
      const raw = this.shell.execute ? await (await this.shell.execute(spec)).result() : await this.shell.run(spec)
      if (raw.timedOut || raw.aborted || raw.signal || raw.sandbox?.denied || raw.sandbox?.runnerFailed) throw new Error('运行被超时、取消或宿主沙箱阻断；未将该请求视为成功')
      if (raw.stdout?.truncated) throw new Error('运行时 JSON 输出被宿主截断；请减少单次预览内容或归档旧运行记录')
      const stdout = typeof raw.stdout === 'string' ? raw.stdout : raw.stdout?.text || ''
      const stderr = typeof raw.stderr === 'string' ? raw.stderr : raw.stderr?.text || ''
      let value
      try { value = JSON.parse(stdout.trim()) } catch { throw new Error(`运行时未返回有效 JSON（退出码 ${raw.exitCode ?? '?'}）：${String(stderr || stdout).slice(0, 1000)}`) }
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('运行时响应必须是 JSON 对象')
      const result = { ...value, ok: raw.exitCode === 0 && value.ok !== false }
      if (action === 'init' && result.ok) {
        const binding = { projectRoot, skillRoot, cwd: session.cwd }
        this.bindings.set(session.id, binding)
        if ((await this.settings.read()).persistent) await this.settings.update({ bindings: { [session.id]: binding } })
        else result.bindingNotice = '会话绑定仅当前进程有效；重启后请重新初始化或显式指定 projectRoot'
      }
      return result
    } catch (error) { return { ok: false, error: errorText(error) } }
  }
  async snapshot(sessionId) {
    const { projectRoot } = await this.context({}, sessionId)
    const statePath = join(projectRoot, '.math-modeling/state.json')
    if (!await this.exists(statePath)) return { initialized: false }
    const value = JSON.parse(await this.fs.readText(await this.fs.resolve(statePath)))
    return { ...value, initialized: !!value.project, stale: true, snapshotAt: value.updated_at || value.updatedAt || value.completedAt || null,
      refreshNotice: '只读快照；请在当前会话调用 mm_state 重新验证产物变更。' }
  }
}

export function toolDefinition(name, description, properties, execute, required = []) {
  return { name, description, parameters: { type: 'object', properties, ...(required.length ? { required } : {}) },
    output: { schema: { type: 'object', additionalProperties: true }, render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }] },
    execute: async (args = {}, execution) => { try { return await execute(args, execution) } catch (error) { return { ok: false, error: errorText(error) } } },
  }
}
