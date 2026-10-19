# Louvain 孤立社区不输出：根因定位与修复验证物料（2026-10-19）

图算法引擎验收 Louvain 未过项的完整复核物料。结论、根因、修复补丁、三臂对照实验的原始产物全部在本目录，可独立重审。

## 1. 结论摘要

| 项 | 内容 |
|---|---|
| 现象 | 小型连通分量（星型）的顶点在 Louvain 结果中整段缺失（该分量输出 0 行） |
| 根因 | 上游 nebula-algorithm **v3.1.0** `LouvainAlgo.scala` step2 用 `Graph.fromEdges(edges, None)` 重建压缩图，只物化「仍有社区间边」的顶点；step1 即完全内部化的社区没有任何社区间边 → 其超级点不进压缩图 → 全部成员从最终结果消失。与 Louvain 阈值/迭代参数无关 |
| 修复 | 给每个超级点补一条 **0 权自环** 并入 fromEdges（28 行补丁，见 `LouvainAlgo-step2-selfloop.patch`） |
| 验证 | 三臂对照：部署 JAR 与未打补丁重建 JAR 结果**逐字节一致**且恰好缺失 9 个星型顶点；打补丁 JAR 输出全量 33 点，24 个共有顶点社区划分与部署版**零差异**，三颗星各自成社区 |
| 状态 | 补丁未上线（替换 runner JAR + 重启属生产动作，待另行批准）；上游是否接受此补丁方向待定 |

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
- 加权图未测：样例 `hasWeight=false`；0 权自环论证按代码路径推演，未在加权样例实测；
- 补丁未与上游社区对齐（是否/如何回馈上游待定）；
- 上线动作（替换 runner JAR + 重启）待另行批准，本分支纯验证物料，不含部署变更。

## 10. 脱敏声明

本目录所有脚本与配置副本中，API key、数据库密码、内网 IP 已分别替换为 `<REDACTED-API-KEY>` / `<REDACTED>` / `<RUNNER-HOST>`，不影响语义复现（替换处均为环境相关值，非算法参数）。三个 JAR 本体过大不入库，仅附 sha256 清单。
