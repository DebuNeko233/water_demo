<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  configured: boolean
  busy: boolean
  error: string
}>()
const emit = defineEmits<{
  (event: 'cancel'): void
  (event: 'submit', password: string): void
}>()
const password = ref('')
const confirmation = ref('')
const mismatch = computed(() =>
  !props.configured && confirmation.value.length > 0 &&
  confirmation.value !== password.value,
)
const valid = computed(() =>
  password.value.length >= 8 &&
  (props.configured || password.value === confirmation.value),
)
function submit(): void {
  if (valid.value && !props.busy) emit('submit', password.value)
}
</script>

<template>
  <div class="algorithm-mask" @click.self="emit('cancel')">
    <section class="role-dialog" role="dialog" aria-modal="true" aria-labelledby="role-dialog-title">
      <header class="role-dialog-header">
        <h2 id="role-dialog-title">{{ configured ? '管理员登录' : '设置管理员密码' }}</h2>
        <button type="button" class="modal-close" aria-label="关闭" @click="emit('cancel')">×</button>
      </header>
      <form class="role-form" @submit.prevent="submit">
        <label class="role-input-label">
          <span>管理员密码</span>
          <input v-model="password" type="password" :autocomplete="configured ? 'current-password' : 'new-password'" minlength="8" maxlength="128" required autofocus />
        </label>
        <label v-if="!configured" class="role-input-label">
          <span>确认密码</span>
          <input v-model="confirmation" type="password" autocomplete="new-password" minlength="8" maxlength="128" required />
        </label>
        <p v-if="!configured" class="role-password-note">首次使用请设置至少 8 位密码</p>
        <p v-if="mismatch" class="role-error" role="alert">两次输入的密码不一致</p>
        <p v-if="error" class="role-error" role="alert">{{ error }}</p>
        <footer class="role-dialog-actions">
          <button type="button" class="btn btn-muted" @click="emit('cancel')">取消</button>
          <button type="submit" class="btn btn-primary" :disabled="!valid || busy">
            {{ busy ? '请稍候…' : configured ? '切换到管理员' : '创建并切换' }}
          </button>
        </footer>
      </form>
    </section>
  </div>
</template>
