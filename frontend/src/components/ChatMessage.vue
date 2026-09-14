<template>
  <div class="message-item" :class="{ 'is-user': message.role === 'user' }">
    <div v-if="message.role === 'assistant'" class="avatar assistant-avatar">
      <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2L14 6H10L12 2Z" fill="white" />
        <path d="M7 6H17L19 10H5L7 6Z" fill="white" />
        <path d="M5 10H19V14H5V10Z" fill="white" opacity="0.9" />
        <path d="M8 14H16L15 20H9L8 14Z" fill="white" opacity="0.8" />
      </svg>
    </div>

    <div class="message-bubble-wrapper">
      <ThinkingStages
        v-if="message.role === 'assistant' && message.thinkingStages && message.thinkingStages.length > 0"
        :stages="message.thinkingStages"
        :auto-collapse="!message.streaming"
      />

      <div class="message-bubble" :class="{ 'user-bubble': message.role === 'user' }">
        <div v-if="message.imageUrl" class="message-image">
          <img :src="message.imageUrl" alt="上传的图片" @click="openImagePreview(message.imageUrl)" />
        </div>
        <div v-if="message.content || message.role === 'user'" class="message-text">
          <MarkdownRender v-if="message.role === 'assistant'" :content="formattedContent" :streaming="message.streaming" />
          <span v-else>{{ message.content }}</span>
        </div>
        <div v-else-if="message.role === 'assistant' && message.streaming" class="message-placeholder">
          <div class="placeholder-dots">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="message.role === 'user'" class="avatar user-avatar">
      <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 12C14.2091 12 16 10.2091 16 8C16 5.79086 14.2091 4 12 4C9.79086 4 8 5.79086 8 8C8 10.2091 9.79086 12 12 12Z" fill="white" />
        <path d="M12 14C9.79086 14 4 15.7909 4 18V20H20V18C20 15.7909 14.2091 14 12 14Z" fill="white" />
      </svg>
    </div>

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
import { computed, ref } from 'vue'
import { MarkdownRender } from '@ashlesss/markstream-vue'
import '@ashlesss/markstream-vue/index.css'
import ThinkingStages from './ThinkingStages.vue'

const previewImageUrl = ref('')

function openImagePreview(url) {
  previewImageUrl.value = url
}

function closeImagePreview() {
  previewImageUrl.value = ''
}

const props = defineProps({
  message: {
    type: Object,
    required: true
  }
})

const formattedContent = computed(() => {
  return props.message.content || ''
})
</script>

<style scoped>
.message-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.message-item.is-user {
  flex-direction: row;
  justify-content: flex-end;
}

/* ===== Avatar ===== */
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.assistant-avatar {
  background: #c2703d;
}

.user-avatar {
  background: #d4a56c;
}

.avatar svg {
  width: 20px;
  height: 20px;
}

/* ===== Message Bubble ===== */
.message-bubble-wrapper {
  max-width: 78%;
  display: flex;
  flex-direction: column;
}

.message-item.is-user .message-bubble-wrapper {
  align-items: flex-end;
  max-width: 75%;
}

.message-bubble {
  padding: 12px 16px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
}

/* AI 气泡 — 奶油白 */
.message-bubble:not(.user-bubble) {
  background: #ffffff;
  color: #3d2e1f;
  border: 1px solid #f0e8da;
}

/* 用户气泡 — 暖陶土色 */
.user-bubble {
  background: #c2703d;
  color: #ffffff;
}

.message-image {
  margin-bottom: 8px;
  border-radius: 8px;
  overflow: hidden;
}

.message-image img {
  max-width: 200px;
  width: 100%;
  height: auto;
  border-radius: 8px;
  display: block;
  cursor: zoom-in;
  transition: transform 0.2s ease;
}

.message-image img:hover {
  transform: scale(1.02);
}

.message-text {
  font-size: 14px;
  line-height: 1.7;
}

.message-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px 0;
}

.placeholder-dots {
  display: flex;
  gap: 4px;
}

.placeholder-dots span {
  width: 5px;
  height: 5px;
  background: #ccc;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}

.placeholder-dots span:nth-child(1) { animation-delay: -0.32s; }
.placeholder-dots span:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* ===== Markdown 样式覆盖 ===== */
.message-text :deep(p) {
  margin: 0 0 10px 0;
}

.message-text :deep(p:last-child) {
  margin-bottom: 0;
}

.message-text :deep(strong) {
  font-weight: 600;
  color: #2d2014;
}

.message-text :deep(h1),
.message-text :deep(h2),
.message-text :deep(h3),
.message-text :deep(h4) {
  font-weight: 600;
  margin: 16px 0 8px 0;
  line-height: 1.35;
  color: #2d2014;
}

.message-text :deep(h1) { font-size: 1.4em; }
.message-text :deep(h2) { font-size: 1.2em; }
.message-text :deep(h3) { font-size: 1.1em; }

.message-text :deep(ul),
.message-text :deep(ol) {
  margin: 8px 0;
  padding-left: 22px;
}

.message-text :deep(li) {
  margin: 3px 0;
}

.message-text :deep(blockquote) {
  border-left: 3px solid #d4a56c;
  padding: 6px 14px;
  margin: 8px 0;
  background: #faf0e4;
  border-radius: 0 6px 6px 0;
  color: #7a5c3a;
}

.message-text :deep(code) {
  background: #f5ebe0;
  padding: 2px 5px;
  border-radius: 4px;
  font-size: 0.88em;
  font-family: 'Consolas', 'Monaco', monospace;
  color: #b8651c;
}

.message-text :deep(pre) {
  background: #2d2014;
  color: #f5ebe0;
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 8px 0;
  font-size: 13px;
}

.message-text :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
}

.message-text :deep(a) {
  color: #c7500f;
  text-decoration: none;
  border-bottom: 1px solid #e8c4a0;
}

.message-text :deep(a:hover) {
  border-bottom-color: #c7500f;
}

.message-text :deep(hr) {
  border: none;
  border-top: 1px solid #e5e5e0;
  margin: 12px 0;
}

.message-text :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 13px;
}

.message-text :deep(th) {
  background: #faf0e4;
  padding: 8px 12px;
  text-align: left;
  font-weight: 600;
  border-bottom: 2px solid #e8d5b8;
  color: #8b5a1f;
}

.message-text :deep(td) {
  padding: 7px 12px;
  border-bottom: 1px solid #f0e8da;
}

/* ===== 图片预览弹窗 ===== */
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

/* ===== PC 端 ===== */
@media (min-width: 768px) {
  .message-item {
    gap: 12px;
  }
  .avatar {
    width: 38px;
    height: 38px;
  }
  .avatar svg {
    width: 21px;
    height: 21px;
  }
  .message-bubble-wrapper {
    max-width: 80%;
  }
  .message-item.is-user .message-bubble-wrapper {
    max-width: 78%;
  }
  .message-bubble {
    padding: 14px 18px;
    border-radius: 16px;
    font-size: 15px;
  }
  .message-text {
    font-size: 15px;
    line-height: 1.75;
  }
  .message-image img {
    max-width: 260px;
  }
}

@media (min-width: 1200px) {
  .message-item {
    gap: 14px;
  }
  .avatar {
    width: 40px;
    height: 40px;
  }
  .avatar svg {
    width: 22px;
    height: 22px;
  }
  .message-bubble-wrapper {
    max-width: 82%;
  }
  .message-item.is-user .message-bubble-wrapper {
    max-width: 80%;
  }
  .message-bubble {
    padding: 15px 20px;
  }
  .message-image img {
    max-width: 300px;
  }
}
</style>
