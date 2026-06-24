import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useChatStore = defineStore('chat', () => {
  const conversations = ref([])
  const currentConversationId = ref(null)
  const messages = ref({})

  function createNewConversation() {
    const id = Date.now().toString()
    const conversation = {
      id,
      title: '新对话',
      createTime: new Date().toLocaleString()
    }
    conversations.value.unshift(conversation)
    messages.value[id] = []
    currentConversationId.value = id
    return id
  }

  function setCurrentConversation(id) {
    currentConversationId.value = id
  }

  function addMessage(conversationId, message) {
    if (!messages.value[conversationId]) {
      messages.value[conversationId] = []
    }
    messages.value[conversationId].push(message)
  }

  function updateConversationTitle(conversationId, title) {
    const conversation = conversations.value.find(c => c.id === conversationId)
    if (conversation) {
      conversation.title = title
    }
  }

  function deleteConversation(id) {
    const index = conversations.value.findIndex(c => c.id === id)
    if (index !== -1) {
      conversations.value.splice(index, 1)
      delete messages.value[id]
      if (currentConversationId.value === id) {
        currentConversationId.value = conversations.value[0]?.id || null
      }
    }
  }

  function getCurrentMessages() {
    return messages.value[currentConversationId.value] || []
  }

  return {
    conversations,
    currentConversationId,
    messages,
    createNewConversation,
    setCurrentConversation,
    addMessage,
    updateConversationTitle,
    deleteConversation,
    getCurrentMessages
  }
})