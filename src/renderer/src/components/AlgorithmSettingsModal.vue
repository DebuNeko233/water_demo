<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  ALGORITHM_GROUPS, DEFAULT_ALGORITHM_SETTINGS, copyAlgorithmSettings,
  validateAlgorithmSettings,
  type AlgorithmSettings,
} from '../utils/algorithm-settings.mjs'
import {
  type VideoSourceSettings,
} from '../services/video-source'

type SettingsTab = 'parameters' | 'source' | 'device'
const props = defineProps<{
  settings: AlgorithmSettings
  source: VideoSourceSettings
  busy?: boolean
}>()
const emit = defineEmits<{
  (event: 'cancel'): void
  (event: 'save', value: AlgorithmSettings): void
  (event: 'saveSource', value: VideoSourceSettings): void
  (event: 'importProfile'): void
  (event: 'exportProfile'): void
}>()
const activeTab = ref<SettingsTab>('parameters')
const draft = reactive<AlgorithmSettings>(copyAlgorithmSettings(props.settings))
const sourceDraft = reactive<VideoSourceSettings>({ ...props.source })
const error = computed(() => validateAlgorithmSettings(draft))
const sourceError = computed(() => {
  if (sourceDraft.kind === 'file' && !sourceDraft.file_path) {
    return '请选择视频文件'
  }
  if (sourceDraft.kind === 'rtsp') {
    if (!/^rtsp:\/\/[^/\s]+/i.test(sourceDraft.rtsp_url)) return '请输入 RTSP 视频地址'
  }
  if (!Number.isInteger(sourceDraft.usb_index) ||
      sourceDraft.usb_index < 0 || sourceDraft.usb_index > 15) {
    return 'USB 设备编号须为 0～15 的整数'
  }
  return ''
})
// Keep the existing hidden-image settings policy.
const visibleAlgorithmGroups = ALGORITHM_GROUPS.filter(group => group.title !== '图像与时序')

watch(() => props.source, next => Object.assign(sourceDraft, next))
watch(() => props.settings, next => Object.assign(draft, copyAlgorithmSettings(next)))

function defaults(): void {
  Object.assign(draft, DEFAULT_ALGORITHM_SETTINGS)
}
async function browseVideo(): Promise<void> {
  const selected = await window.desktop.system.selectVideoFile()
  if (selected) sourceDraft.file_path = selected
}

function save(): void {
  if (error.value) return
  emit('save', copyAlgorithmSettings(draft))
}
function saveSource(): void {
  if (sourceError.value) return
  emit('saveSource', { ...sourceDraft })
}
</script>

<template>
  <div class="algorithm-mask" @click.self="emit('cancel')">
    <section class="algorithm-dialog" role="dialog" aria-modal="true" aria-labelledby="algorithm-dialog-title">
      <header class="algorithm-dialog-head">
        <div><h2 id="algorithm-dialog-title">系统设置</h2></div>
        <button type="button" class="modal-close" title="关闭设置" aria-label="关闭设置" @click="emit('cancel')">×</button>
      </header>
      <nav class="settings-tabs" role="tablist" aria-label="设置类别">
        <button type="button" role="tab" :aria-selected="activeTab === 'parameters'" :class="{ active: activeTab === 'parameters' }" @click="activeTab = 'parameters'">检测参数</button>
        <button type="button" role="tab" :aria-selected="activeTab === 'source'" :class="{ active: activeTab === 'source' }" @click="activeTab = 'source'">视频源</button>
        <button type="button" role="tab" :aria-selected="activeTab === 'device'" :class="{ active: activeTab === 'device' }" @click="activeTab = 'device'">设备配置</button>
      </nav>

      <form v-if="activeTab === 'parameters'" class="algorithm-form" @submit.prevent="save">
        <div class="algorithm-scroll">
          <section v-for="group in visibleAlgorithmGroups" :key="group.title" class="algorithm-section">
            <div class="algorithm-section-title"><strong>{{ group.title }}</strong></div>
            <div class="algorithm-fields">
              <label v-for="field in group.fields" :key="field.key" class="algorithm-field">
                <span class="algorithm-field-label">{{ field.label }}</span>
                <span class="algorithm-field-input">
                  <input v-model.number="draft[field.key]" type="number"
                    :min="field.min" :max="field.max" :step="field.step"
                    :aria-label="field.label" required />
                  <small v-if="field.unit">{{ field.unit }}</small>
                </span>
              </label>
            </div>
          </section>
        </div>
        <footer class="algorithm-dialog-foot">
          <button type="button" class="btn btn-muted" :disabled="busy" @click="defaults">恢复默认</button>
          <div class="algorithm-foot-right">
            <span v-if="error" class="algorithm-error" role="alert">{{ error }}</span>
            <button type="button" class="btn btn-muted" @click="emit('cancel')">取消</button>
            <button type="submit" class="btn btn-primary" :disabled="!!error || busy">保存并应用</button>
          </div>
        </footer>
      </form>

      <form v-else-if="activeTab === 'source'" class="algorithm-form" @submit.prevent="saveSource">
        <div class="algorithm-scroll">
          <div class="source-kind-options" role="group" aria-label="视频源类型">
            <label><input v-model="sourceDraft.kind" type="radio" value="file" /> 本地视频</label>
            <label><input v-model="sourceDraft.kind" type="radio" value="rtsp" /> RTSP 摄像头</label>
            <label><input v-model="sourceDraft.kind" type="radio" value="usb" /> USB 摄像头</label>
          </div>
          <div v-if="sourceDraft.kind === 'file'" class="source-field">
            <label for="source-file-path">视频路径</label>
            <div class="source-path-row">
              <input id="source-file-path" :value="sourceDraft.file_path" type="text"
                readonly placeholder="未选择视频" :title="sourceDraft.file_path" />
              <button type="button" class="btn btn-muted" :disabled="busy" @click="browseVideo">浏览…</button>
            </div>
          </div>
          <div v-else-if="sourceDraft.kind === 'rtsp'" class="source-field">
            <label for="source-rtsp-url">RTSP 地址</label>
            <input id="source-rtsp-url" v-model.trim="sourceDraft.rtsp_url" type="text" spellcheck="false"
              autocomplete="off" placeholder="rtsp://192.168.1.66:554/..." />

          </div>
          <div v-else-if="sourceDraft.kind === 'usb'" class="source-field">
            <label for="source-usb-index">USB 摄像头编号</label>
            <input id="source-usb-index" v-model.number="sourceDraft.usb_index" type="number" min="0" max="15" step="1" />

          </div>

        </div>
        <footer class="algorithm-dialog-foot">
          <span></span>
          <div class="algorithm-foot-right">
            <span v-if="sourceError" class="algorithm-error" role="alert">{{ sourceError }}</span>
            <button type="button" class="btn btn-muted" @click="emit('cancel')">取消</button>
            <button type="submit" class="btn btn-primary" :disabled="!!sourceError || busy">保存视频源</button>
          </div>
        </footer>
      </form>

      <div v-else class="algorithm-form">
        <div class="algorithm-scroll source-device-actions">

          <div class="source-device-buttons">
            <button type="button" class="btn btn-muted" :disabled="busy" @click="emit('exportProfile')">导出设备配置 ZIP</button>
            <button type="button" class="btn btn-muted" :disabled="busy" @click="emit('importProfile')">导入设备配置 ZIP</button>
          </div>
        </div>
        <footer class="algorithm-dialog-foot">
          <span></span>
          <button type="button" class="btn btn-primary" @click="emit('cancel')">关闭</button>
        </footer>
      </div>
    </section>
  </div>
</template>
