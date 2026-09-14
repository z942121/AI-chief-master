<template>
  <div class="chat-app">
    <!-- Header -->
    <header class="app-header">
      <div class="header-content">
        <div class="header-left">
          <div class="logo-icon">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2L14 6H10L12 2Z" fill="white" />
              <path d="M7 6H17L19 10H5L7 6Z" fill="white" />
              <path d="M5 10H19V14H5V10Z" fill="white" opacity="0.9" />
              <path d="M8 14H16L15 20H9L8 14Z" fill="white" opacity="0.8" />
            </svg>
          </div>
          <div class="header-text">
            <h1 class="app-title">AI 私人厨师</h1>
            <p class="app-subtitle">你的 AI 烹饪助手</p>
          </div>
        </div>
        <div class="header-right">
          <button class="text-btn new-chat-btn" @click="handleNewConversation" :disabled="isLoading">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 5V19M5 12H19" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
            </svg>
            <span>新对话</span>
          </button>
          <button class="icon-btn" @click="showHistory = !showHistory" title="历史会话">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 8V12L15 15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
              <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8" />
            </svg>
          </button>
        </div>
      </div>
    </header>

    <!-- Main Chat Area -->
    <main class="chat-container" ref="chatContainer">
      <!-- 欢迎页 -->
      <div v-if="messages.length === 0" class="welcome-section">
        <div class="welcome-hero">
          <div class="welcome-icon">🍳</div>
          <h2 class="welcome-title">AI 私人厨师</h2>
          <p class="welcome-desc">告诉我你有什么食材，我来帮你想今天吃什么。</p>
        </div>
        <div class="quick-prompts">
          <button
            v-for="prompt in quickPrompts"
            :key="prompt.text"
            class="prompt-card"
            @click="sendQuickPrompt(prompt)"
            :disabled="isLoading"
          >
            <span class="prompt-icon">{{ prompt.icon }}</span>
            <span class="prompt-text">{{ prompt.text }}</span>
          </button>
        </div>
      </div>

      <!-- 消息列表 -->
      <div v-else class="messages-list" ref="messagesList">
        <ChatMessage
          v-for="(message, index) in messages"
          :key="index"
          :message="message"
        />
        <div v-if="isLoading && !hasCurrentAiMessage" class="loading-indicator">
          <div class="loading-spinner"></div>
          <span>正在连接…</span>
        </div>
      </div>
    </main>

    <!-- 输入区域 -->
    <footer class="input-section">
      <div v-if="uploadedImageUrl" class="image-preview-bar">
        <div class="preview-item">
          <img :src="uploadedImageUrl" alt="食材图片" @click="openImagePreview(uploadedImageUrl)" />
          <button class="remove-btn" @click="removeImage" title="移除图片">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M18 6L6 18M6 6L18 18" stroke="white" stroke-width="2" stroke-linecap="round" />
            </svg>
          </button>
        </div>
      </div>

      <div class="input-bar">
        <button class="icon-btn upload-btn" @click="triggerFileInput" :disabled="isLoading" title="上传食材图片">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M21 15V19C21 19.5304 20.7893 20.0391 20.4142 20.4142C20.0391 20.7893 19.5304 21 19 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M17 8L12 3L7 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M12 3V15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
        <input ref="fileInput" type="file" accept="image/*" class="hidden-file-input" @change="handleFileSelect" />
        <textarea
          v-model="inputMessage"
          class="message-input"
          placeholder="告诉我你有什么食材，或者想吃什么…"
          @keydown="handleKeyDown"
          :disabled="isLoading"
          rows="1"
          ref="inputRef"
        ></textarea>
        <button class="send-btn" @click="handleSend" :disabled="!canSend || isLoading" title="发送">
          <svg v-if="!isLoading" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M22 2L11 13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M22 2L15 22L11 13L2 9L22 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <div v-else class="send-spinner"></div>
        </button>
      </div>
      <p class="input-hint">Enter 发送 · Shift + Enter 换行</p>
    </footer>

    <!-- 会话历史侧边栏 -->
    <div class="history-sidebar" :class="{ open: showHistory }">
      <div class="sidebar-overlay" @click="showHistory = false"></div>
      <div class="sidebar-content">
        <div class="sidebar-header">
          <h3>历史会话</h3>
          <button class="icon-btn close-btn" @click="showHistory = false">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
            </svg>
          </button>
        </div>
        <div class="sidebar-body">
          <SessionHistory @close="showHistory = false" @select="handleSelectSession" />
        </div>
      </div>
    </div>

    <!-- 图片预览弹窗 -->
    <div v-if="previewImageUrl" class="image-preview-modal" @click="closeImagePreview">
      <div class="modal-content" @click.stop>
        <button class="modal-close-btn" @click="closeImagePreview">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M18 6L6 18M6 6L18 18" stroke="white" stroke-width="2" stroke-linecap="round" />
          </svg>
        </button>
        <img :src="previewImageUrl" alt="预览图片" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import ChatMessage from './ChatMessage.vue'
