<template>
  <section class="page" data-module="tunnel">
    <header class="page-head">
      <div>
        <h2>隧道设施管理</h2>
        <p class="page-desc">维护隧道设施，围绕隧道编码、隧道名称、隧道长度、断面形式做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记隧道设施</button>
        <button class="btn" type="button" @click="pickFile">导入台账材料</button>
        <button class="btn" type="button" @click="exportRows">导出隧道设施清单</button>
        <input
          ref="fileInput"
          type="file"
          accept=".csv,.txt"
          style="display: none"
          @change="onFileChange"
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
        <strong>
          批次 {{ importResult.batch_id }}：共 {{ importResult.total }} 行，
          收下 {{ importResult.accepted }} 行，被拒 {{ importResult.rejected }} 行
        </strong>
        <span v-if="importResult.duplicated" class="dup-tag">同一份材料已导入过，本次未重复入账</span>
        <button class="link" type="button" @click="importResult = null">收起</button>
      </header>
      <table class="data-table">
        <thead>
          <tr>
            <th>材料行号</th>
            <th>隧道编码</th>
            <th>结果</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in importResult.results" :key="item.line">
            <td>{{ item.line }}</td>
            <td>{{ item.code || '—' }}</td>
            <td :class="item.accepted ? 'ok-text' : 'error-text'">{{ item.accepted ? '收下' : '被拒' }}</td>
            <td>{{ item.reason }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="imports.length" class="import-panel">
      <header class="import-head">
        <strong>导入结果列表</strong>
        <span class="page-desc">每批的收下数与隧道台账实际落库数逐批对账</span>
      </header>
      <table class="data-table">
        <thead>
          <tr>
            <th>批次号</th>
            <th>材料名</th>
            <th>导入时间</th>
            <th>材料行数</th>
            <th>收下</th>
            <th>被拒</th>
            <th>台账落库</th>
            <th>对账</th>
            <th>明细</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="batch in imports" :key="batch.batch_id">
            <td>{{ batch.batch_id }}</td>
            <td>{{ batch.filename || '—' }}</td>
            <td>{{ batch.created_at }}</td>
            <td>{{ batch.total }}</td>
            <td>{{ batch.accepted }}</td>
            <td>{{ batch.rejected }}</td>
            <td>{{ batch.ledger_count }}</td>
            <td :class="batch.matched ? 'ok-text' : 'error-text'">{{ batch.matched ? '一致' : '不一致' }}</td>
            <td><button class="link" type="button" @click="viewBatch(batch.batch_id)">查看逐行</button></td>
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

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type ImportRowResult = { line: number; code: string; accepted: boolean; reason: string }
type ImportBatch = {
  batch_id: string
  filename: string
  created_at: string
  total: number
  accepted: number
  rejected: number
  ledger_count: number
  matched: boolean
  duplicated?: boolean
  results: ImportRowResult[] | null
}

const ENDPOINT = '/api/tunnel'
const columns = ["隧道编码", "隧道名称", "隧道长度", "断面形式", "照明方式", "通风方式", "管养单位", "隧道状态"]
const actions = ["办理移交", "安排检修", "停用隧道"]
const statuses = ["待移交", "正常养护", "检修封闭", "已停用"]
const stats = [{"label": "在养隧道", "value": 0}, {"label": "检修中隧道", "value": 0}, {"label": "隧道总长", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const fileInput = ref<HTMLInputElement | null>(null)
const importResult = ref<ImportBatch | null>(null)
const imports = ref<ImportBatch[]>([])

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

async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  errorMessage.value = ''
  try {
    const content = await file.text()
    const response = await request(`${ENDPOINT}/import`, {
      method: 'POST',
      body: JSON.stringify({ filename: file.name, content }),
    })
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload?.detail ?? '台账材料导入失败，请稍后重试')
    }
    importResult.value = payload as ImportBatch
    await Promise.all([reload(), loadImports()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '台账材料导入失败'
  }
}

async function viewBatch(batchId: string) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/imports/${batchId}`)
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload?.detail ?? '导入批次读取失败')
    }
    importResult.value = payload as ImportBatch
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导入批次读取失败'
  }
}

async function loadImports() {
  try {
    const response = await request(`${ENDPOINT}/imports`)
    if (!response.ok) return
    const payload = await response.json()
    imports.value = payload.items ?? []
  } catch {
    imports.value = []
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('隧道设施动作未生效，请稍后重试')
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
  void loadImports()
})
</script>

<style scoped>
.import-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.import-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.import-head .page-desc {
  margin: 0;
}
.dup-tag {
  color: #b45309;
  font-size: 12px;
}
.ok-text {
  color: #15803d;
}
</style>
