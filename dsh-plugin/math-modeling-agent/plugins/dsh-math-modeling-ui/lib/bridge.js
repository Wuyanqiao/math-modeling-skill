import { Buffer } from 'node:buffer'
import { fileURLToPath } from 'node:url'
import { randomUUID } from 'node:crypto'
import { Config } from './settings-schema.js'

const settingStores = new WeakMap()
const sessionStores = new WeakMap()
const operationStores = new WeakMap()
const CHUNK_BYTES = 1024 * 1024
const MAX_INPUT_BYTES = 20 * CHUNK_BYTES
const INPUT_KINDS = new Set(['problem', 'attachment', 'paper-template', 'paper-requirements'])
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
    if (!operationStores.has(owner)) operationStores.set(owner, { initializing: new Map(), uploads: new Map() })
    this.operations = operationStores.get(owner)
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
  async skillRoot(explicit, requireRuntime = true) {
    for (const root of explicit ? [explicit] : [packageRoot, bundledRoot, sourceRoot]) {
      if (await this.exists(join(root, 'SKILL.md')) && (!requireRuntime || await this.exists(join(root, 'scripts/mathmodel.py')))) return this.path(root)
    }
    if (!requireRuntime) throw new Error('无法定位 Skill 根目录标记 SKILL.md；无法验证项目目录边界')
    throw new Error('缺少完整 Skill 运行时 scripts/mathmodel.py；请安装完整发行包或显式指定 skillRoot')
  }
  async context(args = {}, sessionId, requireRuntime = true) {
    const session = await this.session(sessionId)
    const saved = (await this.settings.read()).bindings[session.id] || this.bindings.get(session.id)
    const binding = saved?.cwd === session.cwd ? saved : null
    const projectRoot = await this.path(args.projectRoot || args.project_root || binding?.projectRoot || session.cwd)
    const skillRoot = await this.skillRoot(args.skillRoot || args.skill_root || binding?.skillRoot, requireRuntime)
    const info = await this.exists(projectRoot)
    if (!info || info.type !== 'directory') throw new Error('项目目录不存在或不是目录')
    const projectTarget = await this.fs.resolve(projectRoot)
    const skillTarget = await this.fs.resolve(skillRoot)
    if (this.fs.contains(skillTarget, projectTarget) || this.fs.contains(projectTarget, skillTarget)) throw new Error('Skill 与项目目录必须不同且互不包含')
    return { session, projectRoot, skillRoot }
  }
  async presentationContext(sessionId) {
    const settings = await this.settings.read()
    if (!settings.enabled || !sessionId) return { enabled: settings.enabled, eligible: false, initialized: false, hidden: true }
    const session = await this.session(sessionId)
    const projections = this.ctx.get('sessionProjections')
    const presetId = projections?.stateOf ? await projections.stateOf(session.value, 'agentPreset') : session.value.header?.agentPreset
    const presets = this.ctx.get('agentPresets')
    let presetName, hasWorkbench = false
    const agent = this.ctx.get('agents')?.get?.(session.id)
    if (agent && presets?.serviceFor) hasWorkbench = presets.serviceFor(agent, 'mathModelWorkbench')?.version === 2
    if (presetId && presets?.compositionInventory) {
      const preset = (await presets.compositionInventory()).find(item => item.id === presetId)
      presetName = preset?.name
      hasWorkbench ||= !!preset && !preset.broken && preset.rows.some(row => row.enabled === true && (row.fiberState === undefined || row.fiberState === 2) &&
        (row.moduleName === 'dsh-math-modeling-ui/workbench' || /(?:^|[/\\])dsh-math-modeling-ui[/\\]lib[/\\]workbench\.js$/.test(row.moduleName)))
    }
    let snapshot, contextError
    try { snapshot = await this.snapshot(session.id) } catch (error) { contextError = errorText(error) }
    const initialized = snapshot?.initialized === true
    return { enabled: true, eligible: initialized || hasWorkbench, initialized,
      session: { id: session.id, cwd: session.cwd, presetId: presetId || null, presetName, hasWorkbench },
      ...(initialized ? { project: snapshot.project } : {}), ...(contextError ? { contextError } : {}) }
  }
  async ensureProject(sessionId, options = {}, execution) {
    const session = await this.session(sessionId)
    const key = JSON.stringify([session.id, session.cwd])
    if (this.operations.initializing.has(key)) return this.operations.initializing.get(key)
    const task = (async () => {
      const context = await this.presentationContext(session.id)
      if (!context.enabled || !context.eligible) return { ok: false, code: 'workbench-not-selected', error: '当前会话未选择包含数学建模工作台的预设，也没有已初始化项目' }
      const args = context.initialized ? {} : { title: session.cwd.split(/[\\/]/).filter(Boolean).at(-1) || '数学建模项目', scope: 'full', profile: 'balanced', paper_format: 'word', ...options }
      const result = await this.request(context.initialized ? 'state' : 'init', args, session.id, execution)
      return result.ok === false ? result : { ok: true, ...await this.snapshot(session.id) }
    })()
    this.operations.initializing.set(key, task)
    try { return await task } finally { if (this.operations.initializing.get(key) === task) this.operations.initializing.delete(key) }
  }
  sandboxPolicy(session, capability) {
    const policy = this.ctx.get('sandboxPolicy')
    if (capability?.sandboxMode !== undefined && !policy?.resolve) throw new Error('受限能力缺少宿主 sandboxPolicy，拒绝执行')
    return policy?.resolve?.({ session: session.value })
  }
  async beginUpload(sessionId, { filename, kind, size }) {
    if (!INPUT_KINDS.has(kind)) throw new Error('输入类型必须为 problem、attachment、paper-template 或 paper-requirements')
    if (typeof filename !== 'string' || !filename.trim() || filename.length > 160 || /[\\/<>:"|?*\x00-\x1f]/.test(filename) || /[. ]$/.test(filename) || /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(filename)) throw new Error('文件名必须是最多160字符的安全单个文件名')
    if (!Number.isSafeInteger(size) || size <= 0 || size > MAX_INPUT_BYTES) throw new Error('每个文件必须非空且不超过20MiB')
    const context = await this.context({}, sessionId)
    const snapshot = await this.snapshot(sessionId)
    if (!snapshot.initialized) throw new Error('请先打开工作台初始化项目')
    const held = [...this.operations.uploads.values()].filter(item => item.sessionId === context.session.id)
    if (held.length >= 5 || held.reduce((total, item) => total + item.size, 0) + size > 100 * CHUNK_BYTES) throw new Error('当前会话暂存上传已达上限，请完成或取消现有上传')
    const upload_id = randomUUID().replaceAll('-', '')
    this.operations.uploads.set(upload_id, { sessionId: context.session.id, projectRoot: context.projectRoot, skillRoot: context.skillRoot, projectId: snapshot.project.project_id, filename, kind, size, received: 0, parts: [], busy: false })
    return { upload_id, chunk_bytes: CHUNK_BYTES, max_bytes: MAX_INPUT_BYTES }
  }
  async uploadRecord(sessionId, uploadId, checkProject = true) {
    const upload = this.operations.uploads.get(uploadId)
    if (!upload || upload.sessionId !== sessionId) throw new Error('上传不存在或不属于当前会话')
    if (upload.busy || upload.cancelTask) throw new Error('该上传正在处理或取消，请按顺序发送分块')
    if (checkProject) {
      const context = await this.context({}, sessionId)
      const snapshot = await this.snapshot(sessionId)
      if (context.projectRoot !== upload.projectRoot || snapshot.project?.project_id !== upload.projectId) throw new Error('上传期间项目已切换，请取消后重新选择文件')
    }
    if (upload.busy || upload.cancelTask) throw new Error('该上传正在处理或取消，请按顺序发送分块')
    return upload
  }
  async uploadChunk(sessionId, { upload_id, index, content_base64 }, execution) {
    const upload = await this.uploadRecord(sessionId, upload_id)
    if (!Number.isSafeInteger(index) || index !== upload.parts.length || index >= 20) throw new Error('分块序号必须从0开始连续递增，不能覆盖已写分块')
    if (typeof content_base64 !== 'string' || content_base64.length > Math.ceil(CHUNK_BYTES / 3) * 4 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(content_base64)) throw new Error('分块必须是最多1MiB的规范Base64')
    const bytes = Buffer.from(content_base64, 'base64')
    if (!bytes.length || bytes.length > CHUNK_BYTES || bytes.toString('base64') !== content_base64 || upload.received + bytes.length > upload.size) throw new Error('分块长度或编码与上传声明不一致')
    if (upload.received + bytes.length < upload.size && bytes.length !== CHUNK_BYTES) throw new Error('最后一块之外的分块必须恰好1MiB')
    upload.busy = true
    let settled
    upload.settled = new Promise(resolve => { settled = resolve })
    try {
      const relative = `.math-modeling/incoming/${upload_id}/${index}.base64`
      if (!this.fs.lstat || !this.fs.writeText) throw new Error('当前宿主缺少安全暂存所需的 lstat/writeText 能力')
      for (const item of ['.math-modeling', '.math-modeling/incoming', `.math-modeling/incoming/${upload_id}`]) {
        let info
        try { info = await this.fs.lstat(join(upload.projectRoot, item)) } catch (error) { if (!['FS_NOT_FOUND', 'ENOENT'].includes(error.code)) throw error }
        if (info && info.type !== 'directory') throw new Error('输入暂存目录不能是符号链接或普通文件')
      }
      const target = await this.fs.resolve(join(upload.projectRoot, relative))
      if (!this.fs.contains(await this.fs.resolve(upload.projectRoot), target)) throw new Error('输入暂存路径越出项目目录')
      const session = await this.session(sessionId)
      await this.fs.writeText(target, content_base64, { kind: 'createIfAbsent' }, execution?.signal, this.sandboxPolicy(session, this.fs))
      upload.parts.push(relative); upload.received += bytes.length
      return { upload_id, received_bytes: upload.received, next_index: upload.parts.length }
    } finally { upload.busy = false; settled() }
  }
  async commitUpload(sessionId, uploadId, execution) {
    const upload = await this.uploadRecord(sessionId, uploadId)
    if (upload.received !== upload.size) throw new Error('文件尚未完整上传')
    upload.busy = true
    let settled
    upload.settled = new Promise(resolve => { settled = resolve })
    try {
      const result = await this.request('input-import', { filename: upload.filename, kind: upload.kind, source_base64_parts: upload.parts, expected_size: upload.size }, sessionId, execution)
      if (result.ok !== false) this.operations.uploads.delete(uploadId)
      return result
    } finally { upload.busy = false; settled() }
  }
  async cancelUpload(sessionId, uploadId, execution) {
    const upload = this.operations.uploads.get(uploadId)
    if (!upload || upload.sessionId !== sessionId) throw new Error('上传不存在或不属于当前会话')
    if (upload.cancelTask) return upload.cancelTask
    const task = (async () => {
      await upload.settled
      if (!this.operations.uploads.has(uploadId)) return { ok: true, upload_id: uploadId, already_finished: true }
      upload.busy = true
      try {
        const result = await this.request('input-staging-cleanup', { upload_id: uploadId, projectRoot: upload.projectRoot, skillRoot: upload.skillRoot }, sessionId, execution)
        if (result.ok !== false) this.operations.uploads.delete(uploadId)
        return result
      } finally { upload.busy = false }
    })()
    upload.cancelTask = task
    try { return await task } finally { if (upload.cancelTask === task) delete upload.cancelTask }
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
      const useStdin = encoded.length > 8192
      const command = `${windows ? '& ' : ''}${quote('python')} ${quote(script)} --request-base64 ${quote(useStdin ? '-' : encoded)}`
      const description = action === 'run' ? `数学建模运行：${JSON.stringify(args.argv)}；项目 ${projectRoot}` : `数学建模 ${action}；项目 ${projectRoot}`
      // Inherit the selected session's standing policy unchanged. The project
      // binding never becomes a replacement sandbox root or an elevated mode.
      const sandboxPolicy = this.sandboxPolicy(session, this.shell)
      const shellRequest = { command, workdir: projectRoot, description,
        timeoutMs: action === 'run' ? (Number(args.timeout) || 120) * 1000 + 10000 : action === 'environment' ? 90000 : 120000,
        stdoutMaxBytes: 4 * 1024 * 1024,
        env: { PYTHONUTF8: '1', PYTHONDONTWRITEBYTECODE: '1' },
        ...(useStdin ? { stdin: encoded } : {}),
        ...(sandboxPolicy ? { sandboxPolicy } : {}),
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
    } catch (error) {
      const detail = errorText(error)
      if (/\bgrantWrite\b/i.test(detail) && /\bWin32\s+5\b|\bERROR_ACCESS_DENIED\b/i.test(detail)) {
        return { ok: false, code: 'sandbox-workspace-authorization-failed',
          error: '项目目录无法获得 DSH Windows 沙箱写入授权。请检查目录权限，恢复授权后重试。\n宿主原始错误：' + detail }
      }
      return { ok: false, error: detail, ...(error?.code ? { code: error.code } : {}) }
    }
  }
  async snapshot(sessionId) {
    const { projectRoot } = await this.context({}, sessionId, false)
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
