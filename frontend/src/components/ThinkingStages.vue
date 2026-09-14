<template>
  <div class="thinking-block" :class="{ 'is-done': isAllDone, 'is-collapsed': isCollapsed }">
    <!-- 折叠状态 -->
    <div v-if="isCollapsed" class="thinking-collapsed" @click="toggleCollapse">
      <svg class="check-icon" viewBox="0 0 24 24" fill="none">
        <path d="M5 13L9 17L19 7" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span class="collapsed-text">已深度思考</span>
      <span class="collapsed-sub">· 点击展开</span>
      <svg class="expand-icon" viewBox="0 0 24 24" fill="none">
        <path d="M9 18L15 12L9 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>

    <!-- 展开状态 -->
    <div v-else class="thinking-expanded">
      <div class="thinking-header" @click="toggleCollapse">
        <div class="header-left">
          <div v-if="!isAllDone" class="thinking-spinner"></div>
          <svg v-else class="check-icon" viewBox="0 0 24 24" fill="none">
            <path d="M5 13L9 17L19 7" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span class="header-text">{{ isAllDone ? '已深度思考' : '思考中' }}</span>
          <span v-if="!isAllDone" class="thinking-dots">
            <i></i><i></i><i></i>
          </span>
        </div>
        <span class="collapse-btn">收起</span>
      </div>

      <div class="stage-list" ref="listRef">
        <div
          v-for="stage in stages"
          :key="stage.key"
          class="stage-row"
          :class="stage.status"
        >
          <!-- 图标 -->
          <span v-if="stage.status === 'completed'" class="stage-icon icon-done">✓</span>
          <span v-else-if="stage.status === 'running'" class="stage-icon icon-running"></span>
          <span v-else class="stage-icon icon-pending"></span>

          <!-- 步骤名 -->
          <span class="stage-name">{{ stage.label }}</span>

          <!-- 状态描述 -->
          <span v-if="stage.status === 'running' && stage.message" class="stage-msg">
            {{ stage.message }}
          </span>
          <span v-else-if="stage.status === 'completed' && stage.message" class="stage-msg">
            {{ stage.message }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  stages: {
    type: Array,
    default: () => []
  },
  autoCollapse: {
    type: Boolean,
    default: true
  }
})

const isCollapsed = ref(false)
const listRef = ref(null)

const hasStarted = computed(() => props.stages.some(s => s.status !== 'pending'))

const isAllDone = computed(() =>
  props.stages.length > 0 &&
  props.stages.every(s => s.status === 'completed' || s.status === 'failed')
)

watch(isAllDone, (done) => {
  if (done && props.autoCollapse && hasStarted.value) {
    setTimeout(() => {
      isCollapsed.value = true
    }, 600)
  }
})

function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
}

defineExpose({ isCollapsed })
</script>

<style scoped>
.thinking-block {
  margin-bottom: 8px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.6;
}

/* ===== 折叠状态 ===== */
.thinking-collapsed {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  background: #f5ebe0;
  border-radius: 8px;
  cursor: pointer;
  user-select: none;
  color: #8b6f4a;
  font-size: 12.5px;
  transition: all 0.15s ease;
}

.thinking-collapsed:hover {
  background: #faf0e4;
  color: #6b5235;
}

.check-icon {
  width: 14px;
  height: 14px;
  color: #999;
  flex-shrink: 0;
}

.collapsed-text {
  font-weight: 500;
}

.collapsed-sub {
  color: #bbb;
}

.expand-icon {
  width: 14px;
  height: 14px;
  color: #ccc;
}

/* ===== 展开状态 ===== */
.thinking-expanded {
  background: #fdf8f0;
  border-radius: 10px;
  overflow: hidden;
}

.thinking-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.thinking-spinner {
  width: 14px;
  height: 14px;
  border: 1.5px solid #e0e0e0;
  border-top-color: #888;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.header-text {
  color: #888;
  font-size: 12.5px;
  font-weight: 500;
}

.thinking-dots {
  display: inline-flex;
  gap: 2px;
  margin-left: 1px;
}

.thinking-dots i {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: #aaa;
  animation: dotPulse 1.2s infinite ease-in-out;
}

.thinking-dots i:nth-child(2) { animation-delay: 0.2s; }
.thinking-dots i:nth-child(3) { animation-delay: 0.4s; }

@keyframes dotPulse {
  0%, 100% { opacity: 0.3; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1); }
}

.collapse-btn {
  color: #bbb;
  font-size: 11.5px;
  cursor: pointer;
}

.thinking-header .check-icon {
  color: #999;
}

/* ===== 步骤列表 ===== */
.stage-list {
  padding: 2px 12px 10px 14px;
}

.stage-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  transition: all 0.3s ease;
}

/* 图标 */
.stage-icon {
  width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.icon-done {
  color: #bbb;
  font-size: 12px;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.icon-running {
  width: 12px;
  height: 12px;
  border: 1.5px solid #e0e0e0;
  border-top-color: #888;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.icon-pending {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #ddd;
}

/* 步骤名 */
.stage-name {
  font-size: 12.5px;
  white-space: nowrap;
}

/* 状态描述 */
.stage-msg {
  font-size: 11.5px;
  color: #b0b0b0;
  margin-left: 2px;
}

/* ===== 各状态样式 ===== */
.stage-row.completed {
  color: #b0b0b0;
}

.stage-row.completed .stage-name {
  color: #b0b0b0;
}

.stage-row.running {
  color: #555;
}

.stage-row.running .stage-name {
  color: #555;
  font-weight: 500;
}

.stage-row.running .stage-msg {
  color: #999;
}

.stage-row.pending {
  color: #ccc;
}

.stage-row.pending .stage-name {
  color: #ccc;
}

.stage-row.pending .stage-msg {
  display: none;
}

.stage-row.failed .stage-name {
  color: #c2746d;
}

/* ===== 移动端 ===== */
@media (max-width: 480px) {
  .thinking-block {
    font-size: 12px;
  }
  .header-text {
    font-size: 12px;
  }
  .stage-name {
    font-size: 12px;
  }
  .stage-msg {
    font-size: 11px;
  }
}
</style>
