import { defineStore } from "pinia";
import { currentSessionVersion, invalidateSessionVersion } from "../auth/sessionVersion";

import {
  getCurrentProfile,
  getLoginUrl,
  logoutCurrentSession,
  refreshCurrentSession,
  type AuthProfile,
} from "../api/auth";

const profileLoads = new WeakMap<object, { version: number; promise: Promise<AuthProfile | null> }>();

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
    loggingOut: false,
    skipSilentLogin: false,
  }),
  getters: {
    isAuthenticated: (state) => state.profile !== null,
    displayName: (state) =>
      state.profile?.user.nickname ||
      state.profile?.user.username ||
      "未登录用户",
    primaryRole: (state) =>
      state.profile?.isAdmin
        ? "全局管理员"
        : state.profile?.roles[0]?.name || "普通用户",
    isAdmin: (state) => Boolean(state.profile?.isAdmin),
  },
  actions: {
    invalidate(): void {
      invalidateSessionVersion();
      profileLoads.delete(this);
      this.profile = null;
      this.initialized = true;
      this.loading = false;
    },
    async loadCurrentUser(force = false): Promise<AuthProfile | null> {
      if (this.loggingOut || this.skipSilentLogin) return null;
      if (this.initialized && !force) return this.profile;
      const version = currentSessionVersion();
      const pending = profileLoads.get(this);
      if (pending?.version === version) return pending.promise;
      this.loading = true;
      const promise = (async () => {
        try {
          const profile = await getCurrentProfile();
          if (version !== currentSessionVersion()) return null;
          this.profile = profile;
          return profile;
        } catch (error) {
          if (version !== currentSessionVersion()) return null;
          this.invalidate();
          if (!isUnauthorized(error)) throw error;
          return null;
        } finally {
          if (version === currentSessionVersion()) {
            this.loading = false;
            this.initialized = true;
          }
          if (profileLoads.get(this)?.version === version) profileLoads.delete(this);
        }
      })();
      profileLoads.set(this, { version, promise });
      return promise;
    },
    async startLogin(next = "/overview"): Promise<void> {
      const version = currentSessionVersion();
      const result = await getLoginUrl(next);
      if (version !== currentSessionVersion()) return;
      window.location.assign(result.url);
    },
    async refresh(): Promise<AuthProfile | null> {
      const version = currentSessionVersion();
      const profile = await refreshCurrentSession();
      if (version !== currentSessionVersion()) return null;
      this.profile = profile;
      this.initialized = true;
      return profile;
    },
    async logout(): Promise<void> {
      this.loggingOut = true;
      this.skipSilentLogin = true;
      this.invalidate();
      try {
        await logoutCurrentSession();
      } catch {
        // 会话已失效或网络请求失败时，也必须完成前端本地退出。
      } finally {
        this.invalidate();
        this.loggingOut = false;
      }
    },
  },
});