import SessionHistory from './SessionHistory.vue'
import {
  sendMessageStream,
  uploadImage,
  getChatHistory,
  getThreadId,
  clearThreadId,
  generateThreadId,
  saveSession,
  updateSessionTitle
} from '@/utils/api'

const quickPrompts = [
  { icon: '🍅', text: '我有西红柿和鸡蛋' },
  { icon: '🥩', text: '冰箱里有牛肉和土豆' },
  { icon: '🥗', text: '帮我推荐一道低脂晚餐' },
  { icon: '⚡', text: '今天想吃简单一点的' },
]

const STAGES_DEFINITION = [
  { key: 'supervisor', label: '需求规划', status: 'pending', message: '' },
  { key: 'ingredient', label: '食材分析', status: 'pending', message: '' },
  { key: 'preference', label: '偏好分析', status: 'pending', message: '' },
  { key: 'recipe', label: '菜谱搜索', status: 'pending', message: '' },
  { key: 'nutrition', label: '营养分析', status: 'pending', message: '' },
  { key: 'critic', label: '最终审核', status: 'pending', message: '' },
  { key: 'final', label: '整理推荐', status: 'pending', message: '' },
]

const messages = ref([])
const inputMessage = ref('')
const isLoading = ref(false)
const uploadedImageUrl = ref('')
const fileInput = ref(null)
const inputRef = ref(null)
const messagesList = ref(null)
const chatContainer = ref(null)
const showHistory = ref(false)
const previewImageUrl = ref('')
const currentAiIndex = ref(-1)

const canSend = computed(() => {
  return inputMessage.value.trim().length > 0 || uploadedImageUrl.value
})

const hasCurrentAiMessage = computed(() => {
  return currentAiIndex.value >= 0 && currentAiIndex.value < messages.value.length
})

function formatTime() {
  const now = new Date()
  return now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesList.value) {
      messagesList.value.scrollTop = messagesList.value.scrollHeight
    } else if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}

function triggerFileInput() {
  fileInput.value?.click()
}

async function handleFileSelect(event) {
  const file = event.target.files?.[0]
  if (file) {
    await processFile(file)
  }
}

async function processFile(file) {
  try {
    const result = await uploadImage(file)
    if (result.data && result.data.file_url) {
      uploadedImageUrl.value = result.data.file_url
    }
  } catch (error) {
    console.error('上传失败:', error)
    alert('图片上传失败，请重试')
  }
}

