<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from '../utils/axios'
import RagFlowResourceSelector from '../components/RagFlowResourceSelector.vue'
import { useToast } from '../composables/useToast'
import { useUser } from '../composables/useUser'

type RetrievalChunk = {
  id?: string
  chunk_id?: string
  document_id?: string
  document_name?: string
  doc_name?: string
  similarity?: number
  score?: number
  content?: string
  text?: string
}

type RagFlowConfigSummary = {
  api_url: string
  api_key_configured: boolean
  configured: boolean
}

const { showToast } = useToast()
const { hasPermission } = useUser()

const showDatasetSelector = ref(false)
const datasetIds = ref<string[]>([])
const query = ref('')
const topK = ref(5)
const similarityThreshold = ref(0.2)
const vectorSimilarityWeight = ref(0.3)
const loading = ref(false)
const results = ref<RetrievalChunk[]>([])
const errorMessage = ref('')
const ragflowConfig = ref<RagFlowConfigSummary | null>(null)

const canTest = computed(() => hasPermission('element:knowledge:test_retrieval'))
const datasetIdsText = computed(() => datasetIds.value.join(','))
const ragflowApiUrl = computed(() => ragflowConfig.value?.api_url || '未配置')
const friendlyRagFlowError = computed(() => {
  if (!errorMessage.value) return ''
  const lower = errorMessage.value.toLowerCase()
  if (
    lower.includes('ragflow') ||
    lower.includes('bad gateway') ||
    lower.includes('failed to connect') ||
    lower.includes('configuration missing')
  ) {
    return '当前无法连接 RAGFlow 服务，请确认 RAGFlow 服务是否可访问、网关是否正常，以及系统配置中的 RAGFlow 地址/API Key 是否正确。'
  }
  return errorMessage.value
})

const extractError = (err: unknown) => {
  const anyErr = err as any
  return anyErr?.response?.data?.detail || anyErr?.response?.data?.message || anyErr?.message || '检索失败'
}

const handleDatasetSelect = (value: string | string[]) => {
  datasetIds.value = Array.isArray(value) ? value : [value].filter(Boolean)
}

const validate = () => {
  if (datasetIds.value.length === 0) {
    showToast('请至少选择一个知识库', 'warning')
    return false
  }
  if (!query.value.trim()) {
    showToast('请输入检索问题', 'warning')
    return false
  }
  if (topK.value < 1 || topK.value > 50) {
    showToast('top_k 需在 1 到 50 之间', 'warning')
    return false
  }
  return true
}

const runRetrieval = async () => {
  if (!validate()) return
  loading.value = true
  errorMessage.value = ''
  results.value = []
  try {
    const response = await axios.post('/api/portal/ragflow/retrieval-test', {
      query: query.value.trim(),
      dataset_ids: datasetIds.value,
      top_k: topK.value,
      similarity_threshold: similarityThreshold.value,
      vector_similarity_weight: vectorSimilarityWeight.value
    })
    results.value = response.data?.data || []
    showToast(`检索完成，命中 ${results.value.length} 条`, 'success')
  } catch (err) {
    errorMessage.value = extractError(err)
    showToast(errorMessage.value, 'error')
  } finally {
    loading.value = false
  }
}

const copyText = async (text: string, message = '已复制') => {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    showToast(message, 'success')
  } catch {
    showToast('复制失败', 'error')
  }
}

const copyResult = (chunk: RetrievalChunk) => {
  const payload = {
    dataset_ids: datasetIds.value,
    chunk_id: chunk.chunk_id || chunk.id,
    document_name: chunk.document_name || chunk.doc_name,
    score: chunk.similarity ?? chunk.score,
    content: chunk.content || chunk.text
  }
  copyText(JSON.stringify(payload, null, 2), '检索结果关键信息已复制')
}

const formatScore = (chunk: RetrievalChunk) => {
  const score = chunk.similarity ?? chunk.score
  return typeof score === 'number' ? score.toFixed(4) : '-'
}

const fetchRagFlowConfig = async () => {
  try {
    const response = await axios.get('/api/portal/ragflow/config')
    ragflowConfig.value = response.data?.data || null
  } catch {
    ragflowConfig.value = null
  }
}

