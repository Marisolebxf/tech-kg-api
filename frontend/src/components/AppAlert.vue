<script setup lang="ts">
/**
 * Arco Design Alert 规范的四态提示（对齐 @arco-design/web-vue es/alert 的实现）：
 * info（信息/蓝）、success（成功/绿）、warning（警告/橙）、error（错误/红）。
 * 每种状态必带前置提示符（填充圆形图标）+ 同色系浅底、无描边；
 * 有标题时正文用次级文字色（Arco text-2），无标题时正文 text-1。
 * 类型色板取自 Arco 亮色 token：arcoblue/green/orange/red 的 1 号底、6 号图标。
 */
withDefaults(
  defineProps<{
    type?: 'info' | 'success' | 'warning' | 'error'
    title?: string
    closable?: boolean
  }>(),
  { type: 'info', title: '', closable: false },
)
const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <div :class="['app-alert', `app-alert--${type}`, { 'app-alert--with-title': title }]" role="alert">
    <span class="app-alert__icon" aria-hidden="true">
      <svg v-if="type === 'success'" viewBox="0 0 48 48">
        <circle cx="24" cy="24" r="20" fill="currentColor" />
        <path d="M21.2 31.6 13.6 24l3.1-3.1 4.5 4.5 10.1-10.1 3.1 3.1z" fill="#fff" />
      </svg>
      <svg v-else-if="type === 'warning'" viewBox="0 0 48 48">
        <circle cx="24" cy="24" r="20" fill="currentColor" />
        <rect x="21.8" y="13" width="4.4" height="15" rx="2.2" fill="#fff" />
        <circle cx="24" cy="34" r="2.8" fill="#fff" />
      </svg>
      <svg v-else-if="type === 'error'" viewBox="0 0 48 48">
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
    <div class="app-alert__body">
      <strong v-if="title" class="app-alert__title">{{ title }}</strong>
      <div class="app-alert__content"><slot /></div>
    </div>
    <button v-if="closable" class="app-alert__close" type="button" aria-label="关闭" @click="emit('close')">
      ×
    </button>
  </div>
</template>

<style scoped>
/* 布局与尺寸对齐 Arco Alert：icon 左置 margin-right 8px，最小高度 40px，
   padding 8px 15px，圆角 2px（radius-small），无边框（transparent）。 */
.app-alert {
  box-sizing: border-box;
  display: flex;
  align-items: flex-start;
  min-height: 40px;
  padding: 8px 15px;
  border: 1px solid transparent;
  border-radius: 2px;
  font-size: 14px;
  line-height: 22px;
}

.app-alert__icon {
  flex: 0 0 auto;
  margin-right: 8px;
}

.app-alert__icon svg {
  display: block;
  width: 16px;
  height: 16px;
  margin-top: 3px;
}

.app-alert--with-title .app-alert__icon svg {
  width: 18px;
  height: 18px;
  margin-top: 2px;
}

.app-alert__body {
  position: relative;
  flex: 1;
  min-width: 0;
}

.app-alert__title {
  display: block;
  margin: 0 0 4px;
  color: #1d2129;
  font-size: 14px;
  font-weight: 600;
  line-height: 22px;
}

.app-alert__content {
  color: #1d2129;
  word-break: break-word;
}

/* 有标题时正文降为次级文字色（Arco text-2） */
.app-alert--with-title .app-alert__content {
  color: #4e5969;
}

/* 四态色板：底色 = Arco *-1，提示符 = Arco *-6 */
.app-alert--info {
  background: #e8f3ff;
}

.app-alert--info .app-alert__icon {
  color: #165dff;
}

.app-alert--success {
  background: #e8ffea;
}

.app-alert--success .app-alert__icon {
  color: #00b42a;
}

.app-alert--warning {
  background: #fff7e8;
}

.app-alert--warning .app-alert__icon {
  color: #ff7d00;
}

.app-alert--error {
  background: #ffece8;
}

.app-alert--error .app-alert__icon {
  color: #f53f3f;
}

.app-alert__close {
  flex: 0 0 auto;
  margin-left: 8px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #4e5969;
  font-size: 14px;
  line-height: 22px;
  cursor: pointer;
}

.app-alert__close:hover {
  color: #1d2129;
}
</style>
