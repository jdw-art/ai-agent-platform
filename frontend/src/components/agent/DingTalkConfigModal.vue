<script setup lang="ts">
import { ref, watch } from "vue";
import Modal from "../Modal.vue";

interface ToolConfig {
  name: string;
  engine_config_override?: {
    webhook_url?: string;
    secret?: string;
  };
}

const props = defineProps<{
  model: boolean;
  config: ToolConfig;
  readonly?: boolean;
}>();

const emit = defineEmits(["update:model", "save"]);

const localConfig = ref<ToolConfig>({ ...props.config });
const webhookUrl = ref("");
const secret = ref("");

watch(() => props.model, (val) => {
  if (val) {
    localConfig.value = { ...props.config };
    webhookUrl.value = props.config.engine_config_override?.webhook_url || "";
    secret.value = props.config.engine_config_override?.secret || "";
  }
});

const handleSave = () => {
  const updatedConfig = {
    ...localConfig.value,
    engine_config_override: {
      webhook_url: webhookUrl.value.trim(),
      secret: secret.value.trim()
    }
  };
  emit("save", updatedConfig);
  emit("update:model", false);
};
</script>

<template>
  <Modal
    v-if="model"
    title="钉钉通知工具配置"
    @close="emit('update:model', false)"
    size="max-w-md"
  >
    <div class="space-y-5">
      <div class="bg-blue-50 p-4 rounded-xl border border-blue-100 flex items-start space-x-3">
        <span class="text-xl">📢</span>
        <div>
          <p class="text-xs font-bold text-blue-800">配置说明</p>
          <p class="text-[10px] text-blue-600 mt-1 leading-relaxed">
            请前往钉钉群设置 -> 智能群助手 -> 添加机器人 -> 自定义 (Webhook)，获取对应的 Webhook 地址及加签密钥。
          </p>
        </div>
      </div>

      <div class="space-y-4">
        <div>
          <label class="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-1.5">Webhook URL</label>
          <textarea
            v-model="webhookUrl"
            :disabled="readonly"
            rows="3"
            placeholder="https://oapi.dingtalk.com/robot/send?access_token=..."
            class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-primary disabled:bg-gray-50 disabled:text-gray-500 font-mono"
          ></textarea>
        </div>

        <div>
          <label class="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-1.5">加签密钥 (Secret)</label>
          <input
            v-model="secret"
            :disabled="readonly"
            type="password"
            placeholder="可选：若开启了加签请填写"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-primary disabled:bg-gray-50 disabled:text-gray-500 font-mono"
          />
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
