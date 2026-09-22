import { RuntimeBridge, createSettings } from './bridge.js'
import { TaskStartService } from './task-start.js'
export { Config } from './settings-schema.js'

export const name = 'dsh-math-modeling-ui'
export const inject = ['connection', 'settings', 'fs', 'shell', 'sessions']
export const MM_RPC_CHANNEL = '/math-modeling-ui'
export const MM_ENDPOINTS = Object.freeze({ state: 'mm.state', context: 'mm.context', ensureProject: 'mm.ensureProject', configure: 'mm.configure', environment: 'mm.environment', inputs: 'mm.inputs', inputRead: 'mm.inputRead',
  startOptions: 'mm.startOptions', startRun: 'mm.startRun',
  importBegin: 'mm.importBegin', importChunk: 'mm.importChunk', importCommit: 'mm.importCommit', importCancel: 'mm.importCancel',
  setEnabled: 'mm.setEnabled', getEnabled: 'mm.getEnabled', artifact: 'mm.artifact', runLog: 'mm.runLog', checkpointCreate: 'mm.checkpointCreate', checkpointRestore: 'mm.checkpointRestore' })
const ok = value => ({ ok: true, value })
const fail = (message, code = 'bad-request') => ({ ok: false, error: { code, message, details: {} } })

export function apply(ctx) {
  if (!ctx.connection?.rpc?.handle || !ctx.get('fs')) return () => {}
  const bridge = new RuntimeBridge(ctx)
  const settings = createSettings(ctx)
  const taskStart = new TaskStartService(ctx, bridge)

  async function state(payload, signal) {
    if (!(await settings.read()).enabled) return ok({ hidden: true })
    if (!payload.sessionId) return ok({ hidden: true, reason: 'no-session' })
    let snapshot
    try { snapshot = await bridge.snapshot(payload.sessionId) }
    catch (error) {
      const binding = (await settings.read()).bindings[payload.sessionId]
      return binding ? fail(String(error.message || error)) : ok({ hidden: true, reason: 'no-project' })
    }
    if (!snapshot.initialized) return ok({ hidden: true, reason: 'no-project' })
    if (!payload.refresh) return ok(snapshot)
    const result = await bridge.request('state', {}, payload.sessionId, { signal })
    if (result.ok === false) return ok({ ...snapshot, refreshError: result.error || '宿主未完成刷新；当前显示已保存快照。' })
    return ok({ ...result, stale: false, snapshotAt: new Date().toISOString() })
  }

  return ctx.connection.rpc.handle(MM_RPC_CHANNEL, async (endpoint, payload = {}, signal) => {
    try {
      if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return fail('请求必须为对象')
      if (endpoint === MM_ENDPOINTS.startOptions) return ok(await taskStart.options(payload.sessionId, { signal }))
      if (endpoint === MM_ENDPOINTS.startRun) return ok(await taskStart.start(payload, { signal }))
      if (endpoint === MM_ENDPOINTS.context) return ok(await bridge.presentationContext(payload.sessionId))
      if (endpoint === MM_ENDPOINTS.ensureProject) {
        if (!payload.sessionId) return fail('初始化需要当前会话')
        const result = await bridge.ensureProject(payload.sessionId, {}, { signal })
        return result.ok === false ? fail(result.error, result.code) : ok(result)
      }
      if (endpoint === MM_ENDPOINTS.configure) {
        if (!payload.sessionId || !payload.settings || typeof payload.settings !== 'object' || Array.isArray(payload.settings)) return fail('配置需要当前会话和 settings 对象')
        const result = await bridge.request('configure', { settings: payload.settings }, payload.sessionId, { signal })
        return result.ok === false ? fail(result.error, result.code) : ok(result)
      }
      if (endpoint === MM_ENDPOINTS.environment) {
        if (typeof payload.sessionId !== 'string' || !payload.sessionId) return fail('环境检测需要当前会话')
        if (!(await settings.read()).enabled) return fail('数学建模看板已关闭', 'workbench-disabled')
        const result = await bridge.request('environment', {}, payload.sessionId, { signal })
        return result.ok === false ? fail(result.error || '环境检测失败', result.code) : ok(result)
      }
      if (endpoint === MM_ENDPOINTS.inputs || endpoint === MM_ENDPOINTS.inputRead) {
        if (!payload.sessionId) return fail('读取输入资料需要当前会话')
        if (endpoint === MM_ENDPOINTS.inputRead && typeof payload.input_id !== 'string') return fail('缺少输入资料 id')
        const result = await bridge.request(endpoint === MM_ENDPOINTS.inputs ? 'input-list' : 'input-read', { ...(payload.input_id ? { input_id: payload.input_id } : {}) }, payload.sessionId, { signal })
        return result.ok === false ? fail(result.error, result.code) : ok(result)
      }
      if ([MM_ENDPOINTS.importBegin, MM_ENDPOINTS.importChunk, MM_ENDPOINTS.importCommit, MM_ENDPOINTS.importCancel].includes(endpoint)) {
        if (typeof payload.sessionId !== 'string' || !payload.sessionId) return fail('导入需要当前会话')
        let result
        if (endpoint === MM_ENDPOINTS.importBegin) result = await bridge.beginUpload(payload.sessionId, payload)
        else {
          if (typeof payload.upload_id !== 'string' || !/^[a-f0-9]{32}$/.test(payload.upload_id)) return fail('无效上传 id')
          if (endpoint === MM_ENDPOINTS.importChunk) result = await bridge.uploadChunk(payload.sessionId, payload, { signal })
          else if (endpoint === MM_ENDPOINTS.importCommit) result = await bridge.commitUpload(payload.sessionId, payload.upload_id, { signal })
          else result = await bridge.cancelUpload(payload.sessionId, payload.upload_id, { signal })
        }
        return result.ok === false ? fail(result.error, result.code) : ok(result)
      }
      if (endpoint === MM_ENDPOINTS.state) return await state(payload, signal)
      if (endpoint === MM_ENDPOINTS.getEnabled) {
        const value = await settings.read()
        return ok({ enabled: value.enabled, persistent: value.persistent })
      }
      if (endpoint === MM_ENDPOINTS.setEnabled) {
        if (typeof payload.enabled !== 'boolean') return fail('enabled 必须是布尔值')
        await settings.update({ enabled: payload.enabled })
        return ok({ enabled: (await settings.read()).enabled })
      }
      if (endpoint === MM_ENDPOINTS.artifact) {
        if (!payload.sessionId || typeof payload.path !== 'string') return fail('预览需要当前会话和项目内路径')
        const result = await bridge.request('artifact-read', { path: payload.path }, payload.sessionId, { signal })
        return result.ok === false ? fail(result.error || '无法预览文件') : ok(result)
      }
      if (endpoint === MM_ENDPOINTS.runLog) {
        if (!payload.sessionId || typeof payload.run_id !== 'string' || !['stdout', 'stderr'].includes(payload.stream)) return fail('读取日志需要当前会话、运行 id 和日志名称')
        const result = await bridge.request('run-log-read', { run_id: payload.run_id, stream: payload.stream }, payload.sessionId, { signal })
        return result.ok === false ? fail(result.error || '无法读取日志') : ok(result)
      }
      if (endpoint === MM_ENDPOINTS.checkpointCreate) {
        if (!payload.sessionId || (payload.name !== undefined && typeof payload.name !== 'string')) return fail('创建快照需要当前会话，名称必须为文本')
        const result = await bridge.request('checkpoint-create', { name: payload.name || `工作台快照 ${new Date().toISOString()}` }, payload.sessionId, { signal })
        return result.ok === false ? fail(result.error || '无法创建快照', result.code) : ok(result)
      }
      if (endpoint === MM_ENDPOINTS.checkpointRestore) {
        if (!payload.sessionId || typeof payload.checkpoint_id !== 'string' || typeof payload.apply !== 'boolean') return fail('恢复需要当前会话、快照 id 和明确的 apply 布尔值')
        if (payload.apply && !Number.isSafeInteger(payload.expected_revision)) return fail('确认恢复需要预览返回的 expected_revision')
        const args = { checkpoint_id: payload.checkpoint_id, apply: payload.apply, ...(payload.apply ? { expected_revision: payload.expected_revision } : {}) }
        const result = await bridge.request('checkpoint-restore', args, payload.sessionId, { signal })
        return result.ok === false ? fail(result.error || '无法恢复快照', result.code) : ok(result)
      }
      return fail(`未知操作: ${endpoint}`)
    } catch (error) { return fail(String(error.message || error), error.code) }
  })
}
