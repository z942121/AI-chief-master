import axios from 'axios'
import { fetchEventSource } from '@microsoft/fetch-event-source'

const BASE_URL = '/api/v1'

const activeRequests = new Set()

const axiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30000
})

export function generateThreadId() {
  return 'thread_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9)
}

export function getThreadId() {
  let threadId = localStorage.getItem('cook_thread_id')
  if (!threadId) {
    threadId = generateThreadId()
    localStorage.setItem('cook_thread_id', threadId)
  }
  return threadId
}

export function clearThreadId() {
  localStorage.removeItem('cook_thread_id')
}

export async function uploadImage(file) {
  const formData = new FormData()
  formData.append('file', file)

  const response = await axiosInstance.post('/oss/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
  return response.data
}

/**
 * 流式发送消息
 * @param {string} message - 用户消息
 * @param {string} imageUrl - 图片URL
 * @param {string} threadId - 会话ID
 * @param {object} callbacks - 回调函数
 *   - onStatus(status): { stage, status, message }  Agent 工作状态
 *   - onChunk(chunk): { content }  Markdown 流式内容
 *   - onDone():  完成
 *   - onError(err):  错误
 */
export function sendMessageStream(message, imageUrl = '', threadId = '', callbacks = {}) {
  const id = threadId || getThreadId()

  if (activeRequests.has(id)) {
    return Promise.reject(new Error('正在处理上一条消息，请稍候...'))
  }

  activeRequests.add(id)
  const controller = new AbortController()

  return new Promise((resolve, reject) => {
    let fullResponse = ''
    let isCompleted = false

    fetchEventSource(`${BASE_URL}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        message,
        image_url: imageUrl,
        thread_id: id
      }),
      signal: controller.signal,
      onopen(response) {
        if (response.status !== 200) {
          isCompleted = true
          controller.abort()
          reject(new Error(`连接失败: ${response.status}`))
        }
      },
      onmessage(event) {
        if (!event.data) return

        try {
          const data = JSON.parse(event.data)
          const eventType = event.event || 'message'

          if (eventType === 'status') {
            // Agent 工作状态事件
            if (callbacks.onStatus) {
              callbacks.onStatus(data)
            }
          } else if (eventType === 'chunk') {
            // Markdown 流式内容 — 确保 content 是字符串
            let content = data.content
            if (typeof content !== 'string') {
              content = content != null ? String(content) : ''
            }
            fullResponse += content
            if (callbacks.onChunk) {
              callbacks.onChunk(content)
            }
          } else if (eventType === 'done') {
            // 完成事件
            if (callbacks.onDone) {
              callbacks.onDone(data)
            }
          } else if (eventType === 'error') {
            // 错误事件
            if (callbacks.onError) {
              callbacks.onError(new Error(data.message || '服务异常'))
            }
          }
        } catch (error) {
          console.error('SSE 数据解析失败:', event.data, error)
        }
      },
      onclose() {
        activeRequests.delete(id)
        if (!isCompleted) {
          isCompleted = true
          resolve(fullResponse)
        }
      },
      onerror(err) {
        activeRequests.delete(id)
        if (!isCompleted) {
          isCompleted = true
          controller.abort()
          if (callbacks.onError) {
            callbacks.onError(err)
          }
          reject(err)
        }
      },
      fetch: (url, options) => {
        return fetch(url, options)
      },
      retry: 0
    })
  })
}

export async function getChatHistory(threadId = '') {
  const id = threadId || getThreadId()
  const response = await axiosInstance.get(`/chat/messages?thread_id=${id}`)
  return response.data
}

export async function healthCheck() {
  const response = await axios.get('/health')
  return response.data
}

// ========== 会话历史管理（后端存储）==========

// 获取所有会话列表
export async function getAllSessions() {
  const response = await axiosInstance.get('/chat/sessions')
  return response.data.sessions || []
}

// 保存会话到历史列表
export async function saveSession(threadId, title = '新对话') {
  const response = await axiosInstance.post(`/chat/sessions?thread_id=${threadId}&title=${encodeURIComponent(title)}`)
  return response.data.session
}

// 更新会话标题
export async function updateSessionTitle(threadId, title) {
  const response = await axiosInstance.put(`/chat/sessions/${threadId}?title=${encodeURIComponent(title)}`)
  return response.data.session
}

// 删除会话
export async function deleteSession(threadId) {
  const response = await axiosInstance.delete(`/chat/sessions/${threadId}`)
  return response.data.success
}
