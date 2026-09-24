import {createRouter, createWebHistory} from 'vue-router'

const routes = [
    {path: '/', redirect: '/overview'},
    {path: '/overview', name: 'overview', component: () => import('./views/OverviewView.vue'), meta: {title: 'Overview'}},
    {path: '/jobs', name: 'jobs', component: () => import('./views/JobsView.vue'), meta: {title: 'Scheduled jobs'}},
    {path: '/jobs/new', name: 'job-new', component: () => import('./views/JobEditView.vue'), meta: {title: 'New job'}},
    {path: '/jobs/:id/edit', name: 'job-edit', component: () => import('./views/JobEditView.vue'), props: true, meta: {title: 'Edit job'}},
    {path: '/logs', name: 'logs', component: () => import('./views/LogsView.vue'), meta: {title: 'Scheduler logs'}},
    {path: '/flags', name: 'flags', component: () => import('./views/FlagsView.vue'), meta: {title: 'Bot settings'}},
    {path: '/:pathMatch(.*)*', redirect: '/overview'},
]

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes,
})

router.afterEach((to) => {
    document.title = to.meta.title ? `${to.meta.title} · Bot Dashboard` : 'Bot Dashboard'
})

export default router
