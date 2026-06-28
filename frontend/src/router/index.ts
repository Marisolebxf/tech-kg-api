import { createRouter, createWebHistory } from 'vue-router'

import ExpertColleagueView from '../views/expert-colleague/ExpertColleagueView.vue'
import ExpertPaperCooperationView from '../views/expert-paper-cooperation/ExpertPaperCooperationView.vue'
import ReasoningPlaceholderView from '../views/reasoning-placeholder/ReasoningPlaceholderView.vue'

const placeholderRoutes = [
  {
    path: '/expert-direct',
    name: 'expert-direct',
    title: '科技专家直接关系',
    endpoint: '/api/v1/expert/direct/relation/infer',
  },
  {
    path: '/node-indirect',
    name: 'node-indirect',
    title: '科技节点间接关系',
    endpoint: '/api/v1/node/indirect/relation/infer',
  },
  {
    path: '/two-point-achievement',
    name: 'two-point-achievement',
    title: '科技两点合作成果',
    endpoint: '/api/v1/achievement/two-point/infer',
  },
  {
    path: '/expert-alumni',
    name: 'expert-alumni',
    title: '科技专家校友关系',
    endpoint: '/api/v1/expert/alumni/relation/infer',
  },
  {
    path: '/enterprise-relation',
    name: 'enterprise-relation',
    title: '重点科技企业关系',
    endpoint: '/api/v1/enterprise/relation/infer',
  },
  {
    path: '/industry-chain-event',
    name: 'industry-chain-event',
    title: '产业链点事件关系',
    endpoint: '/api/v1/industry-chain/event/relation/infer',
  },
  {
    path: '/industry-chain-panorama',
    name: 'industry-chain-panorama',
    title: '科技产业链全景图',
    endpoint: '/api/v1/industry-chain/panorama/infer',
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/expert-colleague',
    },
    {
      path: '/expert-colleague',
      name: 'expert-colleague',
      component: ExpertColleagueView,
      meta: {
        title: '科技专家同事关系',
      },
    },
    {
      path: '/paper-cooperation',
      name: 'paper-cooperation',
      component: ExpertPaperCooperationView,
      meta: {
        title: '专家论文合作关系',
      },
    },
    ...placeholderRoutes.map((route) => ({
      path: route.path,
      name: route.name,
      component: ReasoningPlaceholderView,
      meta: {
        title: route.title,
        featureName: `${route.title}推理构建`,
        endpoint: route.endpoint,
      },
    })),
  ],
})
