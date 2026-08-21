<script setup lang="ts">
import { computed, ref } from 'vue'

type ConfigStatus = '正常' | '停用' | '异常'
type ConfigItem = {
  id: string
  category: string
  name: string
  description: string
  type: string
  endpoint: string
  owner: string
  updatedAt: string
  status: ConfigStatus
  usage: string
  secret?: boolean
}

const categories = [
  // { key: '数据源', label: '数据源连接', icon: 'DB', count: 6 },
  { key: '模型服务', label: '模型与抽取服务', icon: 'AI', count: 4 },
  // { key: 'Schema', label: 'Schema 与字典', icon: 'SC', count: 5 },
  { key: '调度', label: '调度与运行策略', icon: 'CR', count: 3 },
]

const items = ref<ConfigItem[]>([
  { id: 'DS-MYSQL-01', category: '数据源', name: '科技企业主库', description: '企业工商、产品与产业链数据', type: 'MySQL 8.0', endpoint: 'mysql.internal:3306/tech_company', owner: '数据平台组', updatedAt: '2026-07-20 16:42', status: '正常', usage: '8 条 Pipeline', secret: true },
  { id: 'DS-OSS-02', category: '数据源', name: '论文全文对象存储', description: '论文 PDF、解析文本与附件', type: 'S3 / OSS', endpoint: 'oss://kg-paper-fulltext', owner: '知识工程组', updatedAt: '2026-07-19 11:08', status: '正常', usage: '3 条 Pipeline', secret: true },
  { id: 'DS-KAFKA-01', category: '数据源', name: '科技资讯实时流', description: '新闻、政策与产业事件实时数据', type: 'Kafka', endpoint: 'kafka.internal:9092/tech-news', owner: '数据平台组', updatedAt: '2026-07-18 09:31', status: '异常', usage: '2 条 Pipeline', secret: true },
  { id: 'DS-API-03', category: '数据源', name: '专利开放接口', description: '专利著录项、法律状态及引用', type: 'REST API', endpoint: 'https://patent-api.internal/v2', owner: '专利数据组', updatedAt: '2026-07-16 18:20', status: '正常', usage: '1 条 Pipeline', secret: true },
  { id: 'MODEL-LLM-01', category: '模型服务', name: '科技文本抽取大模型', description: '实体、关系、事件与属性联合抽取', type: 'LLM / OpenAI API', endpoint: 'llm-gateway.internal/v1', owner: '算法平台组', updatedAt: '2026-07-20 14:05', status: '正常', usage: '默认抽取模型', secret: true },
  { id: 'MODEL-EMB-02', category: '模型服务', name: '中文语义向量模型', description: '实体召回、相似度计算与消歧', type: 'Embedding', endpoint: 'embedding.internal/v1/embed', owner: '算法平台组', updatedAt: '2026-07-18 13:47', status: '正常', usage: '5 条 Pipeline' },
  { id: 'MODEL-NER-01', category: '模型服务', name: '科技领域 NER', description: '专家、机构、论文及技术术语识别', type: 'NER Service', endpoint: 'ner.internal/v2/extract', owner: '知识工程组', updatedAt: '2026-07-17 10:11', status: '停用', usage: '备用模型' },
  { id: 'SCHEMA-PROD', category: 'Schema', name: '生产图谱 Schema', description: '生产环境实体、关系及属性约束', type: 'Graph Schema', endpoint: 'tech-kg-schema v1.8', owner: '图谱治理组', updatedAt: '2026-07-20 17:20', status: '正常', usage: '12 类实体 · 43 类关系' },
  { id: 'DICT-ORG-02', category: 'Schema', name: '机构类型标准字典', description: '高校、科研院所、企业等类型映射', type: 'Dictionary', endpoint: 'dict-org-category v2.4', owner: '图谱治理组', updatedAt: '2026-07-18 15:30', status: '正常', usage: '128 条映射' },
  { id: 'RULE-DQ-01', category: 'Schema', name: '图谱入库质量规则', description: '必填、唯一性、证据与置信度规则', type: 'Rule Set', endpoint: 'kg-quality-rules v1.3', owner: '质量管理组', updatedAt: '2026-07-15 12:06', status: '正常', usage: '36 条规则' },
  { id: 'SCHEDULE-DEFAULT', category: '调度', name: '生产默认调度策略', description: '错峰运行、失败重试与告警通知', type: 'Schedule Policy', endpoint: 'Asia/Shanghai · 02:00', owner: '平台运维组', updatedAt: '2026-07-19 08:15', status: '正常', usage: '9 条 Pipeline' },
  { id: 'RUNTIME-LARGE', category: '调度', name: '大批量运行资源组', description: '适用于百万级以上批量抽取任务', type: 'Runtime Profile', endpoint: '16 worker · 64 GB', owner: '平台运维组', updatedAt: '2026-07-12 16:55', status: '正常', usage: '并发上限 4' },
])

