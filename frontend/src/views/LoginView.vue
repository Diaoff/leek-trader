<template>
  <section class="auth-shell">
    <div class="auth-card">
      <PageHeader :title="pageTitle" subtitle="核心资产数据按当前登录用户隔离" />
      <ErrorAlert v-if="error" :message="error" />

      <form v-if="authMode === 'login'" class="auth-form" @submit.prevent="submitLogin">
        <label class="auth-field">
          <span>用户名</span>
          <input v-model="loginForm.username" required autocomplete="username" />
        </label>
        <label class="auth-field">
          <span>密码</span>
          <input v-model="loginForm.password" required type="password" autocomplete="current-password" />
        </label>
        <button class="primary-button" type="submit" :disabled="loading">{{ loading ? '登录中...' : '登录' }}</button>
      </form>

      <form v-else class="auth-form" @submit.prevent="submitRegister">
        <label class="auth-field">
          <span>用户名</span>
          <input v-model="registerForm.username" required autocomplete="username" />
        </label>
        <label class="auth-field">
          <span>邮箱</span>
          <input v-model="registerForm.email" required type="email" autocomplete="email" />
        </label>
        <label class="auth-field">
          <span>昵称</span>
          <input v-model="registerForm.full_name" autocomplete="name" />
        </label>
        <label class="auth-field">
          <span>密码</span>
          <input v-model="registerForm.password" required type="password" minlength="6" autocomplete="new-password" />
        </label>
        <button class="primary-button" type="submit" :disabled="loading">{{ loading ? '注册中...' : '注册并登录' }}</button>
      </form>

      <div class="auth-switch">
        <span>{{ switchHint }}</span>
        <button type="button" @click="switchMode">
          {{ switchAction }}
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import ErrorAlert from '../components/ErrorAlert.vue'
import PageHeader from '../components/PageHeader.vue'
import { login, register } from '../api/auth'
import { getApiErrorMessage } from '../utils/http'

const router = useRouter()
const loading = ref(false)
const error = ref('')
const authMode = ref<'login' | 'register'>('login')

const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', email: '', full_name: '', password: '' })

const pageTitle = computed(() => (authMode.value === 'login' ? '登录 Leek Trader' : '注册 Leek Trader'))
const switchHint = computed(() => (authMode.value === 'login' ? '还没有账号？' : '已有账号？'))
const switchAction = computed(() => (authMode.value === 'login' ? '创建新账号' : '返回登录'))

function switchMode() {
  error.value = ''
  authMode.value = authMode.value === 'login' ? 'register' : 'login'
}

async function persistToken(username: string, password: string) {
  const token = await login(username, password)
  localStorage.setItem('token', token.access_token)
  await router.push('/')
}

async function submitLogin() {
  loading.value = true
  error.value = ''
  try {
    await persistToken(loginForm.username, loginForm.password)
  } catch (err) {
    error.value = getApiErrorMessage(err, '登录失败')
  } finally {
    loading.value = false
  }
}

async function submitRegister() {
  loading.value = true
  error.value = ''
  try {
    await register(registerForm)
    await persistToken(registerForm.username, registerForm.password)
  } catch (err) {
    error.value = getApiErrorMessage(err, '注册失败')
  } finally {
    loading.value = false
  }
}
</script>
