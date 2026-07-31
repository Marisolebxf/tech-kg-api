<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";

type OperatorCategory = "输入" | "处理" | "抽取" | "图谱" | "控制";
type OperatorDefinition = {
  type: string;
  name: string;
  category: OperatorCategory;
  icon: string;
  description: string;
  color: string;
};
type PipelineNode = OperatorDefinition & {
  id: string;
  title: string;
  status: "idle" | "running" | "success" | "error";
  config: Record<string, any>;
};

const operatorCatalog: OperatorDefinition[] = [
  {
    type: "data-source",
    name: "数据源",
    category: "输入",
    icon: "DB",
    description: "数据库、API、文件或消息流",
    color: "#175cd3",
  },
  {
    type: "document-parser",
    name: "文档解析",
    category: "处理",
    icon: "DOC",
    description: "解析 PDF、Word 与网页正文",
    color: "#7a5af8",
  },
  {
    type: "abstract",
    name: "摘要生成",
    category: "处理",
    icon: "SUM",
    description: "提炼长文本的核心内容",
    color: "#7a5af8",
  },
  {
    type: "transform",
    name: "字段转换",
    category: "处理",
    icon: "FX",
    description: "清洗、映射、合并与格式转换",
    color: "#7a5af8",
  },
  {
    type: "filter",
    name: "条件过滤",
    category: "处理",
    icon: "IF",
    description: "按表达式保留或丢弃记录",
    color: "#7a5af8",
  },
  {
    type: "entity-extract",
    name: "实体抽取",
    category: "抽取",
    icon: "ENT",
    description: "识别实体、类型及属性",
    color: "#e04f8a",
  },
  {
    type: "relation-extract",
    name: "关系抽取",
    category: "抽取",
    icon: "REL",
    description: "抽取实体之间的语义关系",
    color: "#e04f8a",
  },
  {
    type: "event-extract",
    name: "事件抽取",
    category: "抽取",
    icon: "EVT",
    description: "识别事件、参与方与时间",
    color: "#e04f8a",
  },
  {
    type: "entity-align",
    name: "实体对齐",
    category: "抽取",
    icon: "ID",
    description: "与存量图谱召回、消歧和合并",
    color: "#e04f8a",
  },
  {
    type: "schema-add",
    name: "Schema 新增",
    category: "图谱",
    icon: "+SC",
    description: "创建新的实体或关系类型",
    color: "#079455",
  },
  {
    type: "schema-delete",
    name: "Schema 删除",
    category: "图谱",
    icon: "-SC",
    description: "下线实体、关系或属性定义",
    color: "#d92d20",
  },
  {
    type: "graph-write",
    name: "写入图谱",
    category: "图谱",
    icon: "KG",
    description: "校验并写入目标知识图谱",
    color: "#079455",
  },
  {
    type: "quality-check",
    name: "质量校验",
    category: "控制",
    icon: "QA",
    description: "执行完整性、唯一性与证据规则",
    color: "#f79009",
  },
  {
    type: "manual-review",
    name: "人工处理",
    category: "控制",
    icon: "HITL",
    description: "将低置信结果送入人工队列",
    color: "#f79009",
  },
];

const categoryTabs: Array<"全部" | OperatorCategory> = [
  "全部",
  "输入",
  "处理",
  "抽取",
  "图谱",
  "控制",
];
const activeCategory = ref<"全部" | OperatorCategory>("全部");
const operatorKeyword = ref("");
const pipelineName = ref("科技资讯实体关系抽取");
const pipelineDescription = ref(
  "从科技资讯流中抽取企业、技术、事件及其关系，校验后增量写入生产图谱。",
);
const pipelineStatus = ref<"草稿" | "已发布">("草稿");
const selectedNodeId = ref("node-source");
const feedback = ref("");
const scheduleEnabled = ref(true);
const scheduleMode = ref("每天");
const scheduleTime = ref("02:30");
const retryCount = ref(2);
const timeoutMinutes = ref(60);
const showSettings = ref(true);
const showRuns = ref(false);
const draggedOperator = ref<OperatorDefinition | null>(null);
const running = ref(false);
let runTimers: number[] = [];