// const activeCategory = ref('数据源')
const activeCategory = ref('模型服务')
const keyword = ref('')
const statusFilter = ref('全部状态')
const selected = ref<ConfigItem | null>(null)
const dialogOpen = ref(false)
const feedback = ref('')
const testingId = ref('')
const form = ref({ name: '', type: 'MySQL 8.0', endpoint: '', owner: '知识工程组', description: '', username: '', secret: '' })

const visibleItems = computed(() => items.value.filter((item) => {
  const matchCategory = item.category === activeCategory.value
  const query = keyword.value.trim().toLowerCase()
  const matchKeyword = !query || `${item.name}${item.id}${item.type}${item.endpoint}`.toLowerCase().includes(query)
  const matchStatus = statusFilter.value === '全部状态' || item.status === statusFilter.value
  return matchCategory && matchKeyword && matchStatus
}))

const summary = computed(() => ({
  total: items.value.length,
  healthy: items.value.filter((item) => item.status === '正常').length,
  warning: items.value.filter((item) => item.status === '异常').length,
  references: 28,
}))

function openCreate() {
  form.value = { name: '', type: activeCategory.value === '数据源' ? 'MySQL 8.0' : activeCategory.value === '模型服务' ? 'LLM API' : 'Graph Schema', endpoint: '', owner: '知识工程组', description: '', username: '', secret: '' }
  dialogOpen.value = true
}

function saveConfig() {
  if (!form.value.name.trim() || !form.value.endpoint.trim()) return
  const prefix = activeCategory.value === '数据源' ? 'DS' : activeCategory.value === '模型服务' ? 'MODEL' : activeCategory.value === 'Schema' ? 'SCHEMA' : 'SCHEDULE'
  items.value.unshift({
    id: `${prefix}-${String(items.value.length + 1).padStart(2, '0')}`,
    category: activeCategory.value,
    name: form.value.name,
    description: form.value.description || '新建平台配置',
    type: form.value.type,
    endpoint: form.value.endpoint,
    owner: form.value.owner,
    updatedAt: '刚刚',
    status: '正常',
    usage: '尚未引用',
    secret: Boolean(form.value.secret),
  })
  dialogOpen.value = false
  feedback.value = `“${form.value.name}”已保存，可在 Pipeline 中引用。`
}

function testConnection(item: ConfigItem) {
  testingId.value = item.id
  feedback.value = ''
  window.setTimeout(() => {
    testingId.value = ''
    item.status = '正常'
    feedback.value = `${item.name}连接测试成功，延迟 38 ms。`
  }, 650)
}

function toggleItem(item: ConfigItem) {
  item.status = item.status === '停用' ? '正常' : '停用'
  feedback.value = `${item.name}已${item.status === '停用' ? '停用' : '启用'}。`
}
</script>

