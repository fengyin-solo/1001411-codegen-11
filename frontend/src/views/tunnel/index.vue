<template>
  <section class="page" data-module="tunnel">
    <header class="page-head">
      <div>
        <h2>隧道设施管理</h2>
        <p class="page-desc">维护隧道设施，围绕隧道编码、隧道名称、隧道长度、断面形式做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记隧道设施</button>
        <button class="btn" type="button" :disabled="importing" @click="pickFile">
          {{ importing ? '正在导入…' : '导入台账材料' }}
        </button>
        <button class="btn ghost" type="button" @click="downloadTemplate">下载导入模板</button>
        <button class="btn" type="button" @click="exportRows">导出隧道设施清单</button>
        <input
          ref="fileInput"
          type="file"
          accept=".csv,.tsv,text/csv"
          class="visually-hidden"
          @change="onFilePicked"
        />
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <section v-if="importResult" class="import-panel">
      <header class="import-head">
        <strong>导入结果：批次 {{ importResult.batch_id }}</strong>
        <span>{{ importResult.message }}</span>
        <span v-if="importResult.deduplicated" class="dup-badge">同一份材料只算一次，本次未重复入账</span>
      </header>
      <p class="import-summary">
        共 {{ importResult.total }} 行，收下 {{ importResult.accepted }} 行，被拒 {{ importResult.rejected }} 行
        <template v-if="importResult.duplicate_codes.length">
          ；重复编码：{{ importResult.duplicate_codes.join('、') }}
        </template>
      </p>
      <table class="data-table">
        <thead>
          <tr>
            <th>行号</th>
            <th v-for="column in importColumns" :key="column">{{ column }}</th>
            <th>结论</th>
            <th>原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in importResult.rows" :key="row.row_no" :class="{ 'row-rejected': !row.accepted }">
            <td>{{ row.row_no }}</td>
            <td v-for="column in importColumns" :key="column">{{ row.values[column] ?? '—' }}</td>
            <td>
              <span class="decision" :class="row.accepted ? 'accepted' : 'rejected'">
                {{ row.accepted ? '收下' : '被拒' }}
              </span>
            </td>
            <td>{{ row.reasons.join('；') || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="batches.length" class="import-panel">
      <header class="import-head">
        <strong>导入记录</strong>
        <span>结果列表与隧道台账按批次一一对应</span>
      </header>
      <table class="data-table">
        <thead>
          <tr>
            <th>批次号</th>
            <th>材料名称</th>
            <th>导入时间</th>
            <th>总行数</th>
            <th>收下</th>
            <th>被拒</th>
            <th>重复编码</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="batch in batches" :key="batch.batch_id">
            <td>{{ batch.batch_id }}</td>
            <td>{{ batch.filename }}</td>
            <td>{{ batch.imported_at }}</td>
            <td>{{ batch.total }}</td>
            <td>{{ batch.accepted }}</td>
            <td>{{ batch.rejected }}</td>
            <td>{{ batch.duplicate_codes.join('、') || '—' }}</td>
            <td><button class="link" type="button" @click="showBatch(batch.batch_id)">查看逐行结果</button></td>
          </tr>
        </tbody>
      </table>
    </section>

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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无隧道设施数据，可先登记隧道设施</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条隧道设施记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson, request, upload } from '@/api/client'

type Row = Record<string, string | number | null>

interface ImportRow {
  row_no: number
  accepted: boolean
  reasons: string[]
  values: Record<string, string | number | null>
  entry_id: number | null
}

interface ImportBatch {
  batch_id: string
  filename: string
  imported_at: string
  deduplicated: boolean
  total: number
  accepted: number
  rejected: number
  duplicate_codes: string[]
  rows: ImportRow[]
  message: string
}

const ENDPOINT = '/api/tunnel'
const columns = ["隧道编码", "隧道名称", "隧道长度", "断面形式", "照明方式", "通风方式", "管养单位", "隧道状态"]
const actions = ["办理移交", "安排检修", "停用隧道"]
const statuses = ["待移交", "正常养护", "检修封闭", "已停用"]
const stats = [{"label": "在养隧道", "value": 0}, {"label": "检修中隧道", "value": 0}, {"label": "隧道总长", "value": 0}]
const importColumns = ["隧道编码", "隧道名称", "隧道长度", "断面形式", "照明方式", "通风方式"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const fileInput = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const importResult = ref<ImportBatch | null>(null)
const batches = ref<Omit<ImportBatch, 'rows' | 'deduplicated' | 'message'>[]>([])

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '隧道设施登记入口尚未接入审批流'
}

function pickFile() {
  fileInput.value?.click()
}

async function onFilePicked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  importing.value = true
  errorMessage.value = ''
  try {
    const response = await upload(`${ENDPOINT}/import`, file)
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload?.detail ?? '台账材料导入失败，请检查固定列后重试')
    }
    importResult.value = payload as ImportBatch
    await Promise.all([reload(), reloadBatches()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '台账材料导入失败'
  } finally {
    importing.value = false
  }
}

function downloadTemplate() {
  const header = '隧道编码,隧道名称,隧道长度,断面形式,照明通风方式'
  const example = 'TUNN-0101,云峰山隧道,1520,分离式,LED照明/机械通风'
  const blob = new Blob([`\ufeff${header}\n${example}\n`], { type: 'text/csv;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = '隧道台账导入模板.csv'
  link.click()
  URL.revokeObjectURL(link.href)
}

async function showBatch(batchId: string) {
  errorMessage.value = ''
  try {
    importResult.value = await fetchJson<ImportBatch>(`${ENDPOINT}/imports/${batchId}`)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导入批次读取失败'
  }
}

async function reloadBatches() {
  try {
    const payload = await fetchJson<{ items: typeof batches.value }>(`${ENDPOINT}/imports`)
    batches.value = payload.items ?? []
  } catch {
    batches.value = []
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? '隧道设施动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '隧道设施操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('隧道设施列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '隧道设施列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void reloadBatches()
})
</script>

<style scoped>
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
.import-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.import-head {
  display: flex;
  gap: 10px;
  align-items: baseline;
  font-size: 13px;
  margin-bottom: 6px;
}
.import-head span {
  color: var(--muted);
  font-size: 12px;
}
.import-summary {
  font-size: 12px;
  color: var(--muted);
  margin: 0 0 8px;
}
.dup-badge {
  color: #b45309;
}
.decision.accepted {
  color: #027a48;
}
.decision.rejected {
  color: #b42318;
}
.row-rejected td {
  background: #fef6f5;
}
</style>
