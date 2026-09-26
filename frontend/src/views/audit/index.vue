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
            <RouterLink v-if="column === '内审编号'" class="link" :to="`/audit/${row.id}`">
              {{ row[column] ?? '—' }}
            </RouterLink>
            <template v-else>
              {{ row[column] ?? '—' }}
              <span
                v-if="column === '内审状态' && getConclusion(row)"
                class="conclusion-tag"
                :class="conclusionTone(getConclusion(row))"
              >{{ getConclusion(row) }}</span>
            </template>
          </td>
          <td class="row-actions">
            <template v-if="getActions(row).length">
              <button
                v-for="action in getActions(row)"
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
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { conclusionTone, getActions, getConclusion, type AuditEntry } from './rules'

const ENDPOINT = '/api/audit'
const columns = ["内审编号", "内审日期", "内审部门", "检查条款", "检查结果", "不符合项", "整改期限", "内审状态"]
const stats = [{"label": "待审核记录", "value": 0}, {"label": "审核中记录", "value": 0}, {"label": "已通过记录", "value": 0}]

const rows = ref<AuditEntry[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

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

async function runAction(action: string, row: AuditEntry) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null) as { message?: string } | null
    if (!response.ok) {
      throw new Error(payload?.message || '内审检查动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '内审检查操作失败'
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
.conclusion-tag {
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 4px;
  font-size: 12px;
  border: 1px solid var(--border);
}
.conclusion-tag.muted { color: var(--muted); }
.conclusion-tag.info { color: #1f6feb; border-color: #1f6feb; }
.conclusion-tag.success { color: #067647; border-color: #067647; }
.conclusion-tag.warning { color: #b54708; border-color: #b54708; }
.conclusion-tag.danger { color: #b42318; border-color: #b42318; }
.muted-text { color: var(--muted); }
</style>