<template>
  <div class="configuration-page">
    <header class="page-header">
      <div><span>PLATFORM CONFIGURATION</span><p>统一管理 Pipeline 运行依赖的数据源、模型服务、Schema、字典及调度策略。</p></div>
      <button class="primary" type="button" @click="openCreate">＋ 新建配置</button>
    </header>

    <section class="summary-grid">
      <article><i class="blue">∑</i><div><span>配置总数</span><strong>{{ summary.total }}</strong><small>覆盖 4 类平台能力</small></div></article>
      <article><i class="green">✓</i><div><span>运行正常</span><strong>{{ summary.healthy }}</strong><small>最近检测 2 分钟前</small></div></article>
      <article><i class="orange">!</i><div><span>需要关注</span><strong>{{ summary.warning }}</strong><small>Kafka 连接延迟异常</small></div></article>
      <article><i class="purple">↗</i><div><span>Pipeline 引用</span><strong>{{ summary.references }}</strong><small>跨 11 条生产流程</small></div></article>
    </section>

    <p v-if="feedback" class="feedback"><span>✓</span>{{ feedback }}<button type="button" @click="feedback=''">×</button></p>

    <section class="config-workbench">
      <aside class="category-nav">
        <header><strong>配置分类</strong><span>按能力域管理</span></header>
        <button v-for="category in categories" :key="category.key" type="button" :class="{ active: activeCategory === category.key }" @click="activeCategory=category.key;selected=null">
          <i>{{ category.icon }}</i><span><strong>{{ category.label }}</strong><small>{{ category.key === '数据源' ? '数据库、文件与消息流' : category.key === '模型服务' ? 'LLM、向量与抽取模型' : category.key === 'Schema' ? '图谱约束、字典与规则' : '定时、重试与资源配置' }}</small></span><em>{{ items.filter(item => item.category === category.key).length }}</em>
        </button>
        <section><b>凭据安全</b><p>密码与 API Key 使用密钥中心加密保存，页面仅展示脱敏值。</p><a href="#" @click.prevent="feedback='已打开凭据访问审计。'">查看访问审计 →</a></section>
      </aside>

      <main class="config-list">
        <header><div><h2>{{ categories.find(item => item.key === activeCategory)?.label }}</h2><span>{{ visibleItems.length }} 项配置</span></div><nav><input v-model="keyword" placeholder="搜索名称、标识或地址" /><select v-model="statusFilter"><option>全部状态</option><option>正常</option><option>异常</option><option>停用</option></select></nav></header>
        <div class="table-wrap">
          <table>
            <thead><tr><th>配置名称</th><th>类型 / 地址</th><th>状态</th><th>引用情况</th><th>负责人 / 更新时间</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="item in visibleItems" :key="item.id" @click="selected=item">
                <td><div class="config-name"><i>{{ item.category === '数据源' ? 'DB' : item.category === '模型服务' ? 'AI' : item.category === 'Schema' ? 'SC' : 'CR' }}</i><span><strong>{{ item.name }}</strong><small>{{ item.id }} · {{ item.description }}</small></span></div></td>
                <td><strong class="type-name">{{ item.type }}</strong><code>{{ item.endpoint }}</code></td>
                <td><span class="status" :class="`is-${item.status}`"><i />{{ item.status }}</span></td>
                <td>{{ item.usage }}</td>
                <td><span>{{ item.owner }}</span><small class="updated">{{ item.updatedAt }}</small></td>
                <td><button class="link" type="button" @click.stop="selected=item">管理</button></td>
              </tr>
              <tr v-if="!visibleItems.length"><td class="empty" colspan="6">没有符合条件的配置</td></tr>
            </tbody>
          </table>
        </div>
      </main>
    </section>

    <button v-if="selected || dialogOpen" class="mask" type="button" aria-label="关闭" @click="selected=null;dialogOpen=false" />
    <aside v-if="selected" class="detail-drawer">
      <header><div><span>{{ selected.id }}</span><h2>{{ selected.name }}</h2><p>{{ selected.description }}</p></div><button type="button" @click="selected=null">×</button></header>
      <section class="health-card"><i :class="`is-${selected.status}`" /><div><strong>{{ selected.status === '正常' ? '配置可用' : selected.status === '异常' ? '连接存在异常' : '配置已停用' }}</strong><span>最近健康检查：2 分钟前</span></div><button type="button" :disabled="testingId === selected.id" @click="testConnection(selected)">{{ testingId === selected.id ? '测试中…' : '测试连接' }}</button></section>
      <div class="detail-form">
        <label><span>配置名称</span><input v-model="selected.name" /></label>
        <label><span>服务类型</span><input v-model="selected.type" /></label>
        <label class="wide"><span>连接地址 / 版本</span><input v-model="selected.endpoint" /></label>
        <label class="wide"><span>配置说明</span><textarea v-model="selected.description" /></label>
        <label><span>负责人</span><input v-model="selected.owner" /></label>
        <label><span>访问凭据</span><input :value="selected.secret ? '••••••••••••••••' : '无需凭据'" readonly /></label>
      </div>
      <section class="reference-card"><header><strong>引用关系</strong><span>{{ selected.usage }}</span></header><p>配置变更将在下次 Pipeline 运行时生效。删除前需先解除所有生产流程引用。</p></section>
      <footer><button type="button" @click="toggleItem(selected)">{{ selected.status === '停用' ? '启用配置' : '停用配置' }}</button><button class="primary" type="button" @click="feedback=`${selected.name}的修改已保存。`;selected=null">保存修改</button></footer>
    </aside>

    <aside v-if="dialogOpen" class="create-dialog">
      <header><div><span>NEW CONFIGURATION</span><h2>新建{{ categories.find(item => item.key === activeCategory)?.label }}</h2></div><button type="button" @click="dialogOpen=false">×</button></header>
      <div class="dialog-form">
        <label><span>配置名称 *</span><input v-model="form.name" placeholder="例如：科技项目数据仓库" /></label>
        <label><span>连接类型 *</span><select v-model="form.type"><option>MySQL 8.0</option><option>PostgreSQL</option><option>REST API</option><option>Kafka</option><option>S3 / OSS</option><option>LLM API</option><option>Graph Schema</option></select></label>
        <label class="wide"><span>连接地址 / 版本 *</span><input v-model="form.endpoint" placeholder="主机地址、Topic、Bucket 或服务 URL" /></label>
        <label><span>访问账号</span><input v-model="form.username" placeholder="可选" /></label>
        <label><span>密码 / API Key</span><input v-model="form.secret" type="password" placeholder="加密保存" /></label>
        <label><span>负责人</span><input v-model="form.owner" /></label>
        <label class="wide"><span>说明</span><textarea v-model="form.description" placeholder="说明数据范围、用途或变更影响" /></label>
      </div>
      <footer><button type="button" @click="dialogOpen=false">取消</button><button class="primary" type="button" :disabled="!form.name.trim() || !form.endpoint.trim()" @click="saveConfig">保存并测试</button></footer>
    </aside>
  </div>
