import axios from 'axios'

export const http = axios.create({
  baseURL: '/api',
  timeout: 20_000,
})

http.interceptors.response.use((response) => response.data)
