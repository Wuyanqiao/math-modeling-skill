// DSH provides schemastery. Keeping this import optional also permits the
// dependency-free adapter tests and older hosts without Config-derived forms.
let Config
try {
  const { default: z } = await import('@deepseek-ai/schemastery')
  const fields = {
    enabled: z.boolean().default(true).description('显示数学建模项目看板'),
    bindings: z.dict(z.object({ projectRoot: z.string(), skillRoot: z.string(), cwd: z.string() })).default({}).description('由工作台管理的会话项目绑定'),
  }
  if (fields.enabled.volatile) { fields.enabled = fields.enabled.volatile(); fields.bindings = fields.bindings.volatile() }
  Config = z.object(fields)
} catch (error) {
  if (error.code !== 'ERR_MODULE_NOT_FOUND') throw error
}
export { Config }
