import { createRouter, createWebHistory } from 'vue-router'

import ExpertDirectRelationPage from '../pages/kg-construction/ExpertDirectRelationPage.vue'
import ExpertEnterpriseRelationPage from '../pages/kg-construction/ExpertEnterpriseRelationPage.vue'
import ExpertPaperCooperationPage from '../pages/kg-construction/ExpertPaperCooperationPage.vue'
import ScaffoldModulePage from '../pages/kg-construction/scaffold/ScaffoldModulePage.vue'
import { KG_MODULES } from '../config/kg-modules'

const scaffoldRoutes = KG_MODULES.filter((item) => item.mode === 'scaffold').map((item) => ({
  path: item.path,
  name: item.routeName,
  component: ScaffoldModulePage,
  props: { moduleCode: item.code },
}))

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/kg/expert-paper-cooperation' },
    {
      path: '/kg/expert-direct-relation',
      name: 'ExpertDirectRelation',
      component: ExpertDirectRelationPage,
    },
    {
      path: '/kg/expert-paper-cooperation',
      name: 'ExpertPaperCooperation',
      component: ExpertPaperCooperationPage,
    },
    {
      path: '/kg/expert-enterprise-relation',
      name: 'ExpertEnterpriseRelation',
      component: ExpertEnterpriseRelationPage,
    },
    ...scaffoldRoutes,
    { path: '/:pathMatch(.*)*', redirect: '/kg/expert-paper-cooperation' },
  ],
})
