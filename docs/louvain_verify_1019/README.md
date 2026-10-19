# Louvain 孤立社区不输出：根因定位与修复验证物料（2026-10-19）

图算法引擎验收 Louvain 未过项的完整复核物料。结论、根因、修复补丁、三臂对照实验的原始产物全部在本目录，可独立重审。

## 1. 结论摘要

| 项 | 内容 |
|---|---|
| 现象 | 小型连通分量（星型）的顶点在 Louvain 结果中整段缺失（该分量输出 0 行） |
| 根因 | 上游 nebula-algorithm **v3.1.0** `LouvainAlgo.scala` step2 用 `Graph.fromEdges(edges, None)` 重建压缩图，只物化「仍有社区间边」的顶点；step1 即完全内部化的社区没有任何社区间边 → 其超级点不进压缩图 → 全部成员从最终结果消失。与 Louvain 阈值/迭代参数无关 |
| 修复 | 给每个超级点补一条 **0 权自环** 并入 fromEdges（28 行补丁，见 `LouvainAlgo-step2-selfloop.patch`） |
| 验证 | 三臂对照：部署 JAR 与未打补丁重建 JAR 结果**逐字节一致**且恰好缺失 9 个星型顶点；打补丁 JAR 输出全量 33 点，24 个共有顶点社区划分与部署版**零差异**，三颗星各自成社区 |
| 状态 | 三臂对照 + Round 2 发布前补齐（默认参数/非负加权/单关系复刻/空输入，见 §11）均完成；补丁未上线（替换 runner JAR 属生产动作，待另行批准）；上游是否接受此补丁方向待定 |

## 2. 触发条件

step1 一轮就把某个连通分量完全合并为单一社区（该分量与图其余部分无边、分量内部再无跨社区边）→ 压缩图重建时该分量无任何边可挂 → 整分量不输出。典型即小星型分量。大分量因阈值不满足合并不受影响（样例中的 K8 对照组即为此设计）。

## 3. 根因代码位置

上游 `nebula-algorithm/src/main/scala/com/vesoft/nebula/algorithm/lib/LouvainAlgo.scala` 约 :187-190（每轮压缩后）：

```scala
// reconstruct graph based on new edge info
val initG = Graph.fromEdges(edges, None)   // edges 只含社区间边
```

`Graph.fromEdges` 只为「触及一条边」的顶点建 VertexId，孤立超级点（无任何社区间边）不存在于 initG，其成员随后从 louvain 结果整体消失。

## 4. 补丁与 0 权自环安全性论证

补丁全文见 `LouvainAlgo-step2-selfloop.patch`，打补丁后的完整源文件副本在 `src/com/vesoft/nebula/algorithm/lib/LouvainAlgo.scala`（与上游 v3.1.0 其余部分逐字节一致，仅此 hunk 有改动）。核心：

```scala
val selfLoops = superVertexInfo.map(x => Edge(x._1, x._1, 0.0))
val initG     = Graph.fromEdges(edges.union(selfLoops), None)
```

0 权自环不改变任何簿记（论据写在补丁注释中，请对照源码复核）：

- `createLouvainGraph`：自环对超点度的贡献为 0.0；
- `getNeighCommInfo`：自环对 `k_i,n` 的贡献为 0.0；
- 下一轮 step2：自环被滤入 `v2vKin` 时 weight*2 = 0，与 `k_i,n` 无双重计入；
- 附带保证每个顶点都有 triplet，`getChangeInfo` 的 inner join 对孤立超点保持完整。

## 5. 三臂对照实验

隔离空间 `graphalgo_lv_1019`（样例 v2，33 点 51 边，见 §6）。作业参数：`maxIter=20, internalIter=10, tol=0.5, encodeId=true, labels=[link], hasWeight=false, partitionNum=1`（完整参数见各臂 `application.conf`）。

| 臂 | JAR | sha256[:16] | 结果行数 | 说明 |
|---|---|---|---|---|
| A | 部署版（runner 在用） | `c98f4f57d3376b73` | **24** | 缺 9 个星型顶点 |
| B | 上游 v3.1.0 源码未打补丁重建 | `20c554b97156b06f` | **24** | 结果 CSV 与 A **逐字节一致** |
| C | 同源码打本补丁重建 | `4b45ba6f23593544` | **33** | 全量输出 |

