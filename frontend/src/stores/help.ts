import { defineStore } from 'pinia'
import { api, type HelpTopic, type UiPrefs } from '@/api/client'

// Beginner-facing explanations, shared by the Web UI, the Mini App and the Setup
// Wizard. The catalog is fetched once and cached; the "show explanations"
// preference controls whether <InfoHint> actually renders (on by default).
export const useHelpStore = defineStore('help', {
  state: () => ({
    topics: {} as Record<string, HelpTopic>,
    loaded: false,
    showExplanations: true,
  }),
  getters: {
    topic(state) {
      return (key: string): HelpTopic | undefined => state.topics[key]
    },
  },
  actions: {
    async load() {
      if (this.loaded) return
      try {
        const [topics, prefs] = await Promise.all([api.helpTopics(), api.helpPrefs()])
        const map: Record<string, HelpTopic> = {}
        for (const t of topics) map[t.key] = t
        this.topics = map
        this.showExplanations = prefs.show_explanations
        this.loaded = true
      } catch {
        // Explanations are a nicety; never block the app if they fail.
        this.loaded = true
      }
    },
    async setShowExplanations(value: boolean) {
      this.showExplanations = value
      try {
        const prefs: UiPrefs = await api.updateHelpPrefs({ show_explanations: value })
        this.showExplanations = prefs.show_explanations
      } catch {
        // Keep the optimistic value; the UI still respects the toggle.
      }
    },
  },
})
