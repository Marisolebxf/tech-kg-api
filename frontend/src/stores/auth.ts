import { defineStore } from "pinia";

import {
  getCurrentProfile,
  getLoginUrl,
  logoutCurrentSession,
  refreshCurrentSession,
  type AuthProfile,
} from "../api/auth";

function isUnauthorized(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    (error as { response?: { status?: number } }).response?.status === 401
  );
}

export const useAuthStore = defineStore("auth", {
  state: () => ({
    profile: null as AuthProfile | null,
    initialized: false,
    loading: false,
  }),
  getters: {
    isAuthenticated: (state) => state.profile !== null,
    displayName: (state) =>
      state.profile?.user.nickname ||
      state.profile?.user.username ||
      "未登录用户",
    primaryRole: (state) => state.profile?.roles[0]?.name || "普通用户",
  },
  actions: {
    async loadCurrentUser(force = false): Promise<AuthProfile | null> {
      if (this.initialized && !force) return this.profile;
      this.loading = true;
      try {
        this.profile = await getCurrentProfile();
        return this.profile;
      } catch (error) {
        this.profile = null;
        if (!isUnauthorized(error)) throw error;
        return null;
      } finally {
        this.loading = false;
        this.initialized = true;
      }
    },
    async startLogin(next = "/overview"): Promise<void> {
      const result = await getLoginUrl(next);
      window.location.assign(result.url);
    },
    async refresh(): Promise<AuthProfile> {
      this.profile = await refreshCurrentSession();
      this.initialized = true;
      return this.profile;
    },
    async logout(): Promise<void> {
      try {
        await logoutCurrentSession();
      } finally {
        this.profile = null;
        this.initialized = true;
      }
    },
  },
});