关键事实（可从 `jobs/*/result_merged.csv` 直接复核）：

1. `cmp` A vs B 结果 CSV：**完全一致** → 部署 JAR 行为 = 上游 v3.1.0 源码行为，排除本地构建污染/版本漂移。B 的 JAR 字节 sha 与 A 不同系构建时间戳等元数据，行为等价以结果 CSV 为准。
2. A/B 缺失集合恰为三颗星全部 9 点：`{st1c, st1l1, st1l2, st2c, st2l1, st2l2, st2l3, st3c, st3l1}`；C 有 A 无 = 该 9 点，A 有 C 无 = 0。
3. 24 个共有顶点的社区归属 A vs C **差异数 = 0** → 补丁对非触发拓扑零扰动。
4. C 的社区分布：a 环 8 点 → 社区 `a5`；b 环 8 点 → `b6`；K8 全 singleton（`c1`..`c8` 各自）；三颗星 3/4/2 点各自成社区（`st1l1`/`st2l2`/`st3l1`）。

## 6. 样例设计（fixture v2）

`load_fixture2.py` 重建隔离空间 `graphalgo_lv_1019`：33 顶点、51 边、4 组分量，各司其职：

| 分量 | 点数 | 角色 |
|---|---|---|
| 双 8 环 + 1 桥（a1..a8, b1..b8, a1–b1） | 16 | 驱动「压缩后再合并」的多级 Louvain 轮次 |
| K8 团（c1..c8） | 8 | 回归对照：内部增益低于阈值 → 全 singleton，不打补丁也应同样输出 |
| 三颗星 3/4/2（st1/st2/st3） | 9 | **bug 触发器**：完全内部化的孤立社区 |

`setup_space.sh` 为 v1 样例装载脚本（BTN 星型 + K8+K8+桥），已被 v2 取代，仅留档。终版空间以 v2 为准。

## 7. 目录清单

```
LouvainAlgo-step2-selfloop.patch   28 行补丁（target：LouvainAlgo.scala）
jars_sha256.txt                    三个 JAR 的完整 sha256（JAR 本体过大不入库，原物在服务器受限区）
src/.../LouvainAlgo.scala          打补丁后完整源文件副本
scripts/setup_space.sh             v1 样例装载（已废弃，留档）
scripts/load_fixture.py            v1 装载（已废弃，留档）
scripts/load_fixture2.py           终版样例装载（隔离空间 + 33 点 51 边 + 索引重建）
scripts/run_arm.sh                 向隔离 runner 提交 louvain 作业并取结果
jobs/<arm>/application.conf        各臂作业完整参数（runner 生成）
jobs/<arm>/result_merged.csv       各臂结果（result/part-*.csv 合并，单一表头）
jobs/<arm>/spark_tail.log          各臂 spark 日志尾部 120 行
jobs/rows-*.csv                    runner 行转储摘要（按 jobId）
round2/                            发布前补齐（§11）：默认参数/加权/单关系/空输入 8 作业 + 驱动与装载脚本
```

jobId ↔ 臂映射：

| jobId | 臂 |
|---|---|
| `a6b3191ec6ca41db9f68cd2f7f33fe86` | **armA-deployed-jar-v2 = A 终值**（部署版在样例 v2 就绪后的正式跑） |
| `1efdf054f7bc4a5fac152071009786b5` | armA-deployed-jar 首跑：赶在样例 v2 装载完成前提交，跑在空间 v1 残留数据上（16 点、环未合并、K8 未在场），结果不作数，仅留档 |
| `c73a228172854b3eb61b93a803386fa8` | armB-rebuild-unpatched |
| `434b8de878b04d559824495da2712ee4` | armC-patched-jar |
| `9691b228e4b349a6af74eb33fa36c6dd` | 首次提交，无结果产出（runner 侧无 result 分片），仅存 conf 与日志尾部备查 |

## 8. 复现步骤

