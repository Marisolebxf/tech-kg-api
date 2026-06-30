import { createRouter, createWebHistory } from 'vue-router'

import EnterpriseRelationView from '../views/enterprise-relation/EnterpriseRelationView.vue'
import ExpertDirectRelationView from '../views/expert-direct/ExpertDirectRelationView.vue'
import ExpertColleagueView from '../views/expert-colleague/ExpertColleagueView.vue'
import ExpertPaperCooperationView from '../views/expert-paper-cooperation/ExpertPaperCooperationView.vue'
import ReasoningPlaceholderView from '../views/reasoning-placeholder/ReasoningPlaceholderView.vue'

const placeholderRoutes = [
  {
    path: '/expert-direct',
    name: 'expert-direct',
    title: '科技专家直接关系',
    endpoint: '/api/v1/kg-construction/expert-direct-relations/query',
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
      path: '/enterprise-relation',
      name: 'enterprise-relation',
      component: EnterpriseRelationView,
      meta: {
        title: '重点科技企业关系',
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
    {
      path: '/expert-direct',
      name: 'expert-direct',
      component: ExpertDirectRelationView,
      meta: {
        title: '科技专家直接关系',
        featureName: '科技专家直接关系推理构建',
        endpoint: '/api/v1/kg-construction/expert-direct-relations/query',
      },
    },
    ...placeholderRoutes.filter((route) => route.name !== 'expert-direct').map((route) => ({
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
