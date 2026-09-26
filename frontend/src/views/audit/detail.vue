<template>
  <section class="page" data-module="audit-detail">
    <header class="page-head">
      <div>
        <h2>内审记录详情</h2>
        <p class="page-desc">内审编号 {{ entry?.['内审编号'] ?? entryId }} 的检查条款、整改期限与整改记录。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn ghost" to="/audit">返回内审列表</RouterLink>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

    <template v-if="entry">
      <div class="conclusion-banner" :class="conclusionTone(conclusion)">
        <span class="conclusion-label">当前结论</span>
        <strong>{{ conclusion || '—' }}</strong>
        <span v-if="requiresRecheck(entry)" class="recheck-hint">
          检查条款需重新核对，核对完成前整改材料不予接收
        </span>
      </div>

      <table class="data-table detail-table">
        <tbody>
          <tr v-for="column in columns" :key="column">
            <th>{{ column }}</th>
            <td>{{ entry[column] ?? '—' }}</td>
          </tr>
          <tr>
            <th>可执行动作</th>
            <td class="row-actions">
              <template v-if="actions.length">
                <button
                  v-for="action in actions"
                  :key="action"
                  class="link"
                  type="button"
                  :disabled="busy === action"
                  @click="runAction(action)"
                >{{ action }}</button>
              </template>
              <span v-else class="muted-text">当前没有可执行动作</span>
            </td>
          </tr>
        </tbody>
      </table>

      <form v-if="canRectify" class="rectify-panel" @submit.prevent="submitRectification">
        <h3>提交整改</h3>
        <label class="filter-item">
          <span>整改说明</span>
          <textarea v-model="rectifyNote" rows="3" placeholder="说明针对不符合项采取的整改措施"></textarea>
        </label>
        <div class="rectify-foot">
          <button class="btn primary" type="submit" :disabled="submitting">提交整改</button>
          <span v-if="actionMessage" class="action-msg">{{ actionMessage }}</span>
        </div>
      </form>
      <div v-else-if="actionMessage" class="rectify-panel">
        <h3>提交整改</h3>
        <p class="action-msg">{{ actionMessage }}</p>
      </div>

      <section class="history-panel">
        <h3>历史整改记录</h3>
        <table v-if="history.length" class="data-table">
          <thead>
            <tr>
              <th v-for="col in historyColumns" :key="col">{{ col }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in history" :key="idx">
              <td v-for="col in historyColumns" :key="col">{{ item[col] ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted-text">暂无历史整改记录</p>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'
import {
  ACTION_SUBMIT,
  conclusionTone,
  getActions,
  getConclusion,
  requiresRecheck,
  type AuditEntry,
} from './rules'

const route = useRoute()
const entryId = String(route.params.id ?? '')

const columns = ["内审编号", "内审日期", "内审部门", "检查条款", "检查结果", "不符合项", "整改期限", "内审状态"]
const historyColumns = ["日期", "检查条款", "不符合项", "整改期限", "整改说明"]

const entry = ref<AuditEntry | null>(null)
const errorMessage = ref('')
const actionMessage = ref('')
const busy = ref('')
const submitting = ref(false)
const rectifyNote = ref('')

const conclusion = computed(() => (entry.value ? getConclusion(entry.value) : ''))
const actions = computed(() => (entry.value ? getActions(entry.value) : []))
const canRectify = computed(() => actions.value.includes(ACTION_SUBMIT))
const history = computed(() => entry.value?.rectification_history ?? [])

async function load() {
  errorMessage.value = ''
  try {
    const response = await request(`/api/audit/${entryId}`)
    const payload = await response.json().catch(() => null) as { detail?: string } | null
    if (!response.ok) {
      throw new Error(payload?.detail || '内审记录详情读取失败')
    }
    entry.value = payload as AuditEntry
    actionMessage.value = ''
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '内审记录详情读取失败'
  }
}

async function runAction(action: string) {
  actionMessage.value = ''
  busy.value = action
  try {
    const response = await request(`/api/audit/${entryId}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null) as { message?: string } | null
    if (!response.ok) {
      throw new Error(payload?.message || '内审检查动作未生效，请稍后重试')
    }
    actionMessage.value = payload?.message ?? '操作已生效'
    await load()
  } catch (error) {
    actionMessage.value = error instanceof Error ? error.message : '内审检查操作失败'
  } finally {
    busy.value = ''
  }
}

async function submitRectification() {
  actionMessage.value = ''
  submitting.value = true
  try {
    const response = await request(`/api/audit/${entryId}/rectification`, {
      method: 'POST',
      body: JSON.stringify({ values: { 整改说明: rectifyNote.value } }),
    })
    const payload = await response.json().catch(() => null) as { message?: string } | null
    if (!response.ok) {
      throw new Error(payload?.message || '整改未被接收，请稍后重试')
    }
    actionMessage.value = payload?.message ?? '整改已提交'
    rectifyNote.value = ''
    await load()
  } catch (error) {
    actionMessage.value = error instanceof Error ? error.message : '提交整改失败'
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.conclusion-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #fff;
  border: 1px solid var(--border);
  border-left-width: 4px;
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 12px;
}
.conclusion-banner.muted { border-left-color: var(--muted); }
.conclusion-banner.info { border-left-color: #1f6feb; }
.conclusion-banner.success { border-left-color: #067647; }
.conclusion-banner.warning { border-left-color: #b54708; }
.conclusion-banner.danger { border-left-color: #b42318; }
.conclusion-label { color: var(--muted); font-size: 12px; }
.recheck-hint { color: #b42318; font-size: 12px; }
.detail-table th { width: 140px; background: #f8fafc; }
.rectify-panel,
.history-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  margin-top: 14px;
}
.rectify-panel h3,
.history-panel h3 { margin: 0 0 10px; font-size: 14px; }
.rectify-panel textarea { width: 100%; resize: vertical; }
.rectify-foot { display: flex; align-items: center; gap: 12px; margin-top: 8px; }
.action-msg { color: var(--muted); font-size: 12px; }
.muted-text { color: var(--muted); }
</style>