const makeConfig = (type: string): Record<string, any> => {
  if (type === "data-source")
    return {
      source: "科技资讯实时流",
      table: "tech_news",
      mode: "增量读取",
      watermark: "publish_time",
    };
  if (type === "document-parser")
    return {
      parser: "智能版面分析 v2",
      output: "Markdown + 元数据",
      ocr: true,
    };
  if (type === "abstract")
    return {
      model: "科技文本抽取大模型",
      maxLength: 500,
      language: "自动检测",
      prompt: "保留技术、机构、产品与事件关键信息",
    };
  if (type === "transform")
    return {
      expression: "trim(title); normalize(publish_time)",
      errorPolicy: "记录异常并继续",
      output: "标准字段集",
    };
  if (type === "filter")
    return {
      expression: "language in [zh, en] AND content_length > 100",
      unmatched: "丢弃",
    };
  if (type === "entity-extract")
    return {
      model: "科技文本抽取大模型",
      schema: "Expert, Organization, Product, ResearchField, Event",
      threshold: 0.82,
      prompt: "严格按 Schema 返回实体及来源证据",
    };
  if (type === "relation-extract")
    return {
      model: "科技文本抽取大模型",
      schema: "HAS_PRODUCT, ORG_FIELD, HAS_EVENT, COOPERATE_WITH",
      threshold: 0.78,
      evidence: true,
    };
  if (type === "event-extract")
    return {
      eventTypes: "融资, 合作, 产品发布, 政策",
      threshold: 0.8,
      timeNormalize: true,
    };
  if (type === "entity-align")
    return {
      index: "生产图谱实体索引",
      topK: 10,
      threshold: 0.86,
      strategy: "名称 + 机构 + 标识符",
    };
  if (type === "quality-check")
    return {
      rules: "图谱入库质量规则 v1.3",
      onFailure: "进入人工处理",
      sampleRate: 100,
    };
  if (type === "manual-review")
    return {
      queue: "图谱建设人工处理队列",
      priority: "按风险自动分级",
      sla: "4 小时",
    };
  if (type === "schema-add")
    return {
      target: "生产图谱 Schema",
      change: "新增实体 / 关系定义",
      approval: "需要 Schema 管理员审批",
    };
  if (type === "schema-delete")
    return {
      target: "生产图谱 Schema",
      change: "选择待下线定义",
      approval: "需要影响分析与审批",
    };
  if (type === "graph-write")
    return {
      graph: "科技知识图谱（生产）",
      mode: "MERGE 增量写入",
      batchSize: 1000,
      version: "自动创建变更版本",
    };
  return {};
};

const initialTypes = [
  "data-source",
  "document-parser",
  "entity-extract",
  "relation-extract",
  "quality-check",
  "graph-write",
];
const nodes = ref<PipelineNode[]>(
  initialTypes.map((type, index) => {
    const definition = operatorCatalog.find((item) => item.type === type)!;
    return {
      ...definition,
      id: index === 0 ? "node-source" : `node-${type}`,
      title: definition.name,
      status: "idle",
      config: makeConfig(type),
    };
  }),
);

const filteredOperators = computed(() =>
  operatorCatalog.filter((item) => {
    const categoryMatch =
      activeCategory.value === "全部" || item.category === activeCategory.value;
    const query = operatorKeyword.value.trim().toLowerCase();
    return (
      categoryMatch &&
      (!query ||
        `${item.name}${item.description}${item.type}`
          .toLowerCase()
          .includes(query))
    );
  }),
);
const selectedNode = computed(
  () => nodes.value.find((node) => node.id === selectedNodeId.value) ?? null,
);
const scheduleDescription = computed(() =>
  scheduleEnabled.value
    ? `${scheduleMode.value} ${scheduleTime.value}（Asia/Shanghai）`
    : "仅手动触发",
);
const pipelineReady = computed(
  () =>
    nodes.value.some((node) => node.type === "data-source") &&
    nodes.value.some((node) => node.type === "graph-write"),
);

function addOperator(
  definition: OperatorDefinition,
  targetIndex = nodes.value.length,
) {
  const node: PipelineNode = {
    ...definition,
    id: `node-${definition.type}-${Date.now()}`,
    title: definition.name,
    status: "idle",
    config: makeConfig(definition.type),
  };
  nodes.value.splice(targetIndex, 0, node);
  selectedNodeId.value = node.id;
  feedback.value = `已添加“${definition.name}”算子，请在右侧完成参数配置。`;
}

function removeNode(id: string) {
  const index = nodes.value.findIndex((node) => node.id === id);
  if (index < 0) return;
  const [removed] = nodes.value.splice(index, 1);
  selectedNodeId.value = nodes.value[Math.max(0, index - 1)]?.id ?? "";
  feedback.value = `已从画布移除“${removed.title}”。`;
}

function moveNode(index: number, delta: number) {
  const target = index + delta;
  if (target < 0 || target >= nodes.value.length) return;
  const [node] = nodes.value.splice(index, 1);
  nodes.value.splice(target, 0, node);
}

function handleDragStart(definition: OperatorDefinition) {
  draggedOperator.value = definition;
}

function handleDrop(index: number) {
  if (draggedOperator.value) addOperator(draggedOperator.value, index);
  draggedOperator.value = null;
}

function savePipeline(publish = false) {
  if (!pipelineName.value.trim()) return;
  pipelineStatus.value = publish ? "已发布" : pipelineStatus.value;
  feedback.value = publish
    ? `Pipeline 已发布，下一次计划执行时间为 2026-07-22 ${scheduleTime.value}。`
    : "Pipeline 草稿已保存。";
}

