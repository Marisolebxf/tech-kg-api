import axios from 'axios'

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 20_000,
  withCredentials: true,
})

http.interceptors.response.use((response) => response.data)
