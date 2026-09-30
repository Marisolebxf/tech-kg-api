<script setup lang="ts">
import { Modal as AModal } from '@arco-design/web-vue'
withDefaults(defineProps<{
  visible: boolean
  title: string
  name: string
  identifier?: string
  identifierLabel?: string
  description: string
  loading?: boolean
  error?: string
}>(), { loading: false, error: '', identifier: '', identifierLabel: '标识' })
const emit = defineEmits<{ 'update:visible': [visible: boolean]; confirm: [] }>()
</script>

<template>
  <a-modal :visible="visible" :title="title" :width="480" modal-class="kg-delete-dialog"
    :mask-style="{ background: 'rgba(16,38,76,.42)', backdropFilter: 'blur(2px)' }"
    :mask-closable="!loading" :esc-to-close="!loading" :closable="!loading"
    @update:visible="value => !loading && emit('update:visible', value)">
    <div class="kg-delete-summary">
      <span class="kg-delete-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 3 2.8 19a1.4 1.4 0 0 0 1.2 2h16a1.4 1.4 0 0 0 1.2-2L12 3Zm0 6v5m0 3.5v.1" /></svg></span>
      <div><h3>确认删除“{{ name }}”吗？</h3><p><template v-if="identifier">{{ identifierLabel }}：<code>{{ identifier }}</code>。 </template>删除后无法恢复，请谨慎操作。</p></div>
    </div>
    <div class="kg-delete-impact"><p>{{ description }}</p></div>
    <p v-if="error" class="kg-delete-error" role="alert">{{ error }}</p>
    <template #footer>
      <button type="button" :disabled="loading" @click="emit('update:visible', false)">取消</button>
      <button type="button" class="danger" :disabled="loading" @click="emit('confirm')">{{ loading ? '删除中...' : '确认删除' }}</button>
    </template>
  </a-modal>
</template>

<style>
/* Schema 删除弹窗的尺寸、语义与内容层级；Modal 保留 Arco 的焦点和键盘管理。 */
.kg-delete-dialog{background:#fff!important;box-shadow:0 24px 70px rgba(28,58,107,.3);max-width:calc(100vw - 48px);border-radius:8px;font-family:"PingFang SC","PingFang HK","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;font-size:14px;line-height:22px;letter-spacing:0}
.kg-delete-dialog .arco-modal-header{box-sizing:border-box;height:56px;padding:0 24px}
.kg-delete-dialog .arco-modal-title{justify-content:flex-start;font-size:16px;line-height:24px;font-weight:600;text-align:left}
.kg-delete-dialog .arco-modal-body{box-sizing:border-box;max-height:60vh;overflow:auto;padding:24px;display:flex;flex-direction:column;gap:16px}
.kg-delete-summary{display:flex;align-items:flex-start;gap:12px;min-width:0}
.kg-delete-summary>div{min-width:0;overflow-wrap:anywhere}
.kg-delete-icon{display:grid;flex:0 0 auto;place-items:center;width:40px;height:40px;border-radius:50%;background:#fff1f0;color:#e5484d}
.kg-delete-icon svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.kg-delete-summary h3{margin:0;color:#1d2129;font-size:16px;line-height:24px;font-weight:600}
.kg-delete-summary p{margin:4px 0 0;color:#86909c;font-size:13px;line-height:20px}
.kg-delete-summary code{padding:1px 5px;border-radius:3px;background:#f2f3f5;color:#4e5969;font-family:inherit}
.kg-delete-impact{margin-left:52px;padding:12px 14px;border-radius:6px;background:#fff2f0;color:#b42318;overflow-wrap:anywhere}
.kg-delete-impact p{margin:0;font-size:12px;line-height:20px}
.kg-delete-error{margin:0;color:#b42318;font-size:14px;line-height:22px;overflow-wrap:anywhere}
.kg-delete-dialog .arco-modal-footer{box-sizing:border-box;min-height:64px;padding:16px 24px;display:flex;justify-content:flex-end;align-items:center;gap:16px;border-top:1px solid #e5e6eb}
.kg-delete-dialog .arco-modal-footer button{height:32px;padding:0 16px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#4e5969;font:inherit;cursor:pointer}
.kg-delete-dialog .arco-modal-footer button:hover:not(:disabled){background:#f7f8fa}
.kg-delete-dialog .arco-modal-footer .danger{border-color:#e5484d;background:#e5484d;color:#fff}
.kg-delete-dialog .arco-modal-footer .danger:hover:not(:disabled){border-color:#b42318;background:#b42318}
.kg-delete-dialog button:disabled{opacity:.6;cursor:not-allowed}
.kg-delete-dialog button:focus-visible{outline:2px solid #165dff;outline-offset:2px}
</style>