function testRun() {
  if (running.value || !pipelineReady.value) return;
  runTimers.forEach(window.clearTimeout);
  runTimers = [];
  running.value = true;
  feedback.value = "试运行已启动，正在读取 100 条样例数据。";
  nodes.value.forEach((node) => {
    node.status = "idle";
  });
  nodes.value.forEach((node, index) => {
    runTimers.push(
      window.setTimeout(() => {
        if (index > 0) nodes.value[index - 1].status = "success";
        node.status = "running";
        selectedNodeId.value = node.id;
        if (index === nodes.value.length - 1) {
          runTimers.push(
            window.setTimeout(() => {
              node.status = "success";
              running.value = false;
              feedback.value =
                "试运行成功：读取 100 条，抽取 386 个实体、241 条关系，7 条进入人工处理。";
            }, 500),
          );
        }
      }, index * 420),
    );
  });
}

onBeforeUnmount(() => runTimers.forEach(window.clearTimeout));
</script>

<template>
  <div class="pipeline-page">
    <header class="designer-header">
      <div class="pipeline-identity">
        <span>PIPELINE DESIGNER</span>
        <div>
          <input v-model="pipelineName" aria-label="Pipeline 名称" /><em
            :class="{ published: pipelineStatus === '已发布' }"
            >{{ pipelineStatus }}</em
          >
        </div>
        <p>{{ pipelineDescription }}</p>
      </div>
      <nav>
        <button type="button" @click="showRuns = !showRuns">运行记录</button>
        <button
          type="button"
          :disabled="running || !pipelineReady"
          @click="testRun"
        >
          {{ running ? "运行中…" : "▷ 试运行" }}
        </button>
        <button type="button" @click="savePipeline(false)">保存草稿</button>
        <button
          class="primary"
          type="button"
          :disabled="!pipelineReady"
          @click="savePipeline(true)"
        >
          发布 Pipeline
        </button>
      </nav>
    </header>

    <p v-if="feedback" class="designer-feedback">
      <span>✓</span>{{ feedback
      }}<button type="button" @click="feedback = ''">×</button>
    </p>

    <section class="designer-shell">
      <aside class="operator-library">
        <header>
          <div>
            <strong>算子库</strong
            ><span>{{ operatorCatalog.length }} 个可用算子</span>
          </div>
          <input v-model="operatorKeyword" placeholder="搜索算子" />
        </header>
        <nav>
          <button
            v-for="category in categoryTabs"
            :key="category"
            type="button"
            :class="{ active: activeCategory === category }"
            @click="activeCategory = category"
          >
            {{ category }}
          </button>
        </nav>
        <div class="operator-list">
          <button
            v-for="operator in filteredOperators"
            :key="operator.type"
            type="button"
            draggable="true"
            @dragstart="handleDragStart(operator)"
            @dragend="draggedOperator = null"
            @click="addOperator(operator)"
          >
            <i
              :style="{
                background: `${operator.color}16`,
                color: operator.color,
              }"
              >{{ operator.icon }}</i
            >
            <span
              ><strong>{{ operator.name }}</strong
              ><small>{{ operator.description }}</small></span
            ><em>＋</em>
          </button>
        </div>
        <footer>
          <strong>使用提示</strong>
          <p>
            点击或拖拽算子到画布；同一算子可重复添加，用于构建分阶段处理逻辑。
          </p>
        </footer>
      </aside>

      <main class="pipeline-canvas">
        <header>
          <div>
            <strong>流程画布</strong
            ><span>{{ nodes.length }} 个节点 · 自动保存于 10:42:18</span>
          </div>
          <nav>
            <button type="button" title="缩小">−</button><span>100%</span
            ><button type="button" title="放大">＋</button
            ><button type="button" title="整理布局">自动布局</button>
          </nav>
        </header>
        <div
          class="canvas-area"
          @dragover.prevent
          @drop.prevent="handleDrop(nodes.length)"
        >
          <div class="canvas-grid" />
          <section class="pipeline-summary">
            <span><i class="green" />数据源已连接</span
            ><span
              ><i class="blue" />{{
                nodes.filter((node) => node.category === "抽取").length
              }}
              个抽取算子</span
            ><span><i class="orange" />{{ scheduleDescription }}</span>
          </section>
          <div class="node-flow">
            <template v-for="(node, index) in nodes" :key="node.id">
              <div
                class="drop-target"
                @dragover.prevent
                @drop.stop.prevent="handleDrop(index)"
              >
                <span>在此插入</span>
              </div>
              <article
                class="pipeline-node"
                :class="[
                  { selected: selectedNodeId === node.id },
                  `is-${node.status}`,
                ]"
                @click="selectedNodeId = node.id"
              >
                <header>
                  <i
                    :style="{
                      background: `${node.color}16`,
                      color: node.color,
                    }"
                    >{{ node.icon }}</i
                  ><span
                    ><small>{{ node.category }}算子</small
                    ><input v-model="node.title" @click.stop /></span
                  ><em v-if="node.status === 'running'">运行中</em
                  ><em v-else-if="node.status === 'success'" class="success"
                    >成功</em
                  ><em v-else>已配置</em>
                </header>
                <p>{{ node.description }}</p>
                <dl>
                  <div
                    v-for="(value, key) in Object.fromEntries(
                      Object.entries(node.config).slice(0, 2),
                    )"
                    :key="key"
                  >
                    <dt>{{ key }}</dt>
                    <dd>
                      {{
                        typeof value === "boolean"
                          ? value
                            ? "是"
                            : "否"
                          : value
                      }}
                    </dd>
                  </div>
                </dl>
                <footer>
                  <span>节点 {{ String(index + 1).padStart(2, "0") }}</span>
                  <nav>
                    <button
                      type="button"
                      :disabled="index === 0"
                      title="上移"
                      @click.stop="moveNode(index, -1)"
                    >
                      ↑</button
                    ><button
                      type="button"
                      :disabled="index === nodes.length - 1"
                      title="下移"
                      @click.stop="moveNode(index, 1)"
                    >
                      ↓</button
                    ><button
                      class="danger"
                      type="button"
                      title="删除"
                      @click.stop="removeNode(node.id)"
                    >
                      ×
                    </button>
                  </nav>
                </footer>
              </article>
              <div v-if="index < nodes.length - 1" class="connector">
                <i /><span>成功后继续</span><i />
              </div>
            </template>
            <div
              class="drop-target end"
              @dragover.prevent
              @drop.stop.prevent="handleDrop(nodes.length)"
            >
              <span>＋ 拖入下一个算子</span>
            </div>
          </div>
        </div>
      </main>

      <aside class="property-panel">
        <nav>
          <button
            type="button"
            :class="{ active: showSettings }"
            @click="showSettings = true"
          >
            节点配置</button
          ><button
            type="button"
            :class="{ active: !showSettings }"
            @click="showSettings = false"
          >
            运行与调度
          </button>
        </nav>
        <template v-if="showSettings && selectedNode">
          <header>
            <div>
              <i
                :style="{
                  background: `${selectedNode.color}16`,
                  color: selectedNode.color,
                }"
                >{{ selectedNode.icon }}</i
              ><span
                ><strong>{{ selectedNode.title }}</strong
                ><small>{{ selectedNode.type }}</small></span
              >
            </div>
            <em>节点参数</em>
          </header>
          <div class="property-form">
            <label
              ><span>节点名称</span><input v-model="selectedNode.title"
            /></label>
            <template v-for="(value, key) in selectedNode.config" :key="key">
              <label v-if="typeof value === 'boolean'" class="toggle-field"
                ><span>{{ key }}</span
                ><button
                  type="button"
                  :class="{ on: value }"
                  @click="selectedNode.config[key] = !value"
                >
                  <i /></button
              ></label>
              <label v-else
                ><span>{{ key }}</span
                ><input
                  v-if="typeof value === 'number'"
                  v-model.number="selectedNode.config[key]"
                  type="number" /><textarea
                  v-else-if="String(value).length > 44"
                  v-model="selectedNode.config[key]" /><input
                  v-else
                  v-model="selectedNode.config[key]"
              /></label>
            </template>
            <section v-if="selectedNode.category === '抽取'">
              <strong>输出预览</strong>
              <p>
                输出将包含
                <code>entities[]</code
                >、<code>relations[]</code>、置信度及来源证据，可供后续算子直接引用。
              </p>
            </section>
          </div>
          <footer>
            <button
              type="button"
              @click="feedback = `${selectedNode.title}参数已应用。`"
            >
              应用节点配置
            </button>
          </footer>
        </template>
        <template v-else>
          <header>
            <div>
              <i class="schedule-icon">CR</i
              ><span
                ><strong>运行与调度</strong
                ><small>触发、重试及资源策略</small></span
              >
            </div>
          </header>
          <div class="property-form schedule-form">
            <label class="toggle-field"
              ><span>启用定时任务<small>发布后按计划自动执行</small></span
              ><button
                type="button"
                :class="{ on: scheduleEnabled }"
                @click="scheduleEnabled = !scheduleEnabled"
              >
                <i /></button
            ></label>
            <label
              ><span>执行频率</span
              ><select v-model="scheduleMode" :disabled="!scheduleEnabled">
                <option>每小时</option>
                <option>每 6 小时</option>
                <option>每天</option>
                <option>每周一</option>
                <option>每月 1 日</option>
              </select></label
            >
            <label
              ><span>执行时间</span
              ><input
                v-model="scheduleTime"
                type="time"
                :disabled="!scheduleEnabled"
            /></label>
            <label
              ><span>失败重试次数</span
              ><input v-model.number="retryCount" type="number" min="0" max="5"
            /></label>
            <label
              ><span>运行超时（分钟）</span
              ><input v-model.number="timeoutMinutes" type="number" min="10"
            /></label>
            <label
              ><span>运行资源组</span
              ><select>
                <option>标准运行资源组（推荐）</option>
                <option>大批量运行资源组</option>
                <option>实时低延迟资源组</option>
              </select></label
            >
            <label
              ><span>失败通知</span
              ><select>
                <option>平台通知 + 企业微信</option>
                <option>仅平台通知</option>
                <option>邮件通知</option>
              </select></label
            >
            <section>
              <strong>下次计划执行</strong>
              <p>
                {{
                  scheduleEnabled
                    ? `2026-07-22 ${scheduleTime}（Asia/Shanghai）`
                    : "定时任务未启用"
                }}
              </p>
            </section>
          </div>
          <footer>
            <button type="button" @click="feedback = '运行与调度策略已保存。'">
              保存运行策略
            </button>
          </footer>
        </template>
      </aside>
    </section>

    <button
      v-if="showRuns"
      class="mask"
      type="button"
      aria-label="关闭运行记录"
      @click="showRuns = false"
    />
    <aside v-if="showRuns" class="run-drawer">
      <header>
        <div>
          <span>RUN HISTORY</span>
          <h2>Pipeline 运行记录</h2>
          <p>{{ pipelineName }}</p>
        </div>
        <button type="button" @click="showRuns = false">×</button>
      </header>
      <section class="run-overview">
        <article><span>近 7 日运行</span><strong>14</strong></article>
        <article><span>成功率</span><strong>92.9%</strong></article>
        <article><span>平均耗时</span><strong>18m</strong></article>
      </section>
      <div class="run-list">
        <article>
          <i class="success">✓</i>
          <div>
            <strong>RUN-20260721-0230</strong
            ><span>定时触发 · 02:30:00 — 02:48:16</span>
            <p>读取 24,755 条 · 实体 83,412 · 关系 61,208 · 人工处理 126 条</p>
          </div>
          <em>成功</em>
        </article>
        <article>
          <i class="success">✓</i>
          <div>
            <strong>RUN-20260720-1642</strong
            ><span>张建图手动触发 · 16:42:09 — 16:43:31</span>
            <p>样例 100 条 · 实体 386 · 关系 241 · 人工处理 7 条</p>
          </div>
          <em>成功</em>
        </article>
        <article>
          <i class="error">!</i>
          <div>
            <strong>RUN-20260720-0230</strong
            ><span>定时触发 · 02:30:00 — 02:34:52</span>
            <p>科技资讯 Kafka 连接超时，重试 2 次后停止。</p>
          </div>
          <em class="error-text">失败</em>
        </article>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.pipeline-page {
  display: flex;
  box-sizing: border-box;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  color: #17233b;
  flex-direction: column;
}
.designer-header {
  display: flex;
  flex: 0 0 auto;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 10px;
}
.pipeline-identity > span {
  color: #165dff;
  font-size: 9px;
  letter-spacing: 0.12em;
}
.pipeline-identity > div {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
}
.pipeline-identity input {
  width: 420px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #17233b;
  font: 600 21px/28px inherit;
}
.pipeline-identity input:focus {
  outline: 0;
  border-bottom: 1px solid #8fb7f2;
}
.pipeline-identity em {
  padding: 3px 8px;
  border-radius: 99px;
  background: #fff3d8;
  color: #b54708;
  font-size: 9px;
  font-style: normal;
}
.pipeline-identity em.published {
  background: #dcfae6;
  color: #067647;
}
.pipeline-identity p {
  max-width: 720px;
  margin: 3px 0 0;
  overflow: hidden;
  color: #66758f;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.designer-header > nav {
  display: flex;
  gap: 7px;
}
.designer-header > nav button {
  height: 33px;
  padding: 0 12px;
  border: 1px solid #bdd0ea;
  border-radius: 5px;
  background: #fff;
  color: #40516d;
  font-size: 10px;
  cursor: pointer;
}
.designer-header > nav button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.primary {
  border-color: #165dff !important;
  background: #165dff !important;
  color: #fff !important;
}
.designer-feedback {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 9px;
  padding: 7px 10px;
  border: 1px solid #a6f4c5;
  border-radius: 6px;
  background: #ecfdf3;
  color: #067647;
  font-size: 9px;
}
.designer-feedback > span {
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #12b76a;
  color: #fff;
}
.designer-feedback button {
  margin-left: auto;
  border: 0;
  background: transparent;
  color: #067647;
  cursor: pointer;
}
.designer-shell {
  display: grid;
  flex: 1;
  min-height: 0;
  grid-template-columns: 230px minmax(480px, 1fr) 280px;
  overflow: hidden;
  border: 1px solid #afcff9;
  border-radius: 9px;
  background: #fff;
}
.operator-library {
  display: flex;
  min-height: 0;
  border-right: 1px solid #dce8f8;
  background: #f8fbff;
  flex-direction: column;
}
.operator-library > header {
  padding: 12px;
  border-bottom: 1px solid #dce8f8;
}
.operator-library > header > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.operator-library > header strong {
  font-size: 12px;
}
.operator-library > header span {
  color: #8290a7;
  font-size: 8px;
}
.operator-library > header input {
  box-sizing: border-box;
  width: 100%;
  height: 29px;
  margin-top: 9px;
  padding: 0 9px;
  border: 1px solid #bdd0ea;
  border-radius: 5px;
  background: #fff;
  font-size: 9px;
}
.operator-library > nav {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  padding: 8px 10px;
  border-bottom: 1px solid #e4ecf6;
}
.operator-library > nav button {
  padding: 4px 7px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #66758f;
  font-size: 9px;
  cursor: pointer;
}
.operator-library > nav button.active {
  background: #eaf2ff;
  color: #165dff;
  font-weight: 600;
}
.operator-list {
  flex: 1;
  min-height: 0;
  padding: 7px;
  overflow: auto;
}
.operator-list > button {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  width: 100%;
  margin-bottom: 5px;
  padding: 8px;
  border: 1px solid #dce8f8;
  border-radius: 6px;
  background: #fff;
  color: #344766;
  text-align: left;
  cursor: grab;
}
.operator-list > button:hover {
  border-color: #8fb7f2;
  box-shadow: 0 4px 10px rgba(48, 105, 194, 0.08);
}
.operator-list > button:active {
  cursor: grabbing;
}
.operator-list i {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 7px;
  font-size: 8px;
  font-style: normal;
  font-weight: 700;
}
.operator-list span {
  display: grid;
  gap: 2px;
}
.operator-list strong {
  font-size: 10px;
}
.operator-list small {
  overflow: hidden;
  color: #8290a7;
  font-size: 8px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.operator-list em {
  color: #165dff;
  font-size: 15px;
  font-style: normal;
}
.operator-library > footer {
  margin: 8px;
  padding: 9px;
  border: 1px solid #d6e3f4;
  border-radius: 6px;
  background: #fff;
}
.operator-library > footer strong {
  font-size: 9px;
}
.operator-library > footer p {
  margin: 3px 0 0;
  color: #71809a;
  font-size: 8px;
  line-height: 14px;
}
.pipeline-canvas {
  display: flex;
  min-width: 0;
  min-height: 0;
  background: #f4f8fd;
  flex-direction: column;
}
.pipeline-canvas > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 12px;
  border-bottom: 1px solid #dce8f8;
  background: #fff;
}
.pipeline-canvas > header > div {
  display: grid;
  gap: 2px;
}
.pipeline-canvas > header strong {
  font-size: 12px;
}
.pipeline-canvas > header span {
  color: #8290a7;
  font-size: 8px;
}
.pipeline-canvas > header nav {
  display: flex;
  align-items: center;
}
.pipeline-canvas > header nav button,
.pipeline-canvas > header nav span {
  height: 25px;
  padding: 0 8px;
  border: 1px solid #d5e1f1;
  background: #fff;
  color: #526783;
  font-size: 9px;
  line-height: 23px;
}
.pipeline-canvas > header nav button {
  cursor: pointer;
}
.canvas-area {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.canvas-grid {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(#aec5e4 1px, transparent 1px);
  background-size: 20px 20px;
  opacity: 0.42;
  pointer-events: none;
}
.pipeline-summary {
  position: sticky;
  z-index: 3;
  top: 9px;
  display: flex;
  width: max-content;
  gap: 12px;
  margin: 9px auto 0;
  padding: 6px 10px;
  border: 1px solid #d6e3f4;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 4px 12px rgba(44, 91, 157, 0.07);
}
.pipeline-summary span {
  display: flex;
  align-items: center;
  gap: 5px;
  color: #66758f;
  font-size: 8px;
}
.pipeline-summary i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.pipeline-summary .green {
  background: #12b76a;
}
.pipeline-summary .blue {
  background: #2e90fa;
}
.pipeline-summary .orange {
  background: #f79009;
}
.node-flow {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  width: max-content;
  min-width: 100%;
  min-height: calc(100% - 45px);
  padding: 35px 42px;
}
.pipeline-node {
  width: 230px;
  overflow: hidden;
  border: 1px solid #b9cdea;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 7px 18px rgba(47, 82, 132, 0.1);
  cursor: pointer;
  transition: 0.15s;
}
.pipeline-node:hover,
.pipeline-node.selected {
  border-color: #165dff;
  box-shadow:
    0 0 0 2px rgba(22, 93, 255, 0.12),
    0 9px 22px rgba(47, 82, 132, 0.13);
}
.pipeline-node.is-running {
  border-color: #2e90fa;
  animation: pulse 1s infinite;
}
.pipeline-node.is-success {
  border-color: #75d5a2;
}
.pipeline-node > header {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-height: 58px;
  padding: 10px;
  border-bottom: 1px solid #e7eef7;
}
.pipeline-node > header > i {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 7px;
  font-size: 10px;
  font-style: normal;
  font-weight: 700;
}
.pipeline-node > header > span {
  display: grid;
  min-width: 0;
  gap: 2px;
}
.pipeline-node > header small {
  color: #8290a7;
  font-size: 9px;
  line-height: 14px;
}
.pipeline-node > header input {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  height: 20px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #263853;
  font: 600 12px/18px inherit;
}
.pipeline-node > header input:focus {
  outline: 0;
  border-bottom: 1px solid #8fb7f2;
}
.pipeline-node > header em {
  padding: 2px 6px;
  border-radius: 99px;
  background: #eaf2ff;
  color: #175cd3;
  font-size: 9px;
  font-style: normal;
  line-height: 14px;
  white-space: nowrap;
}
.pipeline-node > header em.success {
  background: #dcfae6;
  color: #067647;
}
.pipeline-node > p {
  display: -webkit-box;
  box-sizing: border-box;
  height: 52px;
  margin: 0;
  padding: 8px 10px;
  overflow: hidden;
  color: #61708a;
  font-size: 11px;
  line-height: 18px;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.pipeline-node dl {
  margin: 0;
  padding: 0 10px;
}
.pipeline-node dl > div {
  display: grid;
  grid-template-columns: 70px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-height: 31px;
  padding: 4px 0;
  border-top: 1px solid #edf2f8;
}
.pipeline-node dt {
  overflow: hidden;
  color: #8290a7;
  font-size: 10px;
  line-height: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pipeline-node dd {
  margin: 0;
  overflow: hidden;
  color: #40516d;
  font-size: 10px;
  line-height: 16px;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pipeline-node > footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
  padding: 7px 9px;
  background: #f8fbff;
}
.pipeline-node > footer > span {
  color: #8290a7;
  font-size: 9px;
  line-height: 16px;
}
.pipeline-node > footer nav {
  display: flex;
  gap: 3px;
}
.pipeline-node > footer button {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 1px solid #d7e2f0;
  border-radius: 4px;
  background: #fff;
  color: #526783;
  font-size: 11px;
  cursor: pointer;
}
.pipeline-node > footer button:disabled {
  opacity: 0.35;
}
.pipeline-node > footer .danger {
  color: #b42318;
}
.connector {
  display: flex;
  align-items: center;
  width: 74px;
}
.connector > i {
  height: 1px;
  background: #82a9df;
  flex: 1;
}
.connector > i:last-child {
  position: relative;
}
.connector > i:last-child::after {
  position: absolute;
  top: -3px;
  right: -1px;
  border-width: 4px 0 4px 5px;
  border-style: solid;
  border-color: transparent transparent transparent #82a9df;
  content: "";
}
.connector span {
  position: absolute;
  margin: -33px 0 0 9px;
  color: #71809a;
  font-size: 9px;
  line-height: 14px;
  white-space: nowrap;
}
.drop-target {
  display: grid;
  width: 16px;
  height: 205px;
  place-items: center;
}
.drop-target span {
  display: none;
  padding: 5px 7px;
  border: 1px dashed #8fb7f2;
  border-radius: 4px;
  background: #eef5ff;
  color: #165dff;
  font-size: 9px;
  line-height: 14px;
  white-space: nowrap;
}
.drop-target:hover {
  width: 82px;
}
.drop-target:hover span {
  display: block;
}
.drop-target.end {
  width: 112px;
}
.drop-target.end span {
  display: block;
}
.property-panel {
  display: flex;
  min-height: 0;
  border-left: 1px solid #dce8f8;
  background: #fff;
  flex-direction: column;
}
.property-panel > nav {
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-bottom: 1px solid #dce8f8;
}
.property-panel > nav button {
  height: 42px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: #fff;
  color: #66758f;
  font-size: 9px;
  cursor: pointer;
}
.property-panel > nav button.active {
  border-color: #165dff;
  color: #165dff;
  font-weight: 600;
}
.property-panel > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 12px;
  border-bottom: 1px solid #e4ecf6;
  background: #f8fbff;
}
.property-panel > header > div {
  display: flex;
  align-items: center;
  gap: 8px;
}
.property-panel > header i {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 7px;
  font-size: 8px;
  font-style: normal;
  font-weight: 700;
}
.property-panel > header span {
  display: grid;
  gap: 2px;
}
.property-panel > header strong {
  font-size: 10px;
}
.property-panel > header small {
  color: #8290a7;
  font-size: 7px;
}
.property-panel > header em {
  color: #8290a7;
  font-size: 8px;
  font-style: normal;
}
.schedule-icon {
  background: #fff3d8 !important;
  color: #b54708 !important;
}
.property-form {
  flex: 1;
  min-height: 0;
  padding: 11px;
  overflow: auto;
}
.property-form > label {
  display: grid;
  gap: 5px;
  margin-bottom: 10px;
}
.property-form label > span {
  color: #5f6f88;
  font-size: 8px;
}
.property-form input,
.property-form select,
.property-form textarea {
  box-sizing: border-box;
  width: 100%;
  height: 31px;
  padding: 0 8px;
  border: 1px solid #bdd0ea;
  border-radius: 5px;
  background: #fff;
  color: #344766;
  font: 9px inherit;
}
.property-form textarea {
  height: 62px;
  padding-top: 7px;
  line-height: 15px;
  resize: none;
}
.property-form input:disabled,
.property-form select:disabled {
  background: #f2f4f7;
  color: #98a2b3;
}
.property-form > section {
  padding: 9px;
  border: 1px solid #d6e3f4;
  border-radius: 6px;
  background: #f8fbff;
}
.property-form > section strong {
  font-size: 9px;
}
.property-form > section p {
  margin: 4px 0 0;
  color: #71809a;
  font-size: 8px;
  line-height: 14px;
}
.property-form code {
  color: #175cd3;
}
.toggle-field {
  display: flex !important;
  align-items: center;
  justify-content: space-between;
}
.toggle-field > span {
  display: grid;
  gap: 2px;
}
.toggle-field small {
  color: #98a2b3;
  font-size: 7px;
}
.toggle-field > button {
  position: relative;
  width: 32px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 9px;
  background: #c9d3e0;
  cursor: pointer;
}
.toggle-field > button i {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  transition: 0.15s;
}
.toggle-field > button.on {
  background: #165dff;
}
.toggle-field > button.on i {
  left: 16px;
}
.property-panel > footer {
  padding: 10px;
  border-top: 1px solid #dce8f8;
}
.property-panel > footer button {
  width: 100%;
  height: 31px;
  border: 0;
  border-radius: 5px;
  background: #165dff;
  color: #fff;
  font-size: 9px;
  cursor: pointer;
}
.mask {
  position: fixed;
  z-index: 40;
  inset: 0;
  border: 0;
  background: rgba(16, 36, 76, 0.24);
}
.run-drawer {
  position: fixed;
  z-index: 41;
  top: 0;
  right: 0;
  display: flex;
  width: min(570px, 92vw);
  height: 100vh;
  background: #f8fbff;
  box-shadow: -18px 0 46px rgba(28, 58, 107, 0.25);
  flex-direction: column;
}
.run-drawer > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 18px;
  border-bottom: 1px solid #dce8f8;
  background: #fff;
}
.run-drawer > header span {
  color: #165dff;
  font-size: 9px;
}
.run-drawer h2 {
  margin: 4px 0;
  font-size: 18px;
}
.run-drawer > header p {
  margin: 0;
  color: #71809a;
  font-size: 10px;
}
.run-drawer > header button {
  width: 29px;
  height: 29px;
  border: 0;
  border-radius: 5px;
  background: #f0f4fa;
  font-size: 19px;
  cursor: pointer;
}
.run-overview {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 9px;
  padding: 13px;
}
.run-overview article {
  display: grid;
  gap: 4px;
  padding: 11px;
  border: 1px solid #d6e3f4;
  border-radius: 6px;
  background: #fff;
}
.run-overview span {
  color: #71809a;
  font-size: 9px;
}
.run-overview strong {
  font-size: 18px;
}
.run-list {
  padding: 0 13px;
  overflow: auto;
}
.run-list article {
  display: grid;
  grid-template-columns: 31px minmax(0, 1fr) auto;
  align-items: start;
  gap: 9px;
  margin-bottom: 8px;
  padding: 12px;
  border: 1px solid #dce8f8;
  border-radius: 7px;
  background: #fff;
}
.run-list > article > i {
  display: grid;
  place-items: center;
  width: 29px;
  height: 29px;
  border-radius: 50%;
  font-style: normal;
}
.run-list i.success {
  background: #dcfae6;
  color: #067647;
}
.run-list i.error {
  background: #fee4e2;
  color: #b42318;
}
.run-list article > div {
  display: grid;
  gap: 4px;
}
.run-list strong {
  font-size: 10px;
}
.run-list span,
.run-list p {
  margin: 0;
  color: #71809a;
  font-size: 8px;
  line-height: 14px;
}
.run-list article > em {
  padding: 2px 6px;
  border-radius: 99px;
  background: #dcfae6;
  color: #067647;
  font-size: 8px;
  font-style: normal;
}
.run-list article > em.error-text {
  background: #fee4e2;
  color: #b42318;
}
@keyframes pulse {
  50% {
    box-shadow: 0 0 0 4px rgba(46, 144, 250, 0.14);
  }
}
@media (max-width: 1200px) {
  .designer-shell {
    grid-template-columns: 200px minmax(420px, 1fr) 250px;
  }
  .pipeline-node {
    width: 220px;
  }
}
</style>
