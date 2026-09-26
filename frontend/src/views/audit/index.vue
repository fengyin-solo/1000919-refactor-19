<template>
  <section class="page" data-module="audit">
    <header class="page-head">
      <div>
        <h2>内审检查管理</h2>
        <p class="page-desc">维护内审记录，围绕内审编号、内审日期、内审部门、检查条款做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记内审记录</button>
        <button class="btn" type="button" @click="exportRows">导出内审检查清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <button v-if="column === '内审编号'" class="link" type="button" @click="openDetail(Number(row.id))">
              {{ row[column] ?? '—' }}
            </button>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <template v-if="rowActions(row).length">
              <button
                v-for="action in rowActions(row)"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else class="muted-text">—</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无内审检查数据，可先登记内审记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条内审检查记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <div class="modal-card">
        <header class="modal-head">
          <h3>内审详情 · {{ detail['内审编号'] ?? '—' }}</h3>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </header>

        <table class="data-table detail-table">
          <tbody>
            <tr v-for="column in columns" :key="column">
              <th>{{ column }}</th>
              <td>{{ detail[column] ?? '—' }}</td>
            </tr>
          </tbody>
        </table>

        <div class="detail-decision">
          <p><span class="decision-label">判定结论：</span>{{ detail.conclusion }}</p>
          <p>
            <span class="decision-label">下一步责任人：</span>{{ detail.next_owner ?? '—' }}
            <span class="decision-label decision-gap">检查条款重新核查：</span>{{ detail.need_recheck ? '需要' : '不需要' }}
          </p>
          <p>
            <span class="decision-label">可执行动作：</span>
            <template v-if="detail.available_actions?.length">{{ detail.available_actions.join('、') }}</template>
            <span v-else>无</span>
          </p>
        </div>

        <section class="history-block">
          <h4>历史整改记录</h4>
          <table v-if="historyRows.length" class="data-table">
            <thead>
              <tr><th>动作</th><th>检查条款</th><th>整改期限</th><th>提交后状态</th></tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in historyRows" :key="index">
                <td>{{ item['动作'] ?? '—' }}</td>
                <td>{{ item['检查条款'] ?? '—' }}</td>
                <td>{{ item['整改期限'] ?? '—' }}</td>
                <td>{{ item['目标状态'] ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="muted-text">暂无整改提交记录</p>
        </section>

        <footer class="modal-foot">
          <span v-if="detailError" class="error-text">{{ detailError }}</span>
          <button
            v-for="action in detail.available_actions ?? []"
            :key="action"
            class="btn primary"
            type="button"
            @click="runDetailAction(action)"
          >
            {{ action }}
          </button>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type HistoryItem = Record<string, string | number | null>
type Row = Record<string, string | number | null> & {
  available_actions?: string[]
  need_recheck?: boolean
  conclusion?: string
  next_owner?: string | null
  整改记录?: HistoryItem[]
}

const ENDPOINT = '/api/audit'
const columns = ["内审编号", "内审日期", "内审部门", "检查条款", "检查结果", "不符合项", "整改期限", "内审状态"]
const statuses = ["待审核", "审核中", "已通过", "待整改"]
const stats = [{"label": "待审核记录", "value": 0}, {"label": "审核中记录", "value": 0}, {"label": "已通过记录", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const detail = ref<Row | null>(null)
const detailError = ref('')
const historyRows = computed<HistoryItem[]>(() => {
  const history = detail.value?.整改记录
  return Array.isArray(history) ? history : []
})

function rowActions(row: Row): string[] {
  // 动作清单只认后端统一判定，列表与详情都不自行推断。
  return row.available_actions ?? []
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '内审记录登记入口尚未接入审批流'
}

function closeDetail() {
  detail.value = null
  detailError.value = ''
}

async function openDetail(id: number) {
  detailError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    if (!response.ok) {
      throw new Error('内审详情读取失败')
    }
    detail.value = (await response.json()) as Row
  } catch (error) {
    detail.value = null
    detailError.value = error instanceof Error ? error.message : '内审详情读取失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.message || '内审检查动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '内审检查操作失败'
  }
}

async function runDetailAction(action: string) {
  if (!detail.value) {
    return
  }
  detailError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${detail.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string; entry?: Row } | null
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || '内审检查动作未生效，请稍后重试')
    }
    detail.value = payload.entry ?? detail.value
    await reload()
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : '内审检查操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('内审记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '内审检查列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.muted-text { color: var(--muted); }

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(16, 24, 40, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}

.modal-card {
  background: #fff;
  border-radius: 8px;
  width: 720px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 48px);
  overflow: auto;
  padding: 16px 20px;
}

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.modal-head h3 { margin: 0; font-size: 16px; }

.detail-table th { width: 120px; white-space: nowrap; }

.detail-decision {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #f8fafc;
  font-size: 13px;
}

.detail-decision p { margin: 4px 0; }

.decision-label { color: var(--muted); }
.decision-gap { margin-left: 16px; }

.history-block { margin-top: 12px; }
.history-block h4 { margin: 0 0 8px; font-size: 14px; }

.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}
</style>
