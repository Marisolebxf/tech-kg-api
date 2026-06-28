import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    collapsed: false,
  }),
  actions: {
    toggleCollapsed() {
      this.collapsed = !this.collapsed
    },
  },
})