</template>

<style scoped>
.configuration-page{display:flex;box-sizing:border-box;height:100%;min-height:0;overflow:hidden;color:#17233b;flex-direction:column}.page-header{display:flex;flex:0 0 auto;align-items:flex-end;justify-content:space-between;margin-bottom:12px}.page-header span{color:#165dff;font-size:9px;letter-spacing:.12em}.page-header h1{margin:3px 0 0;font-size:22px}.page-header p{margin:4px 0 0;color:#66758f;font-size:11px}.primary{border-color:#165dff!important;background:#165dff!important;color:#fff!important}.page-header button{height:34px;padding:0 14px;border:0;border-radius:6px;cursor:pointer}.summary-grid{display:grid;flex:0 0 auto;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:10px}.summary-grid article{display:flex;align-items:center;gap:11px;padding:10px 13px;border:1px solid #bdd7ff;border-radius:8px;background:linear-gradient(145deg,#fff,#f2f8ff)}.summary-grid article>i{display:grid;place-items:center;width:34px;height:34px;border-radius:8px;font-style:normal;font-weight:700}.summary-grid .blue{background:#eaf2ff;color:#165dff}.summary-grid .green{background:#dcfae6;color:#067647}.summary-grid .orange{background:#fff3d8;color:#b54708}.summary-grid .purple{background:#f4f3ff;color:#5925dc}.summary-grid article>div{display:grid;grid-template-columns:1fr auto;flex:1;gap:2px}.summary-grid span,.summary-grid small{color:#71809a;font-size:9px}.summary-grid strong{grid-row:1/3;grid-column:2;font-size:20px}.feedback{display:flex;align-items:center;gap:8px;margin:0 0 10px;padding:8px 11px;border:1px solid #a6f4c5;border-radius:6px;background:#ecfdf3;color:#067647;font-size:10px}.feedback span{display:grid;place-items:center;width:17px;height:17px;border-radius:50%;background:#12b76a;color:#fff}.feedback button{margin-left:auto;border:0;background:transparent;color:#067647;cursor:pointer}.config-workbench{display:grid;flex:1;min-height:0;grid-template-columns:248px minmax(0,1fr);overflow:hidden;border:1px solid #bdd7ff;border-radius:9px;background:#fff}.category-nav{display:flex;min-height:0;border-right:1px solid #dce8f8;background:#f8fbff;flex-direction:column}.category-nav>header{display:grid;gap:3px;padding:14px;border-bottom:1px solid #dce8f8}.category-nav>header strong{font-size:13px}.category-nav>header span{color:#8290a7;font-size:9px}.category-nav>button{display:grid;grid-template-columns:32px minmax(0,1fr) auto;align-items:center;gap:9px;width:100%;padding:11px 12px;border:0;border-bottom:1px solid #edf2f8;background:transparent;color:#344766;text-align:left;cursor:pointer}.category-nav>button.active{background:#eaf2ff;box-shadow:inset 3px 0 #165dff}.category-nav>button>i{display:grid;place-items:center;width:30px;height:30px;border-radius:7px;background:#fff;color:#526783;font-size:9px;font-style:normal;font-weight:700}.category-nav>button.active>i{background:#165dff;color:#fff}.category-nav>button>span{display:grid;gap:3px}.category-nav>button strong{font-size:11px}.category-nav>button small{color:#8290a7;font-size:8px}.category-nav>button em{min-width:20px;padding:2px 6px;border-radius:99px;background:#e7eef8;color:#71809a;font-size:9px;font-style:normal;text-align:center}.category-nav>section{margin:auto 12px 12px;padding:11px;border:1px solid #d6e3f4;border-radius:7px;background:#fff}.category-nav>section b{font-size:10px}.category-nav>section p{margin:4px 0 6px;color:#71809a;font-size:9px;line-height:15px}.category-nav>section a{color:#165dff;font-size:9px;text-decoration:none}.config-list{display:flex;min-width:0;min-height:0;flex-direction:column}.config-list>header{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-bottom:1px solid #dce8f8;background:#fff}.config-list>header>div{display:flex;align-items:baseline;gap:8px}.config-list h2{margin:0;font-size:15px}.config-list>header span{color:#8290a7;font-size:9px}.config-list nav{display:flex;gap:7px}.config-list input,.config-list select{height:31px;padding:0 9px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#344766;font-size:10px}.config-list input{width:210px}.table-wrap{flex:1;min-height:0;overflow:auto}.table-wrap table{width:100%;border-collapse:collapse;font-size:10px}.table-wrap thead{position:sticky;z-index:2;top:0}.table-wrap th,.table-wrap td{padding:10px 11px;border-bottom:1px solid #e7eef7;text-align:left;vertical-align:middle}.table-wrap th{background:#f2f7fd;color:#60708a;font-weight:600;white-space:nowrap}.table-wrap tbody tr{cursor:pointer}.table-wrap tbody tr:hover td{background:#f7faff}.config-name{display:flex;align-items:center;gap:9px;min-width:210px}.config-name>i{display:grid;place-items:center;flex:0 0 auto;width:29px;height:29px;border-radius:7px;background:#eaf2ff;color:#175cd3;font-size:8px;font-style:normal;font-weight:700}.config-name>span{display:grid;gap:3px}.config-name strong{font-size:11px}.config-name small,.updated{display:block;color:#8290a7;font-size:8px}.type-name{display:block;color:#40516d;font-size:10px}.table-wrap code{display:block;max-width:210px;margin-top:3px;overflow:hidden;color:#71809a;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.status{display:inline-flex;align-items:center;gap:5px;padding:3px 7px;border-radius:99px}.status>i{width:6px;height:6px;border-radius:50%;background:currentColor}.status.is-正常{background:#dcfae6;color:#067647}.status.is-异常{background:#fee4e2;color:#b42318}.status.is-停用{background:#eef1f5;color:#667085}.link{border:0;background:transparent;color:#165dff;font-size:10px;cursor:pointer}.empty{height:100px;color:#8290a7;text-align:center!important}.mask{position:fixed;z-index:40;inset:0;border:0;background:rgba(16,36,76,.24)}.detail-drawer{position:fixed;z-index:41;top:0;right:0;display:flex;width:min(500px,90vw);height:100vh;background:#f8fbff;box-shadow:-18px 0 46px rgba(28,58,107,.25);flex-direction:column}.detail-drawer>header,.create-dialog>header{display:flex;align-items:flex-start;justify-content:space-between;padding:18px;border-bottom:1px solid #dce8f8;background:#fff}.detail-drawer>header span,.create-dialog>header span{color:#165dff;font-size:9px}.detail-drawer h2,.create-dialog h2{margin:4px 0;font-size:18px}.detail-drawer>header p{margin:0;color:#71809a;font-size:10px}.detail-drawer>header button,.create-dialog>header button{width:29px;height:29px;border:0;border-radius:5px;background:#f0f4fa;font-size:19px;cursor:pointer}.health-card{display:grid;grid-template-columns:10px minmax(0,1fr) auto;align-items:center;gap:10px;margin:14px 16px 0;padding:12px;border:1px solid #cfe4d7;border-radius:7px;background:#fff}.health-card>i{width:9px;height:9px;border-radius:50%;background:#12b76a;box-shadow:0 0 0 4px rgba(18,183,106,.12)}.health-card>i.is-异常{background:#f04438;box-shadow:0 0 0 4px rgba(240,68,56,.12)}.health-card>i.is-停用{background:#98a2b3;box-shadow:none}.health-card>div{display:grid;gap:3px}.health-card strong{font-size:11px}.health-card span{color:#71809a;font-size:9px}.health-card button{height:29px;padding:0 10px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#165dff;font-size:9px;cursor:pointer}.detail-form,.dialog-form{display:grid;grid-template-columns:1fr 1fr;gap:11px;padding:16px}.detail-form label,.dialog-form label{display:grid;gap:5px}.detail-form label span,.dialog-form label span{color:#60708a;font-size:9px}.detail-form input,.detail-form textarea,.dialog-form input,.dialog-form select,.dialog-form textarea{box-sizing:border-box;width:100%;height:33px;padding:0 9px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#344766;font:10px inherit}.detail-form textarea,.dialog-form textarea{height:65px;padding-top:8px;resize:none}.wide{grid-column:1/-1}.reference-card{margin:0 16px;padding:12px;border:1px solid #d6e3f4;border-radius:7px;background:#fff}.reference-card header{display:flex;justify-content:space-between}.reference-card strong{font-size:10px}.reference-card span{color:#165dff;font-size:9px}.reference-card p{margin:5px 0 0;color:#71809a;font-size:9px;line-height:16px}.detail-drawer>footer,.create-dialog>footer{display:flex;justify-content:flex-end;gap:8px;margin-top:auto;padding:13px 16px;border-top:1px solid #dce8f8;background:#fff}.detail-drawer>footer button,.create-dialog>footer button{height:33px;padding:0 13px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#40516d;cursor:pointer}.create-dialog{position:fixed;z-index:42;top:50%;left:50%;width:min(650px,calc(100vw - 40px));overflow:hidden;border-radius:10px;background:#f8fbff;box-shadow:0 24px 70px rgba(28,58,107,.3);transform:translate(-50%,-50%)}.create-dialog>footer{margin-top:0}.create-dialog button:disabled{opacity:.5;cursor:not-allowed}@media(max-width:1100px){.summary-grid{grid-template-columns:repeat(2,1fr)}.config-workbench{grid-template-columns:210px minmax(0,1fr)}}
</style>