function removeImage() {
  uploadedImageUrl.value = ''
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

function openImagePreview(url) {
  previewImageUrl.value = url
}

function closeImagePreview() {
  previewImageUrl.value = ''
}

function handleKeyDown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

function initThinkingStages() {
  return STAGES_DEFINITION.map(s => ({ ...s }))
}

function updateStage(stageKey, status, message) {
  if (currentAiIndex.value < 0) return
  const msg = messages.value[currentAiIndex.value]
  if (!msg || !msg.thinkingStages) return
  const stage = msg.thinkingStages.find(s => s.key === stageKey)
  if (stage) {
    stage.status = status
    stage.message = message
  }
}

function sendQuickPrompt(prompt) {
  inputMessage.value = prompt.text
  nextTick(() => {
    handleSend()
  })
}

async function handleSend() {
  if (!canSend.value || isLoading.value) return
  isLoading.value = true
  const userText = inputMessage.value.trim()
  const currentImageUrl = uploadedImageUrl.value

  messages.value.push({
    role: 'user',
    content: userText,
    imageUrl: currentImageUrl,
    time: formatTime()
  })

  inputMessage.value = ''
  uploadedImageUrl.value = ''
  if (fileInput.value) {
    fileInput.value.value = ''
  }

  currentAiIndex.value = messages.value.length
  messages.value.push({
    role: 'assistant',
    content: '',
    time: formatTime(),
    streaming: true,
    thinkingStages: initThinkingStages()
  })

  scrollToBottom()

  try {
    const threadId = getThreadId()
    await sendMessageStream(userText, currentImageUrl, threadId, {
      onStatus: (data) => {
        updateStage(data.stage, data.status, data.message)
      },
      onChunk: (content) => {
        if (currentAiIndex.value >= 0 && messages.value[currentAiIndex.value]) {
          const text = typeof content === 'string' ? content : String(content || '')
          messages.value[currentAiIndex.value].content += text
          scrollToBottom()
        }
      },
      onDone: () => {
        if (currentAiIndex.value >= 0 && messages.value[currentAiIndex.value]) {
          messages.value[currentAiIndex.value].streaming = false
        }
      },
      onError: (err) => {
        console.error('SSE 错误:', err)
        if (currentAiIndex.value >= 0 && messages.value[currentAiIndex.value]) {
          messages.value[currentAiIndex.value].streaming = false
          if (!messages.value[currentAiIndex.value].content) {
            messages.value[currentAiIndex.value].content = '抱歉，服务暂时不可用，请稍后重试。'
          }
        }
      }
    })
  } catch (error) {
    console.error('发送失败:', error)
    if (currentAiIndex.value >= 0 && messages.value[currentAiIndex.value]) {
      const msg = messages.value[currentAiIndex.value]
      if (error.message && error.message.includes('正在处理')) {
        messages.value.pop()
        currentAiIndex.value = -1
      } else if (!msg.content) {
        msg.content = '抱歉，服务暂时不可用，请稍后重试。'
        msg.streaming = false
      }
    }
  } finally {
    isLoading.value = false
    currentAiIndex.value = -1
    scrollToBottom()
  }
}

async function loadHistory() {
  try {
    const result = await getChatHistory()
    if (result.messages && result.messages.length > 0) {
      messages.value = result.messages.map(msg => ({
        role: msg.role,
        content: msg.content,
        imageUrl: msg.image_url || '',
        time: formatTime(),
        streaming: false,
        thinkingStages: null
      }))
    }
  } catch (error) {
    console.error('加载历史失败:', error)
  }
}

async function handleNewConversation() {
  const currentThreadId = getThreadId()
  if (messages.value.length > 0) {
    const firstUserMessage = messages.value.find(m => m.role === 'user')
    const title = firstUserMessage ? firstUserMessage.content.slice(0, 20) : '新对话'
    saveSession(currentThreadId, title)
  }
  clearThreadId()
  const newThreadId = generateThreadId()
  localStorage.setItem('cook_thread_id', newThreadId)
  messages.value = []
  uploadedImageUrl.value = ''
  currentAiIndex.value = -1
  showHistory.value = false
  if (fileInput.value) {
    fileInput.value.value = ''
  }
  nextTick(() => {
    inputRef.value?.focus()
  })
}

async function handleSelectSession(threadId) {
  localStorage.setItem('cook_thread_id', threadId)
  messages.value = []
  uploadedImageUrl.value = ''
  currentAiIndex.value = -1
  showHistory.value = false
  if (fileInput.value) {
    fileInput.value.value = ''
  }
  await loadHistory()
}

onMounted(() => {
  loadHistory()
})
</script>

<style scoped>
.chat-app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  max-width: 100%;
  margin: 0 auto;
  background: #faf6f0;
  position: relative;
}