onMounted(fetchRagFlowConfig)
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between pb-4 shrink-0">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">检索测试</h1>
        <p class="text-sm text-gray-500 mt-1">直接调用 RAGFlow Retrieval API，验证知识库 chunk 命中质量。</p>
        <p class="text-xs text-gray-400 mt-1.5">
          当前 RAGFlow 地址：
          <a :href="ragflowApiUrl" target="_blank" rel="noopener noreferrer" class="font-mono text-primary hover:underline">{{ ragflowApiUrl }}</a>
          <span v-if="ragflowConfig && !ragflowConfig.api_key_configured" class="ml-2 text-amber-600">API Key 未配置</span>
        </p>
      </div>
    </div>

    <!-- Left-Right Split -->
    <div class="flex gap-5 flex-1 min-h-0">

      <!-- Left: Search Conditions -->
      <aside class="w-[380px] shrink-0 flex flex-col gap-4">
        <section class="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 space-y-4 flex flex-col flex-1 overflow-y-auto">

          <!-- Dataset IDs -->
          <div>
            <label class="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">知识库</label>
            <div class="flex gap-2">
              <input
                :value="datasetIdsText"
                readonly
                class="flex-1 border border-gray-200 rounded-lg px-3 py-2 bg-gray-50 text-xs font-mono truncate"
                placeholder="请先选择知识库"
              />
              <button
                class="px-3 py-2 rounded-lg bg-primary text-white text-xs font-semibold hover:bg-primary/90 transition-all whitespace-nowrap shrink-0"
                @click="showDatasetSelector = true"
              >
                选择
              </button>
            </div>
          </div>

          <!-- Query -->
          <div>
            <label class="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Query 检索问题</label>
            <textarea
              v-model="query"
              rows="5"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary resize-none"
              placeholder="输入要测试的检索问题..."
            ></textarea>
          </div>

          <!-- Parameters -->
          <div class="space-y-3">
            <label class="block text-xs font-semibold text-gray-500 uppercase tracking-wider">参数调节</label>
            <div class="grid grid-cols-3 gap-3">
              <div>
                <span class="block text-xs text-gray-500 mb-1">top_k</span>
                <input v-model.number="topK" type="number" min="1" max="50" class="w-full border border-gray-200 rounded-lg px-2.5 py-1.5 text-sm" />
              </div>
              <div>
                <span class="block text-xs text-gray-500 mb-1">相似度阈值</span>
                <input v-model.number="similarityThreshold" type="number" min="0" max="1" step="0.01" class="w-full border border-gray-200 rounded-lg px-2.5 py-1.5 text-sm" />
              </div>
              <div>
                <span class="block text-xs text-gray-500 mb-1">向量权重</span>
                <input v-model.number="vectorSimilarityWeight" type="number" min="0" max="1" step="0.01" class="w-full border border-gray-200 rounded-lg px-2.5 py-1.5 text-sm" />
              </div>
            </div>
          </div>

          <!-- Execute -->
          <div class="pt-2 mt-auto">
            <button
              class="w-full px-5 py-2.5 rounded-xl bg-gray-900 hover:bg-gray-800 text-white text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
              :disabled="loading || !canTest"
              @click="runRetrieval"
            >
              <svg v-if="loading" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
              </svg>
              {{ loading ? '检索中...' : '执行检索' }}
            </button>
            <p class="text-[10px] text-gray-400 mt-2 text-center">检索测试会写入审计日志</p>
          </div>
        </section>
      </aside>

      <!-- Right: Results Panel -->
      <section class="flex-1 bg-white rounded-2xl border border-gray-200 shadow-sm flex flex-col min-w-0 overflow-hidden">
        <!-- Results header -->
        <div class="px-5 py-3.5 border-b border-gray-100 flex items-center justify-between shrink-0">
          <div class="flex items-center gap-2">
            <h2 class="font-semibold text-gray-900">命中结果</h2>
            <span v-if="results.length" class="text-xs bg-primary/10 text-primary font-bold px-2 py-0.5 rounded-full">{{ results.length }}</span>
          </div>
          <span class="text-xs text-gray-400">{{ results.length > 0 ? `共 ${results.length} 条命中` : '等待检索' }}</span>
        </div>

        <!-- Error alert -->
        <div v-if="errorMessage" class="mx-4 mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 shrink-0">
          <div class="font-semibold">RAGFlow 暂时不可用</div>
          <div class="mt-1">{{ friendlyRagFlowError }}</div>
          <div class="mt-2 text-xs text-amber-700">
            配置地址：<a :href="ragflowApiUrl" target="_blank" rel="noopener noreferrer" class="font-mono hover:underline">{{ ragflowApiUrl }}</a>
          </div>
          <div class="mt-1 text-xs text-amber-600">原始错误：{{ errorMessage }}</div>
        </div>

        <!-- Results body (scrollable) -->
        <div class="flex-1 overflow-y-auto">
          <!-- Loading state -->
          <div v-if="loading" class="flex flex-col items-center justify-center h-full gap-3 text-gray-400">
            <span class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></span>
            <span class="text-sm">正在检索...</span>
          </div>
          <!-- Empty state -->
          <div v-else-if="results.length === 0" class="flex flex-col items-center justify-center h-full gap-3 text-gray-400">
            <svg class="w-12 h-12 text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <span class="text-sm">在左侧输入条件后执行检索</span>
          </div>
          <!-- Results list -->
          <div v-else class="divide-y divide-gray-100">
            <article v-for="(chunk, idx) in results" :key="chunk.chunk_id || chunk.id" class="p-5 space-y-3 hover:bg-gray-50/50 transition-colors">
              <div class="flex items-start justify-between gap-4">
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <span class="text-xs font-bold text-gray-400 font-mono shrink-0">#{{ idx + 1 }}</span>
                    <h3 class="font-semibold text-gray-900 truncate">{{ chunk.document_name || chunk.doc_name || '未知文档' }}</h3>
                  </div>
                  <p class="text-xs text-gray-500 mt-1 font-mono">
                    Chunk: {{ chunk.chunk_id || chunk.id || '-' }} · 相似度: <span class="font-bold" :class="(chunk.similarity ?? chunk.score ?? 0) >= 0.5 ? 'text-emerald-600' : 'text-amber-600'">{{ formatScore(chunk) }}</span>
                  </p>
                </div>
                <button class="px-2.5 py-1.5 rounded-lg border border-gray-200 text-xs hover:bg-gray-100 transition-colors shrink-0" @click="copyResult(chunk)">复制</button>
              </div>
              <p class="text-sm text-gray-700 whitespace-pre-wrap bg-gray-50 rounded-xl p-4 leading-relaxed border border-gray-100">{{ chunk.content || chunk.text || '无内容片段' }}</p>
            </article>
          </div>
        </div>
      </section>
    </div>

    <RagFlowResourceSelector
      v-model="showDatasetSelector"
      type="dataset"
      :initial-selected="datasetIds"
      @select="handleDatasetSelect"
    />
  </div>
</template>
