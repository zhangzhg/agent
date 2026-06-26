import { defineStore } from "pinia";
import { ref } from "vue";
import {
  getConversations,
  getConversation,
  createConversation,
  deleteConversation,
} from "@/api/chat";

export const useChatStore = defineStore("chat", () => {
  const conversations = ref([]);
  const currentConversationId = ref(null);
  const messages = ref({});
  const loading = ref(false);

  async function loadConversations() {
    try {
      loading.value = true;
      const response = await getConversations();
      conversations.value = response.data || [];
    } catch (error) {
      console.error("加载对话列表失败:", error);
    } finally {
      loading.value = false;
    }
  }

  async function loadConversationMessages(conversationId) {
    try {
      loading.value = true;
      const response = await getConversation(conversationId);
      if (response.data) {
        messages.value[conversationId] = response.data.messages || [];
      }
    } catch (error) {
      console.error("加载对话消息失败:", error);
    } finally {
      loading.value = false;
    }
  }

  async function createNewConversation() {
    try {
      const response = await createConversation("新对话");
      const conversationId = response.data;

      // ✅ 检查返回的会话 ID 是否已经存在于列表中
      const existingConversation = conversations.value.find(
        (c) => c.id === conversationId,
      );

      if (existingConversation) {
        // 如果已存在，直接切换到该会话，不创建新的会话对象
        currentConversationId.value = conversationId;

        // 如果该会话还没有加载消息，加载消息
        if (!messages.value[conversationId]) {
          messages.value[conversationId] = [];
        }

        console.log("切换到现有会话:", conversationId);
        return conversationId;
      } else {
        // 如果不存在，创建新的会话对象并添加到列表
        const conversation = {
          id: conversationId,
          title: "新对话",
          createTime: new Date().toLocaleString(),
        };
        conversations.value.unshift(conversation);
        messages.value[conversationId] = [];
        currentConversationId.value = conversationId;

        console.log("创建新会话:", conversationId);
        return conversationId;
      }
    } catch (error) {
      console.error("创建对话失败:", error);
      return null;
    }
  }

  function setCurrentConversation(id) {
    currentConversationId.value = id;
    if (id && !messages.value[id]) {
      loadConversationMessages(id);
    }
  }

  function addMessage(conversationId, message) {
    if (!messages.value[conversationId]) {
      messages.value[conversationId] = [];
    }
    messages.value[conversationId].push(message);
  }

  function updateConversationTitle(conversationId, title) {
    const conversation = conversations.value.find(
      (c) => c.id === conversationId,
    );
    if (conversation) {
      conversation.title = title;
    }
  }

  async function deleteConversationById(id) {
    try {
      await deleteConversation(id);
      const index = conversations.value.findIndex((c) => c.id === id);
      if (index !== -1) {
        conversations.value.splice(index, 1);
        delete messages.value[id];
        if (currentConversationId.value === id) {
          currentConversationId.value = conversations.value[0]?.id || null;
        }
      }
    } catch (error) {
      console.error("删除对话失败:", error);
    }
  }

  function getCurrentMessages() {
    return messages.value[currentConversationId.value] || [];
  }

  return {
    conversations,
    currentConversationId,
    messages,
    loading,
    loadConversations,
    loadConversationMessages,
    createNewConversation,
    setCurrentConversation,
    addMessage,
    updateConversationTitle,
    deleteConversationById,
    getCurrentMessages,
  };
});