/* ===== Header ===== */
.app-header {
  background: #ffffff;
  border-bottom: 1px solid #f0e8da;
  padding: 12px 20px;
  position: relative;
  z-index: 20;
  flex-shrink: 0;
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 860px;
  margin: 0 auto;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-icon {
  width: 38px;
  height: 38px;
  background: #c2703d;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.logo-icon svg {
  width: 20px;
  height: 20px;
}

.header-text {
  display: flex;
  flex-direction: column;
}

.app-title {
  font-size: 16px;
  font-weight: 600;
  color: #3d2e1f;
  margin: 0;
  line-height: 1.2;
}

.app-subtitle {
  font-size: 12px;
  color: #999;
  margin: 1px 0 0 0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.text-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 7px 12px;
  background: transparent;
  color: #555;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s ease;
}

.text-btn:hover:not(:disabled) {
  background: #f5ebe0;
  color: #3d2e1f;
}

.text-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.text-btn svg {
  width: 15px;
  height: 15px;
}

.icon-btn {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #888;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.icon-btn:hover:not(:disabled) {
  background: #f5ebe0;
  color: #3d2e1f;
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.icon-btn svg {
  width: 18px;
  height: 18px;
}

/* ===== Chat Container ===== */
.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px 16px;
}

/* ===== Welcome Section ===== */
.welcome-section {
  max-width: 580px;
  margin: 0 auto;
  padding: 48px 0 60px;
  text-align: center;
}

.welcome-hero {
  margin-bottom: 36px;
}

.welcome-icon {
  font-size: 44px;
  margin-bottom: 16px;
  line-height: 1;
}

.welcome-title {
  font-size: 26px;
  font-weight: 600;
  color: #3d2e1f;
  margin: 0 0 10px 0;
}

.welcome-desc {
  font-size: 14px;
  color: #888;
  margin: 0;
  line-height: 1.6;
}

.quick-prompts {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.prompt-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px 16px;
  background: #ffffff;
  border: 1px solid #f0e8da;
  border-radius: 10px;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s ease;
  font-family: inherit;
}

.prompt-card:hover:not(:disabled) {
  border-color: #d4a56c;
  background: #fdf8f0;
}

.prompt-card:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.prompt-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.prompt-text {
  font-size: 13px;
  color: #444;
  font-weight: 400;
}

/* ===== Messages List ===== */
.messages-list {
  max-width: 800px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding-bottom: 20px;
}

.loading-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0;
  color: #999;
  font-size: 13px;
}

.loading-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid #e5e5e0;
  border-top-color: #888;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ===== Input Section ===== */
.input-section {
  background: #ffffff;
  border-top: 1px solid #f0e8da;
  padding: 12px 16px;
  padding-bottom: calc(12px + env(safe-area-inset-bottom));
  flex-shrink: 0;
  position: relative;
  z-index: 20;
}

.image-preview-bar {
  max-width: 800px;
  margin: 0 auto 8px;
}

.preview-item {
  position: relative;
  display: inline-block;
}

.preview-item img {
  width: 56px;
  height: 56px;
  border-radius: 8px;
  object-fit: cover;
  border: 1px solid #e5e5e0;
  cursor: zoom-in;
}

.remove-btn {
  position: absolute;
  top: -5px;
  right: -5px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #c2703d;
  border: 2px solid white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0;
  z-index: 10;
}

.remove-btn:hover {
  transform: scale(1.1);
}

.remove-btn svg {
  width: 9px;
  height: 9px;
}

.input-bar {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  max-width: 800px;
  margin: 0 auto;
  background: #fdf8f0;
  border: 1px solid #e8d5b8;
  border-radius: 14px;
  padding: 6px 6px 6px 8px;
  transition: all 0.15s ease;
}

.input-bar:focus-within {
  border-color: #d4a56c;
  background: #fffdf7;
}

.upload-btn {
  width: 34px;
  height: 34px;
  align-self: center;
}

.upload-btn:hover:not(:disabled) {
  background: #f5ebe0;
}

.hidden-file-input {
  display: none;
}

.message-input {
  flex: 1;
  min-height: 22px;
  max-height: 120px;
  padding: 7px 4px;
  border: none;
  background: transparent;
  font-size: 14px;
  color: #3d2e1f;
  outline: none;
  resize: none;
  font-family: inherit;
  line-height: 1.5;
  align-self: center;
}

.message-input::placeholder {
  color: #aaa;
}

.message-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.send-btn {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: #c2703d;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s ease;
  align-self: center;
}

.send-btn:hover:not(:disabled) {
  background: #a85e30;
}

.send-btn:disabled {
  background: #e8d5b8;
  cursor: not-allowed;
}

.send-btn svg {
  width: 16px;
  height: 16px;
  margin-left: 1px;
}

.send-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.input-hint {
  text-align: center;
  font-size: 11px;
  color: #c0c0c0;
  margin: 6px 0 0 0;
}

/* ===== History Sidebar ===== */
.history-sidebar {
  position: fixed;
  top: 0;
  right: 0;
  width: 100%;
  height: 100%;
  z-index: 100;
  pointer-events: none;
}

.history-sidebar.open {
  pointer-events: auto;
}

.sidebar-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.3);
  opacity: 0;
  transition: opacity 0.3s ease;
}

.history-sidebar.open .sidebar-overlay {
  opacity: 1;
}

