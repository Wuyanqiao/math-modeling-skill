import { RuntimeBridge, createSettings } from './bridge.js'
export { Config } from './settings-schema.js'

export const name = 'dsh-math-modeling-ui'
export const inject = ['connection', 'settings', 'fs', 'shell', 'sessions']
export const MM_RPC_CHANNEL = '/math-modeling-ui'
export const MM_ENDPOINTS = Object.freeze({ state: 'mm.state', setEnabled: 'mm.setEnabled', getEnabled: 'mm.getEnabled', artifact: 'mm.artifact', runLog: 'mm.runLog' })
const ok = value => ({ ok: true, value })
const fail = message => ({ ok: false, error: { code: 'bad-request', message, details: {} } })

export function apply(ctx) {
  if (!ctx.connection?.rpc?.handle || !ctx.get('fs')) return () => {}
  const bridge = new RuntimeBridge(ctx)
  const settings = createSettings(ctx)

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
      return fail(`未知操作: ${endpoint}`)
    } catch (error) { return fail(String(error.message || error)) }
  })
}
