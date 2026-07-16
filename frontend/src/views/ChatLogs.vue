<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue';
import { agentApi, type AgentExecutionHistory, type AIAgent } from '../api/agent';
import { 
  ChatBubbleLeftRightIcon, 
  FunnelIcon, 
  ArrowPathIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  MagnifyingGlassIcon,
  ClockIcon,
  ExclamationCircleIcon,
  ArrowTopRightOnSquareIcon,
  UserIcon,
  SparklesIcon
} from '@heroicons/vue/24/outline';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';

// Auth info
const cachedUser = localStorage.getItem('user_info');
const userInfo = ref(cachedUser ? JSON.parse(cachedUser) : null);
const isAdmin = computed(() => userInfo.value?.role === 'admin');

// State
const logs = ref<AgentExecutionHistory[]>([]);
const agents = ref<AIAgent[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(15);
const loading = ref(false);
const showFilters = ref(false);

// Filters
const filters = ref({
  agent_id: '',
  username: '',
  keyword: '',
  status: '',
  start_date: '',
  end_date: ''
});

// Detail State
const selectedTraceId = ref<string | null>(null);
const traceDetail = ref<any>(null);
const traceLoading = ref(false);
const showTraceModal = ref(false);

const fetchAgents = async () => {
  try {
    const res = await agentApi.listAgents();
    agents.value = res.data;
  } catch (e) {
    console.error('Failed to fetch agents', e);
  }
};

const fetchLogs = async () => {
  loading.value = true;
  try {
    const params: any = {
      page: page.value,
      page_size: pageSize.value,
      ...filters.value
    };
    
    // Clean empty values
    Object.keys(params).forEach(key => {
      if (params[key] === '') delete params[key];
    });

    const res = await agentApi.getChatHistory(params);
    logs.value = res.data.data.items;
    total.value = res.data.data.total;
  } catch (e) {
    console.error('Failed to fetch logs', e);
  } finally {
    loading.value = false;
  }
};

const resetFilters = () => {
  filters.value = {
    agent_id: '',
    username: '',
    keyword: '',
    status: '',
    start_date: '',
    end_date: ''
  };
  page.value = 1;
  fetchLogs();
};

const applyFilters = () => {
  page.value = 1;
  fetchLogs();
};

const viewTrace = async (traceId: string) => {
  selectedTraceId.value = traceId;
  showTraceModal.value = true;
  traceLoading.value = true;
  try {
    const res = await agentApi.getChatTrace(traceId);
    traceDetail.value = res.data.data;
  } catch (e) {
    console.error('Failed to fetch trace', e);
  } finally {
    traceLoading.value = false;
  }
};

const formatDate = (dateStr: string) => {
  return format(new Date(dateStr), 'yyyy-MM-dd HH:mm:ss', { locale: zhCN });
};

const getAgentName = (agentId: string) => {
  const agent = agents.value.find(a => a.id === agentId);
  return agent ? agent.display_name : agentId;
};

const getStatusClass = (status: string) => {
  if (status === 'success') return 'bg-green-100 text-green-700 border-green-200';
  if (status === 'error') return 'bg-red-100 text-red-700 border-red-200';
  return 'bg-gray-100 text-gray-700 border-gray-200';
};

onMounted(() => {
  fetchAgents();
  fetchLogs();
});

watch([page, pageSize], () => {
  fetchLogs();
});
</script>

<template>
  <div class="space-y-6 max-w-[1600px] mx-auto pb-20">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <div class="p-2 bg-primary/10 rounded-xl">
          <ChatBubbleLeftRightIcon class="h-6 w-6 text-primary" />
        </div>
        <div>
          <h1 class="text-2xl font-bold text-gray-900 tracking-tight">聊天日志</h1>
          <p class="text-xs text-gray-500 mt-0.5 font-medium uppercase tracking-wider">Independent Chat Execution Audit</p>
        </div>
      </div>
      <div class="flex items-center space-x-3">
        <button
          @click="fetchLogs"
          class="flex items-center px-4 py-2 bg-white border border-gray-200 rounded-xl shadow-sm text-sm font-bold text-gray-600 hover:bg-gray-50 transition-all active:scale-95"
        >
          <ArrowPathIcon class="w-4 h-4 mr-2" :class="{ 'animate-spin': loading }" />
          刷新列表
        </button>
      </div>
    </div>


    <!-- Filter Bar -->
    <div class="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
      <div 
        @click="showFilters = !showFilters"
        class="px-6 py-4 flex items-center justify-between cursor-pointer hover:bg-gray-50 transition-colors"
      >
        <div class="flex items-center space-x-2">
          <FunnelIcon class="w-5 h-5 text-gray-400" />
          <span class="text-sm font-bold text-gray-700">高级检索筛选</span>
        </div>
        <ChevronRightIcon class="w-5 h-5 text-gray-300 transition-transform duration-300" :class="{ 'rotate-90': showFilters }" />
      </div>

      <transition name="filter-slide">
        <div v-show="showFilters" class="px-6 pb-6 pt-2 border-t border-gray-50">
          <div class="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-6">
            <!-- Agent Selection -->
            <div class="space-y-1.5">
              <label class="text-[11px] font-bold text-gray-400 uppercase tracking-wider">选择智能体</label>
              <select 
                v-model="filters.agent_id"
                class="w-full text-xs border-gray-100 rounded-xl bg-gray-50 focus:ring-4 focus:ring-primary/5 focus:border-primary/20 transition-all p-2.5"
              >
                <option value="">全部智能体</option>
                <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.display_name }}</option>
              </select>
            </div>

            <!-- User Search (Admin) -->
            <div v-if="isAdmin" class="space-y-1.5">
              <label class="text-[11px] font-bold text-gray-400 uppercase tracking-wider">用户检索</label>
              <div class="relative">
                <MagnifyingGlassIcon class="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
                <input 
                  v-model="filters.username"
                  type="text"
                  placeholder="输入用户名..."
                  class="w-full text-xs border-gray-100 rounded-xl bg-gray-50 pl-9 focus:ring-4 focus:ring-primary/5 focus:border-primary/20 transition-all p-2.5"
                />
              </div>
            </div>

            <!-- Keyword -->
            <div class="space-y-1.5">
              <label class="text-[11px] font-bold text-gray-400 uppercase tracking-wider">正文关键字</label>
              <div class="relative">
                <MagnifyingGlassIcon class="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
                <input 
                  v-model="filters.keyword"
                  type="text"
                  placeholder="搜索问题或回复内容..."
                  class="w-full text-xs border-gray-100 rounded-xl bg-gray-50 pl-9 focus:ring-4 focus:ring-primary/5 focus:border-primary/20 transition-all p-2.5"
                />
              </div>
            </div>

             <!-- Status -->
             <div class="space-y-1.5">
              <label class="text-[11px] font-bold text-gray-400 uppercase tracking-wider">执行状态</label>
              <select 
                v-model="filters.status"
                class="w-full text-xs border-gray-100 rounded-xl bg-gray-50 focus:ring-4 focus:ring-primary/5 focus:border-primary/20 transition-all p-2.5"
              >
                <option value="">全部状态</option>
                <option value="success">成功 (Success)</option>
                <option value="error">异常 (Error)</option>
              </select>
            </div>

            <!-- Start Date -->
            <div class="space-y-1.5">
              <label class="text-[11px] font-bold text-gray-400 uppercase tracking-wider">开始日期</label>
              <input 
                v-model="filters.start_date"
                type="date"
                class="w-full text-xs border-gray-100 rounded-xl bg-gray-50 focus:ring-4 focus:ring-primary/5 focus:border-primary/20 transition-all p-2.5"
              />
            </div>

            <!-- End Date -->
            <div class="space-y-1.5">
              <label class="text-[11px] font-bold text-gray-400 uppercase tracking-wider">结束日期</label>
              <input 
                v-model="filters.end_date"
                type="date"
                class="w-full text-xs border-gray-100 rounded-xl bg-gray-50 focus:ring-4 focus:ring-primary/5 focus:border-primary/20 transition-all p-2.5"
              />
            </div>
          </div>

          <div class="mt-6 pt-6 border-t border-gray-50 flex justify-end space-x-3">
             <button 
                @click="resetFilters"
                class="px-5 py-2 text-xs font-bold text-gray-400 hover:text-gray-600 transition-colors"
             >
                重置
             </button>
             <button 
                @click="applyFilters"
                class="px-6 py-2 bg-gray-900 text-white text-xs font-bold rounded-xl hover:bg-black transition-all shadow-lg active:scale-95"
             >
                执行筛选
             </button>
          </div>
        </div>
      </transition>
    </div>

    <!-- Data Table -->
    <div class="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
      <div v-if="loading && logs.length === 0" class="py-20 flex flex-col items-center justify-center space-y-4">
         <ArrowPathIcon class="w-8 h-8 text-primary animate-spin" />
         <p class="text-sm font-bold text-gray-400 uppercase tracking-widest">Loading History...</p>
      </div>

      <div v-else-if="logs.length === 0" class="py-20 flex flex-col items-center justify-center space-y-6">
         <div class="p-6 bg-gray-50 rounded-full text-gray-200">
           <ChatBubbleLeftRightIcon class="w-16 h-16" />
         </div>
         <div class="text-center">
           <p class="text-sm font-bold text-gray-600">未发现聊天记录</p>
           <p class="text-xs text-gray-400 mt-1">请尝试调整筛选条件或稍后再试</p>
         </div>
      </div>

      <div v-else class="overflow-x-auto">
        <table class="w-full text-left">
          <thead>
            <tr class="bg-gray-50/50 border-b border-gray-100">
              <th class="px-6 py-4 text-[11px] font-bold text-gray-400 uppercase tracking-wider">用户 / 智能体</th>
              <th class="px-6 py-4 text-[11px] font-bold text-gray-400 uppercase tracking-wider">提问摘要</th>
              <th class="px-6 py-4 text-[11px] font-bold text-gray-400 uppercase tracking-wider">响应内容</th>
              <th class="px-6 py-4 text-[11px] font-bold text-gray-400 uppercase tracking-wider">执行状态 / 耗时</th>
              <th class="px-6 py-4 text-[11px] font-bold text-gray-400 uppercase tracking-wider text-right">执行时间</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-50">
            <tr 
              v-for="log in logs" 
              :key="log.id"
              class="group hover:bg-primary/[0.02] transition-colors cursor-pointer"
              @click="viewTrace(log.trace_id)"
            >
              <td class="px-6 py-5">
                <div class="flex items-center space-x-3">
                   <div v-if="isAdmin" class="flex flex-col">
                      <div class="flex items-center text-xs font-bold text-gray-700">
                        <UserIcon class="w-3 h-3 mr-1 text-gray-400" />
                        {{ log.username || '匿名' }}
                      </div>
                      <div class="flex items-center text-[10px] text-primary font-medium mt-1">
                        <SparklesIcon class="w-3 h-3 mr-1" />
                        {{ getAgentName(log.agent_id) }}
                      </div>
                   </div>
                   <div v-else class="flex items-center text-xs font-bold text-primary">
                      <SparklesIcon class="w-3.5 h-3.5 mr-1.5" />
                      {{ getAgentName(log.agent_id) }}
                   </div>
                </div>
              </td>
              <td class="px-6 py-5">
                <div class="max-w-xs xl:max-w-md">
                   <p class="text-[11px] font-medium text-gray-700 line-clamp-2 leading-relaxed tracking-tight">{{ log.query }}</p>
                </div>
              </td>
              <td class="px-6 py-5">
                <div class="max-w-xs xl:max-w-md">
                   <div v-if="log.summary" class="inline-flex items-center px-2 py-1 bg-gray-50 rounded-lg border border-gray-100/50">
                     <span class="text-[10px] font-mono italic text-gray-500 leading-relaxed line-clamp-2">
                       /* {{ log.summary }} */
                     </span>
                   </div>
                   <span v-else class="text-[10px] text-gray-300 italic">无响应摘要</span>
                </div>
              </td>
              <td class="px-6 py-5 whitespace-nowrap">
                <div class="flex items-center space-x-2">
                   <span class="px-2 py-0.5 rounded-full text-[9px] font-bold border" :class="getStatusClass(log.status)">
                      {{ log.status === 'success' ? 'SUCCESS' : 'ERROR' }}
                   </span>
                   <span class="text-[10px] font-mono text-gray-400">{{ log.execution_time_ms ? `${log.execution_time_ms.toFixed(0)}ms` : '-' }}</span>
                </div>
              </td>
              <td class="px-6 py-5 text-right whitespace-nowrap">
                <div class="flex flex-col items-end">
                  <span class="text-[11px] font-bold text-gray-600">{{ formatDate(log.created_at) }}</span>
                  <div class="opacity-0 group-hover:opacity-100 transition-opacity mt-1">
                    <span class="text-[9px] font-bold text-primary uppercase flex items-center">
                       查看详情
                       <ArrowTopRightOnSquareIcon class="w-3 h-3 ml-1" />
                    </span>
                  </div>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div class="px-6 py-4 bg-gray-50 border-t border-gray-100 flex items-center justify-between">
        <div class="text-[11px] font-bold text-gray-400 uppercase tracking-widest">
           Showing {{ (page-1) * pageSize + 1 }} to {{ Math.min(page * pageSize, total) }} of {{ total }} records
        </div>
        <div class="flex items-center space-x-2">
           <button 
             :disabled="page === 1"
             @click="page--"
             class="p-2 border border-gray-200 rounded-lg hover:bg-white transition-all disabled:opacity-30 disabled:hover:bg-transparent"
           >
             <ChevronLeftIcon class="w-4 h-4" />
           </button>
           <div class="flex items-center space-x-1">
              <span class="text-xs font-bold text-gray-700 px-3">Page {{ page }}</span>
           </div>
           <button 
             :disabled="page * pageSize >= total"
             @click="page++"
             class="p-2 border border-gray-200 rounded-lg hover:bg-white transition-all disabled:opacity-30 disabled:hover:bg-transparent"
           >
             <ChevronRightIcon class="w-4 h-4" />
           </button>
        </div>
      </div>
    </div>

    <!-- Trace Detail Modal (Right SideDrawer Style) -->
    <transition name="drawer-slide">
      <div v-if="showTraceModal" class="fixed inset-0 z-50 overflow-hidden flex justify-end">
         <div class="absolute inset-0 bg-black/20 backdrop-blur-sm" @click="showTraceModal = false"></div>
         
         <div class="relative w-full max-w-2xl bg-white shadow-2xl flex flex-col h-full transform transition-transform">
            <!-- Modal Header -->
            <div class="px-8 py-6 border-b border-gray-100 flex items-center justify-between bg-gradient-to-r from-gray-50 to-white">
               <div class="flex items-center space-x-4">
                  <div class="p-2.5 bg-primary/10 rounded-xl">
                    <SparklesIcon class="h-6 w-6 text-primary" />
                  </div>
                  <div>
                    <h2 class="text-lg font-bold text-gray-900 leading-tight">执行链路详情</h2>
                    <p class="text-[10px] text-gray-400 font-mono tracking-tighter uppercase">{{ selectedTraceId }}</p>
                  </div>
               </div>
               <button @click="showTraceModal = false" class="p-2 text-gray-400 hover:bg-gray-100 rounded-xl transition-colors">
                  <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
               </button>
            </div>

            <!-- Trace Content -->
            <div class="flex-1 overflow-y-auto custom-scrollbar p-8 space-y-10">
               <div v-if="traceLoading" class="flex flex-col items-center justify-center py-20 space-y-4">
                  <ArrowPathIcon class="w-8 h-8 text-primary animate-spin" />
                  <p class="text-xs font-bold text-gray-400 uppercase tracking-widest">Loading steps...</p>
               </div>
               
               <template v-else-if="traceDetail">
                  <!-- Steps Timeline -->
                  <div class="relative space-y-12 pb-10">
                     <div class="absolute left-[21px] top-2 bottom-0 w-0.5 bg-gray-100"></div>

                     <div v-for="(step, idx) in traceDetail.steps" :key="idx" class="relative pl-14">
                        <!-- Dot -->
                        <div class="absolute left-0 top-1 w-11 flex justify-center">
                           <div class="w-3.5 h-3.5 rounded-full ring-8 ring-white bg-white flex items-center justify-center z-10 border-2" 
                              :class="step.status === 'success' ? 'border-primary' : 'border-red-500'"
                           >
                              <div class="w-1.5 h-1.5 rounded-full" :class="step.status === 'success' ? 'bg-primary' : 'bg-red-500'"></div>
                           </div>
                        </div>

                        <!-- Step Info -->
                        <div class="space-y-4">
                           <div class="flex items-center space-x-3">
                              <span class="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Step {{ step.step_number }}</span>
                              <span 
                                class="px-2 py-0.5 rounded text-[9px] font-bold border uppercase tracking-wider"
                                :class="{
                                  'bg-blue-50 text-blue-600 border-blue-100': step.event_type === 'thought',
                                  'bg-amber-50 text-amber-600 border-amber-100': step.event_type === 'tool_call',
                                  'bg-green-50 text-green-600 border-green-100': step.event_type === 'tool_result' || step.event_type === 'final_answer',
                                  'bg-red-50 text-red-600 border-red-100': step.event_type === 'error'
                                }"
                              >
                                {{ step.event_type }}
                              </span>
                              <span v-if="step.execution_time_ms" class="text-[10px] text-gray-400 flex items-center">
                                 <ClockIcon class="w-3 h-3 mr-1" />
                                 {{ step.execution_time_ms.toFixed(0) }}ms
                              </span>
                           </div>

                           <!-- Payload Content -->
                           <div class="bg-gray-50/50 rounded-2xl border border-gray-100 p-5 space-y-4">
                              <div v-if="step.tool_name" class="flex items-center text-xs font-bold text-gray-700">
                                 <code class="px-2 py-1 bg-gray-200/50 rounded-lg mr-2 font-mono text-primary">{{ step.tool_name }}</code>
                              </div>

                              <!-- Input -->
                              <div v-if="step.tool_input">
                                 <label class="text-[9px] font-bold text-gray-400 uppercase mb-2 block tracking-widest pl-1">Params / Thought</label>
                                 <div class="bg-white border border-gray-100 rounded-xl p-4 shadow-sm">
                                    <pre class="text-xs text-gray-600 whitespace-pre-wrap leading-relaxed font-sans">{{ typeof step.tool_input === 'string' ? step.tool_input : JSON.stringify(step.tool_input, null, 2) }}</pre>
                                 </div>
                              </div>

                              <!-- Output -->
                              <div v-if="step.tool_output">
                                 <label class="text-[9px] font-bold text-gray-400 uppercase mb-2 block tracking-widest pl-1">Result / Answer</label>
                                 <div class="bg-white border border-gray-100 rounded-xl p-4 shadow-sm">
                                    <pre class="text-xs text-gray-700 whitespace-pre-wrap leading-relaxed font-sans font-medium">{{ typeof step.tool_output === 'string' ? step.tool_output : JSON.stringify(step.tool_output, null, 2) }}</pre>
                                 </div>
                              </div>

                              <!-- Error -->
                              <div v-if="step.error_message" class="flex items-start bg-red-50/50 border border-red-100 rounded-xl p-4 text-red-600 space-x-2">
                                 <ExclamationCircleIcon class="w-4 h-4 flex-shrink-0 mt-0.5" />
                                 <p class="text-[11px] font-medium leading-relaxed">{{ step.error_message }}</p>
                              </div>
                           </div>
                        </div>
                     </div>
                  </div>
               </template>

               <div v-else class="text-center py-20 text-gray-300">
                  发现了一个空的链路。
               </div>
            </div>
         </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 4px; height: 4px; }
.custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #E5E7EB; border-radius: 2px; }
.custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #D1D5DB; }

.filter-slide-enter-active, .filter-slide-leave-active {
  transition: all 0.3s ease-out;
  max-height: 500px;
  overflow: hidden;
}
.filter-slide-enter-from, .filter-slide-leave-to {
  max-height: 0;
  opacity: 0;
  padding-top: 0;
  padding-bottom: 0;
  margin-top: 0;
}

.drawer-slide-enter-active, .drawer-slide-leave-active {
  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}
.drawer-slide-enter-from, .drawer-slide-leave-to {
  transform: translateX(100%);
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
