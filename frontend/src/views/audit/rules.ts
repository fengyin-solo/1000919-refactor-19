/**
 * 内审可执行动作与整改判断的前端唯一入口。
 *
 * 真正的判定权在后端（app/services/audit_rules.py），列表接口与详情接口都会带回
 * `conclusion` 与 `available_actions`；前端三处（列表、详情、提交整改）只消费这份
 * 后端结论，不再各自按检查条款/整改期限重算，避免同一内审编号走出不同结论。
 *
 * 这里仅保留与后端一致的动作/结论词汇表及少量只读展示辅助，不做第二套判定。
 */

export const ACTION_START = '开始审核'
export const ACTION_RECORD = '记录结果'
export const ACTION_SUBMIT = '提交整改'

export const AUDIT_ACTIONS = [ACTION_START, ACTION_RECORD, ACTION_SUBMIT] as const
export type AuditAction = (typeof AUDIT_ACTIONS)[number]

/** 结论 -> 列表/详情上的展示色调，纯展示用途，不参与判定。 */
const CONCLUSION_TONE: Record<string, string> = {
  待审核: 'muted',
  审核中: 'info',
  符合: 'success',
  待整改: 'warning',
  整改超期: 'danger',
  重新核对: 'danger',
  条款未登记: 'warning',
}

export interface AuditEntry {
  id: number
  status?: string
  conclusion?: string
  available_actions?: string[]
  rectification_history?: Array<Record<string, string>>
  [key: string]: string | number | null | undefined | string[] | Array<Record<string, string>>
}

/** 后端给什么动作就显示什么动作；后端没带时不臆造，返回空（刷新后由接口补齐）。 */
export function getActions(entry: AuditEntry): string[] {
  return Array.isArray(entry.available_actions) ? entry.available_actions : []
}

export function getConclusion(entry: AuditEntry): string {
  return typeof entry.conclusion === 'string' ? entry.conclusion : ''
}

export function conclusionTone(conclusion: string): string {
  return CONCLUSION_TONE[conclusion] ?? 'muted'
}

/** 是否必须先重新核对检查条款——供详情页提示，结论同样取自后端。 */
export function requiresRecheck(entry: AuditEntry): boolean {
  return getConclusion(entry) === '重新核对' || getConclusion(entry) === '整改超期'
}
