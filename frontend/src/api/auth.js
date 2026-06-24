import request from '@/utils/request'
import { encrypt } from '@/utils/encryption'

export function login(data) {
  return request({
    url: '/auth/login',
    method: 'post',
    data: {
      username: data.username,
      password: encrypt(data.password)
    }
  })
}

export function getUserInfo() {
  return request({
    url: '/user/info',
    method: 'get'
  })
}