1. 取上游 nebula-algorithm v3.1.0 源码包并展开；
2. `patch -p1 < LouvainAlgo-step2-selfloop.patch`（或对照 `src/` 副本核对唯一改动）；
3. 构建：`mvn -pl nebula-algorithm -am package -DskipTests`，产物 `nebula-algorithm/target/nebula-algorithm-3.1.0.jar`；
4. `scripts/load_fixture2.py` 重建隔离空间（依赖图查询 API，见脚本头部）；
5. `scripts/run_arm.sh <标签>` 提交作业，比对 `jobs/<arm>/result_merged.csv`。

**诚实声明**：步骤 3 的 mvn 命令为重建路径参考——原始构建命令行未留存。Maven 构建不具备字节级可复现性（时间戳等元数据），复核锚点不是「重建出相同 sha256 的 JAR」，而是「未打补丁重建臂 B 与部署臂 A 的结果 CSV 逐字节一致」这一行为等价证据。

## 9. 边界与未证事项

- 33 点样例证明机制与本修复在该样例成立，**不构成 Louvain 一般正确性证明**；
- 未执行上游官方测试套（构建产出含 tests.jar，未跑）；
- 加权图：**非负权重已实测**（Round 2，§11.3——wlink 全正权，补丁版全量输出且共有顶点划分与部署版零差异）；**负权/零总权未测**（Louvain 模块度语义本身假定非负权）；
- 多分区（partitionNum>1）未测：全部作业 partitionNum=1；Spark 多分区下的数据交换路径未覆盖；
- 平台真实数据单关系场景（gkx_lite BTN/PL/AB）的引擎级复测在 Round 2 以隔离复刻空间完成（§11.4）；平台页面级复测须待受控上线后在真实 runner 上进行，本轮未动线上 JAR；
- 补丁未与上游社区对齐（是否/如何回馈上游待定）；
- 上线动作（替换 runner JAR + 重启）待另行批准，本分支纯验证物料，不含部署变更。

## 10. 脱敏声明

本目录所有脚本与配置副本中，API key、数据库密码、内网 IP 已分别替换为 `<REDACTED-API-KEY>` / `<REDACTED>` / `<RUNNER-HOST>`，不影响语义复现（替换处均为环境相关值，非算法参数）。三个 JAR 本体过大不入库，仅附 sha256 清单。

## 11. Round 2：发布前补齐（2026-10-19，回应复核意见）

隔离 runner 上补测四类场景。**每臂 JAR 绑定方式与运行时环境见 §11.5**；全部作业 `partitionNum=1`、`encodeId=true`，参数除注明外均为平台前端目录默认值 `maxIter=8, internalIter=5, tol=0.5`（graph-algorithm-catalog.ts）。

### 11.1 平台默认参数回归（样例 v2，无权 link）

| 臂 | JAR | 行数 | 结果 |
|---|---|---|---|
| A-default | 部署版 c98f4f57 | 24 | 环 8+8（a5/b6）、K8 全 singleton、**9 星型缺失**（与 20/10 参数下的 A 完全同构） |
| C-default | 补丁版 4b45ba6f | **33** | 全量；三颗星 3/4/2 各自成社区 |

**共有 24 顶点社区归属 A vs C 差异数 = 0**（`round2/jobs/*/result_merged.csv` 可 join 复算）→ 平台默认参数下修复有效、大分量回归零差异。

### 11.2 非负加权对照（wlink，全正权：环/桥=2、K8=1、星=1）

| 臂 | 行数 | 结果 |
|---|---|---|
| A-weighted | 24 | 9 星型缺失；环分裂为 3+5/4+4（权重改变模块度，属预期算法行为） |
| C-weighted | **33** | 全量；星 3/4/2 各自成社区 |

共有 24 顶点归属差异数 = 0 → **非负权入口下补丁同样有效且零扰动**；负权/零总权未测（§9）。

### 11.3 单关系场景隔离复刻（graphalgo_lv_sr_1019）

平台「单关系选择」验收的隔离复刻：`link_ab`=双环+桥（16 点 17 边大分量）、`link_pl`=三颗星（9 点 6 边小分量）、`link_none`=零边。

