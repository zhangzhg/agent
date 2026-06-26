<template>
  <div class="layout-container">
    <div class="sidebar">
      <div class="sidebar-header">
        <el-button type="primary" class="new-chat-btn" @click="handleNewChat">
          <el-icon><Plus /></el-icon>
          新对话
        </el-button>
      </div>
      <div class="conversation-list">
        <div
          v-for="conv in chatStore.conversations"
          :key="conv.id"
          :class="['conversation-item', { active: chatStore.currentConversationId === conv.id }]"
          @click="handleSelectConversation(conv.id)"
        >
          <el-icon><ChatDotRound /></el-icon>
          <span class="conversation-title">{{ conv.title }}</span>
          <el-icon class="delete-icon" @click.stop="handleDeleteConversation(conv.id)">
            <Delete />
          </el-icon>
        </div>
        <div v-if="chatStore.conversations.length === 0" class="empty-tip">
          暂无对话记录
        </div>
      </div>
      <div class="sidebar-footer">
        <div class="user-info">
          <el-icon><User /></el-icon>
          <span>{{ userStore.username }}</span>
        </div>
        <el-button text @click="handleLogout">
          <el-icon><SwitchButton /></el-icon>
          退出登录
        </el-button>
      </div>
    </div>
    <div class="main-content">
      <router-view />
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useChatStore } from '@/stores/chat'

const router = useRouter()
const userStore = useUserStore()
const chatStore = useChatStore()

onMounted(async () => {
  await chatStore.loadConversations()
  if (chatStore.conversations.length === 0) {
    await chatStore.createNewConversation()
  }
})

const handleNewChat = async () => {
  await chatStore.createNewConversation()
}

const handleSelectConversation = (id) => {
  chatStore.setCurrentConversation(id)
}

const handleDeleteConversation = async (id) => {
  ElMessageBox.confirm('确定要删除这个对话吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    await chatStore.deleteConversationById(id)
    ElMessage.success('删除成功')
  }).catch(() => {})
}

const handleLogout = () => {
  ElMessageBox.confirm('确定要退出登录吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    userStore.logout()
    router.push('/login')
    ElMessage.success('退出成功')
  }).catch(() => {})
}
</script>

<style scoped lang="scss">
.layout-container {
  display: flex;
  width: 100%;
  height: 100vh;
}

.sidebar {
  width: 260px;
  background: #1a1a1a;
  display: flex;
  flex-direction: column;
  color: #fff;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid #333;
}

.new-chat-btn {
  width: 100%;
  height: 44px;
  font-size: 14px;
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.conversation-item {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  margin-bottom: 4px;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.2s;
  
  &:hover {
    background: #2a2a2a;
  }
  
  &.active {
    background: #2a2a2a;
  }
  
  .el-icon {
    margin-right: 10px;
    font-size: 18px;
  }
  
  .conversation-title {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 14px;
  }
  
  .delete-icon {
    opacity: 0;
    transition: opacity 0.2s;
    font-size: 16px;
    
    &:hover {
      color: #f56c6c;
    }
  }
  
  &:hover .delete-icon {
    opacity: 1;
  }
}

.empty-tip {
  text-align: center;
  color: #666;
  padding: 20px;
  font-size: 14px;
}

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid #333;
  
  .user-info {
    display: flex;
    align-items: center;
    margin-bottom: 12px;
    font-size: 14px;
    
    .el-icon {
      margin-right: 8px;
      font-size: 18px;
    }
  }
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
  overflow: hidden;
}
</style>