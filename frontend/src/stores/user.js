import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const username = ref(localStorage.getItem('username') || '')
  const userId = ref(localStorage.getItem('userId') || '')

  function setToken(newToken) {
    token.value = newToken
    localStorage.setItem('token', newToken)
  }

  function setUsername(newUsername) {
    username.value = newUsername
    localStorage.setItem('username', newUsername)
  }

  function setUserId(newUserId) {
    userId.value = newUserId
    localStorage.setItem('userId', newUserId)
  }

  function logout() {
    token.value = ''
    username.value = ''
    userId.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    localStorage.removeItem('userId')
  }

  return {
    token,
    username,
    userId,
    setToken,
    setUsername,
    setUserId,
    logout
  }
})