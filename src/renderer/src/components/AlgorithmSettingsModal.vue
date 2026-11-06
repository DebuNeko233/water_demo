<script setup lang="ts">
import { computed, reactive } from 'vue'
import {
  ALGORITHM_GROUPS, DEFAULT_ALGORITHM_SETTINGS, copyAlgorithmSettings,
  validateAlgorithmSettings,
  type AlgorithmSettings,
} from '../utils/algorithm-settings.mjs'

const props = defineProps<{ settings: AlgorithmSettings }>()
const emit = defineEmits<{
  (event: 'cancel'): void
  (event: 'save', value: AlgorithmSettings): void
}>()
const draft = reactive<AlgorithmSettings>(copyAlgorithmSettings(props.settings))
const error = computed(() => validateAlgorithmSettings(draft))
// 暂时隐藏该分组的编辑控件，不删除设置项或改变 Python 检测器参数。
const visibleAlgorithmGroups = ALGORITHM_GROUPS.filter(group => group.title !== '图像与时序')

function defaults(): void {
  Object.assign(draft, DEFAULT_ALGORITHM_SETTINGS)
}
function save(): void {
  if (error.value) return
  emit('save', copyAlgorithmSettings(draft))
}
</script>

<template>
  <div class="algorithm-mask" @click.self="emit('cancel')">
    <section class="algorithm-dialog" role="dialog" aria-modal="true" aria-labelledby="algorithm-dialog-title">
      <header class="algorithm-dialog-head">
        <div>
          <h2 id="algorithm-dialog-title">算法参数设置</h2>
          <p>当前：单工位 ROI · Python 按原视频帧率逐帧检测</p>
        </div>
        <button type="button" class="modal-close" title="关闭设置" aria-label="关闭设置" @click="emit('cancel')">×</button>
      </header>
      <form class="algorithm-form" @submit.prevent="save">
        <div class="algorithm-scroll">
          <section v-for="group in visibleAlgorithmGroups" :key="group.title" class="algorithm-section">
            <div class="algorithm-section-title">
              <strong>{{ group.title }}</strong>
              <span>{{ group.hint }}</span>
            </div>
            <div class="algorithm-fields">
              <label v-for="field in group.fields" :key="field.key" class="algorithm-field">
                <span class="algorithm-field-label">{{ field.label }}</span>
                <span class="algorithm-field-input">
                  <input
                    v-model.number="draft[field.key]"
                    type="number"
                    :min="field.min"
                    :max="field.max"
                    :step="field.step"
                    :aria-label="field.label"
                    required
                  />
                  <small v-if="field.unit">{{ field.unit }}</small>
                </span>
              </label>
            </div>
          </section>
          <p class="algorithm-note">保存后立即以新参数重新初始化检测，历史曲线与 OK/NG 状态会重新预热。视频位置不会改变。</p>
        </div>
        <footer class="algorithm-dialog-foot">
          <button type="button" class="btn btn-muted" @click="defaults">恢复默认</button>
          <div class="algorithm-foot-right">
            <span v-if="error" class="algorithm-error" role="alert">{{ error }}</span>
            <button type="button" class="btn btn-muted" @click="emit('cancel')">取消</button>
            <button type="submit" class="btn btn-primary" :disabled="!!error">保存并应用</button>
          </div>
        </footer>
      </form>
    </section>
  </div>
</template>
