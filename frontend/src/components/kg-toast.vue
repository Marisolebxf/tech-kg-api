<script setup lang="ts">
import { useToast } from '../composables/use-toast'

const { toasts, dismissToast } = useToast()
</script>

<template>
  <div class="kg-toast-stack" aria-live="polite">
    <article
      v-for="item in toasts"
      :key="item.id"
      :class="['kg-toast', `kg-toast--${item.tone}`]"
    >
      <!-- 提示符：与 AppAlert 同一套 Arco 四态填充圆形图标 -->
      <span class="kg-toast__icon" aria-hidden="true">
        <svg v-if="item.tone === 'success'" viewBox="0 0 48 48">
          <circle cx="24" cy="24" r="20" fill="currentColor" />
          <path d="M21.2 31.6 13.6 24l3.1-3.1 4.5 4.5 10.1-10.1 3.1 3.1z" fill="#fff" />
        </svg>
        <svg v-else-if="item.tone === 'warning'" viewBox="0 0 48 48">
          <circle cx="24" cy="24" r="20" fill="currentColor" />
          <rect x="21.8" y="13" width="4.4" height="15" rx="2.2" fill="#fff" />
          <circle cx="24" cy="34" r="2.8" fill="#fff" />
        </svg>
        <svg v-else-if="item.tone === 'error'" viewBox="0 0 48 48">
          <circle cx="24" cy="24" r="20" fill="currentColor" />
          <path
            d="m24 20.7-5.1-5.1-2.8 2.8 5.1 5.1-5.1 5.1 2.8 2.8 5.1-5.1 5.1 5.1 2.8-2.8-5.1-5.1 5.1-5.1-2.8-2.8z"
            fill="#fff"
          />
        </svg>
        <svg v-else viewBox="0 0 48 48">
          <circle cx="24" cy="24" r="20" fill="currentColor" />
          <rect x="21.8" y="20" width="4.4" height="14" rx="2.2" fill="#fff" />
          <circle cx="24" cy="14.8" r="2.8" fill="#fff" />
        </svg>
      </span>
      <span>{{ item.message }}</span>
      <button type="button" aria-label="关闭" @click="dismissToast(item.id)">×</button>
    </article>
  </div>
</template>

<style scoped>
.kg-toast-stack {
  /* 提示顶部居中展示（业界惯例，同 Ant Design / Element Message）：多条向下堆叠 */
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10000;
  display: grid;
  gap: 10px;
  width: min(360px, calc(100vw - 32px));
  pointer-events: none;
}

.kg-toast {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid rgba(22, 93, 255, 0.18);
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.98);
  box-shadow: var(--shadow-card);
  color: var(--text-primary);
  font-size: 13px;
  line-height: 20px;
  pointer-events: auto;
}

/* 提示符与四态描边（Arco 亮色 token：*-6 图标色） */
.kg-toast__icon {
  flex: 0 0 auto;
  display: inline-flex;
}

.kg-toast__icon svg {
  display: block;
  width: 16px;
  height: 16px;
}

.kg-toast > span:not(.kg-toast__icon) {
  flex: 1 1 auto;
  min-width: 0;
}

.kg-toast--success {
  border-color: rgba(0, 180, 42, 0.24);
}

.kg-toast--success .kg-toast__icon {
  color: #00b42a;
}

.kg-toast--info .kg-toast__icon {
  color: #165dff;
}

.kg-toast--warning {
  border-color: rgba(255, 125, 0, 0.24);
}

.kg-toast--warning .kg-toast__icon {
  color: #ff7d00;
}

.kg-toast--error {
  border-color: rgba(245, 63, 63, 0.24);
}

.kg-toast--error .kg-toast__icon {
  color: #f53f3f;
}

.kg-toast button {
  flex: 0 0 auto;
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}

.kg-toast button:hover {
  background: var(--surface-subtle);
  color: var(--text-primary);
}
</style>

<style>
/* 平台布局（AppLayout）下，提示应在去掉左侧「目录」后的内容区水平居中。
   KgToast 挂在 #app 下、与 .app-shell 平级（门户嵌入页/登录页没有 shell），
   无法用后代选择器感知目录，改用 body:has() 按目录实际占位偏移：
   内容区中心 = 50vw + 目录宽 / 2。≤767px 时目录为浮层抽屉、内容占满全屏
   （与 AppLayout isMobile 断口一致），连同无 shell 的页面一起保持整屏居中；
   不支持 :has() 的旧浏览器同样退回整屏居中。 */
@media (min-width: 768px) {
  body:has(.app-shell:not(.is-collapsed)) .kg-toast-stack {
    left: calc(50% + var(--sidebar-width) / 2);
    width: min(360px, calc(100vw - var(--sidebar-width) - 32px));
  }

  body:has(.app-shell.is-collapsed) .kg-toast-stack {
    left: calc(50% + var(--sidebar-width-collapsed) / 2);
    width: min(360px, calc(100vw - var(--sidebar-width-collapsed) - 32px));
  }
}
</style>
