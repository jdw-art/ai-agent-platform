<script setup lang="ts">
import { ref, watch } from "vue";
import Modal from "../Modal.vue";

interface ToolConfig {
  name: string;
  engine_config_override?: {
    smtp_host?: string;
    smtp_port?: number;
    smtp_user?: string;
    smtp_password?: string;
    sender_name?: string;
  };
}

const props = defineProps<{
  model: boolean;
  config: ToolConfig;
  readonly?: boolean;
}>();

const emit = defineEmits(["update:model", "save"]);

const localConfig = ref<ToolConfig>({ ...props.config });
const smtpHost = ref("");
const smtpPort = ref(465);
const smtpUser = ref("");
const smtpPassword = ref("");
const senderName = ref("AI Agent");

watch(() => props.model, (val) => {
  if (val) {
    localConfig.value = { ...props.config };
    const ov = props.config.engine_config_override || {};
    smtpHost.value = ov.smtp_host || "";
    smtpPort.value = ov.smtp_port || 465;
    smtpUser.value = ov.smtp_user || "";
    smtpPassword.value = ov.smtp_password || "";
    senderName.value = ov.sender_name || "AI Agent";
  }
});

const handleSave = () => {
  const updatedConfig = {
    ...localConfig.value,
    engine_config_override: {
      smtp_host: smtpHost.value.trim(),
      smtp_port: Number(smtpPort.value),
      smtp_user: smtpUser.value.trim(),
      smtp_password: smtpPassword.value.trim(),
      sender_name: senderName.value.trim()
    }
  };
  emit("save", updatedConfig);
  emit("update:model", false);
};
</script>

<template>
  <Modal
    v-if="model"
    title="邮件发送配置 (SMTP)"
    @close="emit('update:model', false)"
    size="max-w-md"
  >
    <div class="space-y-5">
      <div class="bg-indigo-50 p-4 rounded-xl border border-indigo-100 flex items-start space-x-3">
        <span class="text-xl">📧</span>
        <div>
          <p class="text-xs font-bold text-indigo-800">SMTP 配置说明</p>
          <p class="text-[10px] text-indigo-600 mt-1 leading-relaxed">
            请配置您的邮件服务器信息。建议使用 SSL (Port 465) 或 TLS (Port 587)。
            如果是 Gmail/QQ 等，请使用“应用专用密码”。
          </p>
        </div>
      </div>

      <div class="space-y-4">
        <div class="grid grid-cols-3 gap-4">
          <div class="col-span-2">
            <label class="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-1.5">SMTP Host</label>
            <input v-model="smtpHost" :disabled="readonly" placeholder="smtp.gmail.com" class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-primary disabled:bg-gray-50 disabled:text-gray-500 font-mono" />
          </div>
          <div>
            <label class="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-1.5">Port</label>
            <input type="number" v-model="smtpPort" :disabled="readonly" placeholder="465" class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-primary disabled:bg-gray-50 disabled:text-gray-500 font-mono" />
          </div>
        </div>

        <div>
          <label class="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-1.5">Sender Name</label>
          <input v-model="senderName" :disabled="readonly" placeholder="AI Assistant" class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-primary disabled:bg-gray-50 disabled:text-gray-500" />
        </div>

        <div>
          <label class="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-1.5">Email / Username</label>
          <input v-model="smtpUser" :disabled="readonly" placeholder="user@example.com" class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-primary disabled:bg-gray-50 disabled:text-gray-500 font-mono" />
        </div>

        <div>
          <label class="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-1.5">Password / App Password</label>
          <input v-model="smtpPassword" :disabled="readonly" type="password" placeholder="••••••••" class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-primary disabled:bg-gray-50 disabled:text-gray-500 font-mono" />
        </div>
      </div>

      <div class="flex justify-end space-x-3 pt-4 border-t border-gray-100">
        <button
          @click="emit('update:model', false)"
          class="px-4 py-2 text-sm text-gray-500 hover:text-gray-700"
        >
          取消
        </button>
        <button
          v-if="!readonly"
          @click="handleSave"
          class="px-8 py-2 bg-primary text-white text-sm rounded-xl hover:bg-primary-dark transition-colors font-bold shadow-lg shadow-primary/20"
        >
          确认保存
        </button>
      </div>
    </div>
  </Modal>
</template>
