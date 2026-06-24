import CryptoJS from 'crypto-js'

const AES_KEY = 'ThisIsASecretKey1234567890123456'

export function encrypt(text) {
  const key = CryptoJS.enc.Utf8.parse(AES_KEY)
  const encrypted = CryptoJS.AES.encrypt(text, key, {
    mode: CryptoJS.mode.ECB,
    padding: CryptoJS.pad.Pkcs7
  })
  return encrypted.toString()
}

export function decrypt(encryptedText) {
  const key = CryptoJS.enc.Utf8.parse(AES_KEY)
  const decrypted = CryptoJS.AES.decrypt(encryptedText, key, {
    mode: CryptoJS.mode.ECB,
    padding: CryptoJS.pad.Pkcs7
  })
  return decrypted.toString(CryptoJS.enc.Utf8)
}