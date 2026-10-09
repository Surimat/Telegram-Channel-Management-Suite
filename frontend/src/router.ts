import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
  { path: '/reactions', name: 'reactions', component: () => import('@/views/ReactionsView.vue') },
  { path: '/ai', name: 'ai', component: () => import('@/views/AiView.vue') },
  { path: '/ai-gateway', name: 'ai-gateway', component: () => import('@/views/AiGatewayView.vue') },
  { path: '/analytics', name: 'analytics', component: () => import('@/views/AnalyticsView.vue') },
  { path: '/bots', name: 'bots', component: () => import('@/views/BotsView.vue') },
  { path: '/bot-factory', name: 'bot-factory', component: () => import('@/views/BotFactoryView.vue') },
  { path: '/bot-onboarding', name: 'bot-onboarding', component: () => import('@/views/BotOnboardingView.vue') },
  { path: '/channels', name: 'channels', component: () => import('@/views/ChannelsView.vue') },
  { path: '/sessions', name: 'sessions', component: () => import('@/views/SessionsView.vue') },
  { path: '/sources', name: 'sources', component: () => import('@/views/SourcesView.vue') },
  { path: '/content', name: 'content', component: () => import('@/views/ContentStudioView.vue') },
  { path: '/audience', name: 'audience', component: () => import('@/views/AudienceView.vue') },
  { path: '/invites', name: 'invites', component: () => import('@/views/InvitesView.vue') },
  { path: '/campaigns', name: 'campaigns', component: () => import('@/views/CampaignsView.vue') },
  { path: '/mesh', name: 'mesh', component: () => import('@/views/MeshView.vue') },
  { path: '/editorial', name: 'editorial', component: () => import('@/views/EditorialView.vue') },
  { path: '/notifications', name: 'notifications', component: () => import('@/views/NotificationsView.vue') },
  { path: '/system', name: 'system', component: () => import('@/views/SystemView.vue') },
  { path: '/diagnostics', name: 'diagnostics', component: () => import('@/views/DiagnosticsView.vue') },
  { path: '/backup', name: 'backup', component: () => import('@/views/BackupView.vue') },
  { path: '/settings', name: 'settings', component: () => import('@/views/SettingsView.vue') },
  { path: '/owner', name: 'owner', component: () => import('@/views/OwnerView.vue') },
  { path: '/logs', name: 'logs', component: () => import('@/views/LogsView.vue') },
  { path: '/queue', name: 'queue', component: () => import('@/views/QueueView.vue') },
  { path: '/:pathMatch(.*)*', name: 'notfound', component: () => import('@/views/NotFoundView.vue') },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