| 臂 | 输出 | 说明 |
|---|---|---|
| PL-deployed | **4 行** | st2 组 4 点以 singleton 输出；st1(3)/st3(2) 组 5 点被丢 |
| PL-patched | **9 行** | st1/st3 各自成社区输出，st2 组 4 点仍 singleton（与部署版归属一致） |
| AB-patched | **16 行** | 大分量全量（环分裂 3+5/4+4，SR 空间边数少、增益尺度不同，属预期） |

**机制数据依赖性的直接观察**：部署版并非丢所有小分量——step1 内部化的（st1/st3）整组消失，未内部化的（st2）以 singleton 存活。补丁版两类都输出，共有 4 点（st2*）归属两版一致。原平台观察（BTN/PL 小分量 0 行）对应 st1/st3 型分量。

### 11.4 空输入边界

`link_none`（零边型，索引已建）+ 补丁版：作业 `succeeded` exit=0、结果仅 `_SUCCESS`+空 part 文件、0 行。空输入不报错、不产出顶点，如实记录。

### 11.5 每臂 JAR 绑定与运行时（复核要求补齐）

**JAR 换装流程**（runner 经 env `NEBULA_ALGORITHM_JAR` 固定指向容器内 `/opt/nebula-algorithm/nebula-algorithm-3.1.0.jar`，spark-submit 每次提交时读该路径，无需重启）：

```bash
# 换装（跑某臂前）
docker cp nebula-algorithm-3.1.0-<arm>.jar trsgraph-algorithm-runner:/opt/nebula-algorithm/nebula-algorithm-3.1.0.jar
docker exec trsgraph-algorithm-runner sha256sum /opt/nebula-algorithm/nebula-algorithm-3.1.0.jar
# 期望：A=c98f4f57…（完整值见 jars_sha256.txt）/ B=20c554b9… / C=4b45ba6f…
# 跑臂（round2/run_job.py：submit→poll→result）
python3 round2/run_job.py <tag> <space> <labels> 8 5 0.5 [--weighted w]
# 复位（每轮跑完必做）
docker cp nebula-algorithm-3.1.0-deployed.jar trsgraph-algorithm-runner:/opt/nebula-algorithm/nebula-algorithm-3.1.0.jar
docker exec trsgraph-algorithm-runner sha256sum /opt/nebula-algorithm/nebula-algorithm-3.1.0.jar  # 必须回到 c98f4f57…
```

**运行时事实**（runner 容器实测）：OpenJDK `1.8.0_432`（JDK8u432-b06）、Spark **2.4.8**（Hadoop 2.7.3，`local[8]`、driver-memory 8g、spark.ui 关闭）；spark-submit 调用形如 `spark-submit --master local[8] --driver-memory 8g --class com.vesoft.nebula.algorithm.Main $JAR <application.conf 路径>`；runner API 监听 `8091`（容器共享 trsgraph 网络命名空间，经其网内地址访问；旧材料中的 8095 为历史临时实例端口，现役 8091）。

**Round 2 jobId ↔ 臂映射**：

| jobId | 臂 |
|---|---|
| `ac0dc61ef1204e29a154d69941217856` | A-default（部署版·默认参数） |
| `3e8ad3b3b1fb47eca09ddd32a1e3b806` | A-weighted（部署版·加权） |
| `84f336a1fc434f6a99a5aef716c42efe` | PL-deployed（部署版·单关系小分量） |
| `cb59b581160e4a6c80695c7c1166b68a` | C-default（补丁版·默认参数） |
| `d60bfed6e44e40e0be211ccb5ce02e13` | C-weighted（补丁版·加权） |
| `677f53deca504199b0fe63db03f0d5f5` | PL-patched（补丁版·单关系小分量） |
| `0fd091ffe466457694b9d6a06792deae` | AB-patched（补丁版·单关系大分量） |
| `52301f3b3ece4da483013990c5131828` | NONE-patched（补丁版·空输入） |

Round 2 物料在 `round2/`：`run_job.py`（作业驱动）、`add_weighted_edges.py`（wlink 装载）、`load_sr_fixture.py`（SR 空间装载）、`jobs/<臂>/{application.conf, result_merged.csv, spark_tail.log, result_files.txt}`（conf 已脱敏，凭证占位）。