.sidebar-content {
  position: absolute;
  top: 0;
  right: 0;
  width: 300px;
  height: 100%;
  background: white;
  transform: translateX(100%);
  transition: transform 0.3s ease;
  display: flex;
  flex-direction: column;
  box-shadow: -4px 0 20px rgba(0, 0, 0, 0.08);
}

.history-sidebar.open .sidebar-content {
  transform: translateX(0);
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0ec;
}

.sidebar-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
}

.close-btn {
  width: 30px;
  height: 30px;
  border-radius: 8px;
}

.sidebar-body {
  flex: 1;
  overflow-y: auto;
}

/* ===== Image Preview Modal ===== */
.image-preview-modal {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease;
}

.modal-content {
  position: relative;
  max-width: 90%;
  max-height: 90%;
  animation: scaleIn 0.3s ease;
}

.modal-content img {
  max-width: 100%;
  max-height: 80vh;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  cursor: zoom-out;
}

.modal-close-btn {
  position: absolute;
  top: -40px;
  right: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0;
  transition: all 0.2s ease;
}

.modal-close-btn:hover {
  background: rgba(255, 255, 255, 0.3);
  transform: scale(1.1);
}

.modal-close-btn svg {
  width: 18px;
  height: 18px;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes scaleIn {
  from { opacity: 0; transform: scale(0.95); }
  to { opacity: 1; transform: scale(1); }
}

/* ===== PC Responsive ===== */
@media (min-width: 768px) {
  .app-header {
    padding: 14px 24px;
  }

  .header-content {
    max-width: 860px;
  }

  .logo-icon {
    width: 40px;
    height: 40px;
    border-radius: 11px;
  }

  .logo-icon svg {
    width: 22px;
    height: 22px;
  }

  .app-title {
    font-size: 17px;
    color: #3d2e1f;
  }

  .app-subtitle {
    font-size: 12.5px;
  }

  .chat-container {
    padding: 32px 24px;
  }

  .welcome-section {
    padding: 72px 0 80px;
  }

  .welcome-icon {
    font-size: 52px;
  }

  .welcome-title {
    font-size: 32px;
  }

  .welcome-desc {
    font-size: 15px;
  }

  .prompt-card {
    padding: 15px 18px;
  }

  .prompt-icon {
    font-size: 24px;
  }

  .prompt-text {
    font-size: 14px;
  }

  .messages-list {
    gap: 24px;
  }

  .input-section {
    padding: 14px 24px;
    padding-bottom: calc(14px + env(safe-area-inset-bottom));
  }

  .input-bar {
    border-radius: 16px;
    padding: 8px 8px 8px 10px;
  }

  .message-input {
    font-size: 15px;
  }

  .send-btn {
    width: 36px;
    height: 36px;
    border-radius: 10px;
  }

  .send-btn svg {
    width: 17px;
    height: 17px;
  }

  .sidebar-content {
    width: 320px;
  }
}

@media (min-width: 1200px) {
  .header-content {
    max-width: 860px;
  }

  .chat-container {
    padding: 40px 32px;
  }
}

/* ===== Mobile ===== */
@media (max-width: 480px) {
  .app-header {
    padding: 10px 14px;
  }

  .text-btn span {
    display: none;
  }

  .text-btn {
    width: 36px;
    height: 36px;
    padding: 0;
    justify-content: center;
  }

  .app-title {
    font-size: 15px;
  }

  .app-subtitle {
    font-size: 11px;
  }

  .logo-icon {
    width: 34px;
    height: 34px;
    border-radius: 9px;
  }

  .logo-icon svg {
    width: 18px;
    height: 18px;
  }

  .chat-container {
    padding: 16px 12px;
  }

  .welcome-section {
    padding: 36px 0 50px;
  }

  .welcome-icon {
    font-size: 36px;
  }

  .welcome-title {
    font-size: 22px;
  }

  .welcome-desc {
    font-size: 14px;
  }

  .prompt-card {
    padding: 11px 14px;
  }

  .prompt-icon {
    font-size: 18px;
  }

  .prompt-text {
    font-size: 12.5px;
  }

  .messages-list {
    gap: 16px;
  }

  .input-section {
    padding: 10px 12px;
    padding-bottom: calc(10px + env(safe-area-inset-bottom));
  }

  .input-hint {
    display: none;
  }

  .sidebar-content {
    width: 85%;
    max-width: 300px;
  }
}
</style>
