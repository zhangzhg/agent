<template>
  <div class="chat-container">
    <div class="chat-header">
      <h3>AI 智能助手</h3>
    </div>
    <div class="chat-messages" ref="messagesRef">
      <div
        v-for="(msg, index) in chatStore.getCurrentMessages()"
        :key="index"
        :class="['message', msg.role]"
      >
        <div class="message-avatar">
          <el-avatar :size="36" :icon="msg.role === 'user' ? 'User' : 'Monitor'" />
        </div>
        <div class="message-content">
          <div class="message-text">{{ msg.content }}</div>
        </div>
      </div>
      <div v-if="chatStore.getCurrentMessages().length === 0" class="welcome-message">
        <el-icon :size="60" color="#409eff"><Monitor /></el-icon>
        <h2>欢迎使用 AI 智能助手</h2>
        <p>我可以帮助您解答问题、提供建议、编写代码等</p>
      </div>
    </div>
    <div class="chat-input">
      <el-input
        v-model="inputMessage"
        type="textarea"
        :rows="3"
        placeholder="请输入您的问题..."
        @keydown.enter.ctrl="handleSend"
      />
      <div class="input-actions">
        <span class="tip">Ctrl + Enter 发送</span>
        <el-button type="primary" :loading="sending" @click="handleSend">
          发送
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch, onMounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import { streamChat } from '@/api/chat'

const chatStore = useChatStore()

const inputMessage = ref('')
const sending = ref(false)
const messagesRef = ref(null)

onMounted(async () => {
  await chatStore.loadConversations()
})

watch(() => chatStore.currentConversationId, () => {
  scrollToBottom()
})

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

const handleSend = async () => {
  if (!inputMessage.value.trim() || sending.value) return
  
  const message = inputMessage.value.trim()
  inputMessage.value = ''
  
  let conversationId = chatStore.currentConversationId
  
  if (!conversationId) {
    conversationId = await chatStore.createNewConversation()
    if (!conversationId) return
  }
  
  chatStore.addMessage(conversationId, {
    role: 'user',
    content: message,
    timestamp: new Date().toISOString()
  })
  
  if (chatStore.getCurrentMessages().length === 1) {
    chatStore.updateConversationTitle(
      conversationId,
      message.substring(0, 20) + (message.length > 20 ? '...' : '')
    )
  }
  
  scrollToBottom()
  
  sending.value = true
  
  const assistantMessage = {
    role: 'assistant',
    content: '',
    timestamp: new Date().toISOString()
  }
  chatStore.addMessage(conversationId, assistantMessage)
  
  const messageIndex = chatStore.getCurrentMessages().length - 1
  
  streamChat(
    conversationId,
    message,
    (chunk) => {
      chatStore.getCurrentMessages()[messageIndex].content += chunk
      scrollToBottom()
    },
    (newConversationId) => {
      if (!chatStore.currentConversationId) {
        chatStore.currentConversationId = newConversationId
      }
    },
    () => {
      sending.value = false
    },
    (error) => {
      console.error('Stream error:', error)
      sending.value = false
      chatStore.getCurrentMessages()[messageIndex].content = '抱歉，发生了错误，请重试。'
    }
  )
}
</script>

<style scoped lang="scss">
.chat-container {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.chat-header {
  padding: 16px 24px;
  background: white;
  border-bottom: 1px solid #e4e7ed;
  
  h3 {
    margin: 0;
    font-size: 18px;
    color: #303133;
  }
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  
  .message {
    display: flex;
    margin-bottom: 24px;
    
    &.user {
      flex-direction: row-reverse;
      
      .message-content {
        margin-right: 0;
        margin-left: 12px;
        
        .message-text {
          background: #409eff;
          color: white;
        }
      }
    }
    
    &.assistant {
      .message-content {
        .message-text {
          background: white;
          color: #303133;
        }
      }
    }
    
    .message-avatar {
      flex-shrink: 0;
    }
    
    .message-content {
      max-width: 70%;
      margin-right: 12px;
      
      .message-text {
        padding: 12px 16px;
        border-radius: 8px;
        line-height: 1.6;
        word-wrap: break-word;
      }
    }
  }
  
  .welcome-message {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #909399;
    
    h2 {
      margin: 20px 0 10px;
      color: #303133;
    }
    
    p {
      margin: 0;
    }
  }
}

.chat-input {
  padding: 16px 24px;
  background: white;
  border-top: 1px solid #e4e7ed;
  
  .input-actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 12px;
    
    .tip {
      font-size: 12px;
      color: #909399;
    }
  }
}
</style>