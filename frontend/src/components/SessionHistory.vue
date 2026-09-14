<template>
  <div class="session-history-content">
    <div v-if="sessions.length === 0" class="empty-state">
      <p class="empty-text">暂无会话历史</p>
    </div>

    <div v-else class="sessions-list">
      <div
        v-for="session in sessions"
        :key="session.thread_id"
        class="session-item"
        @click="handleSelectSession(session.thread_id)"
      >
        <div class="session-info">
          <div class="session-title">{{ session.title }}</div>
          <div class="session-time">{{ formatTime(session.updated_at) }}</div>
        </div>
        <button class="delete-btn" @click.stop="handleDeleteSession(session.thread_id)" :disabled="deleting" title="删除">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M3 6H21M19 6L18 20H6L5 6M10 11V17M14 11V17" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getAllSessions, deleteSession } from '@/utils/api'

const emit = defineEmits(['close', 'select'])

const sessions = ref([])
const deleting = ref(false)

onMounted(() => {
  loadSessions()
})

async function loadSessions() {
  sessions.value = await getAllSessions()
}

function formatTime(timestamp) {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now - date

  if (diff < 24 * 60 * 60 * 1000) {
    return '今天 ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }

  if (diff < 7 * 24 * 60 * 60 * 1000) {
    const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
    return weekdays[date.getDay()] + ' ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }

  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

async function handleDeleteSession(threadId) {
  if (!confirm('确定要删除这个会话吗？')) {
    return
  }
  deleting.value = true
  try {
    await deleteSession(threadId)
    await loadSessions()
  } catch (error) {
    console.error('删除失败:', error)
    alert('删除失败，请重试')
  } finally {
    deleting.value = false
  }
}

function handleSelectSession(threadId) {
  emit('select', threadId)
  emit('close')
}
</script>

<style scoped>
.session-history-content {
  padding: 8px 4px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 20px;
}

.empty-text {
  font-size: 13px;
  color: #999;
  margin: 0;
}

.sessions-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.session-item:hover {
  background: #f7f6f3;
}

.session-info {
  flex: 1;
  min-width: 0;
}

.session-title {
  font-size: 13.5px;
  font-weight: 400;
  color: #333;
  margin-bottom: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-time {
  font-size: 11.5px;
  color: #aaa;
}

.delete-btn {
  width: 30px;
  height: 30px;
  border-radius: 6px;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
  margin-left: 8px;
  color: #ccc;
}

.delete-btn:hover:not(:disabled) {
  background: #f0f0ec;
  color: #c7500f;
}

.delete-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.delete-btn svg {
  width: 15px;
  height: 15px;
}
</style>
