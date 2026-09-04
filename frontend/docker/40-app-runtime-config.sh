#!/bin/sh
# 前端运行时配置注入（方案 B：构建一次、部署期注入）。
# 由 nginx 官方镜像 /docker-entrypoint.d/ 在 20-envsubst 渲染 nginx conf 之后执行：
#   1) 把构建期哨兵前缀 /__BASE__/（VITE_BASE=/__BASE__/）替换为真实部署前缀；
#   2) 从环境变量生成 runtime-config.js（index.html 在主 bundle 前加载）；
#   3) 根路径部署（APP_BASE 空）时修正渲染后的 conf：前缀 302 会自指成环、
#      空前缀 location 匹配器非法，改为直接服务 SPA。
set -eu

HTML_ROOT="${HTML_ROOT:-/usr/share/nginx/html}"
NGINX_CONF="${NGINX_CONF:-/etc/nginx/conf.d/default.conf}"

# ---- 归一化 APP_BASE：未设置/空 = 根路径；去尾斜杠（nginx location 语义） ----
BASE=$(printf '%s' "${APP_BASE:-}" | sed -e 's#/*$##')
case "$BASE" in
  ''|/) BASE='' ;;
  /*) ;;
 *) BASE="/$BASE" ;;
esac

# ---- 1) 哨兵替换：/__BASE__/ → ${BASE}/（含 index.html 与 dist/docs 产物） ----
# 第二遍裸哨兵【仅限 .html】：VitePress 会把 base 转成类名（如 ___BASE___docs_…，
# 无斜杠形态）。不能对 JS 做裸替换——会把业务代码里的哨兵字符串字面量
# （如 config.ts 的防泄漏守卫）一并改写。本地 dev / 显式传 VITE_BASE 构建的
# 镜像不含哨兵，空跑无害。
if [ -d "$HTML_ROOT" ]; then
  grep -rl -F '/__BASE__/' "$HTML_ROOT" 2>/dev/null | xargs -r sed -i "s#/__BASE__/#$BASE/#g"
  grep -rl -F '__BASE__' "$HTML_ROOT" --include='*.html' 2>/dev/null | xargs -r sed -i "s#__BASE__#$BASE#g"
fi

# ---- 2) 生成 runtime-config.js：空值输出空串，前端按未设置回落构建期值 ----
API_BASE=$(printf '%s' "${APP_API_BASE:-}" | sed -e 's#/*$##')
[ -n "$API_BASE" ] || API_BASE="$BASE/api"

jstr() { printf '"%s"' "$(printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')"; }

cat > "$HTML_ROOT/runtime-config.js" <<EOF
// 由容器启动脚本生成（docker/40-app-runtime-config.sh），勿手动编辑
window.__RUNTIME_CONFIG__ = {
  base: $(jstr "$BASE/"),
  apiBase: $(jstr "$API_BASE"),
  graphSpace: $(jstr "${TRS_GRAPH_SPACE:-}"),
  authEnabled: $(jstr "${AUTH_ENABLED:-}"),
  portalEmbeddedDefault: $(jstr "${PORTAL_EMBEDDED_DEFAULT:-}"),
  portalAllowedOrigins: $(jstr "${PORTAL_ALLOWED_ORIGINS:-}"),
  portalTargetOrigin: $(jstr "${PORTAL_TARGET_ORIGIN:-}"),
  portalSource: $(jstr "${PORTAL_SOURCE:-}"),
  adminExampleFallback: $(jstr "${ADMIN_EXAMPLE_FALLBACK:-}")
}
EOF

# ---- 3) 根路径部署：修正 envsubst 渲染产物 ----
# 空前缀下模板退化为：302 自指（死循环）、空匹配器 location（语法错误）、
# 与独立 /api/ 块重复的前缀 api 块。按块过滤：/ 由前缀 location ^~ / 兜底
# 直接服务 SPA，无需跳转；重复 api 块（带 rewrite 的那个）删除。
if [ -z "$BASE" ] && [ -f "$NGINX_CONF" ]; then
  awk '
    /^  location = \/ \{$/ || /^  location =  \{$/ || /^  location \^~ \/api\/ \{$/ {
      inblock = 1; buf = $0 "\n"
      drop = ($0 ~ /^  location = \/ \{$/ || $0 ~ /^  location =  \{$/)
      apiblock = ($0 ~ /\^~ \/api\//)
      next
    }
    inblock && /rewrite \^\/api\// { if (apiblock) drop = 1 }
    inblock && /^  \}$/ {
      buf = buf $0 "\n"
      if (!drop) printf "%s", buf
      inblock = 0; buf = ""
      next
    }
    inblock { buf = buf $0 "\n"; next }
    { print }
  ' "$NGINX_CONF" > "$NGINX_CONF.tmp" && mv "$NGINX_CONF.tmp" "$NGINX_CONF"
fi
