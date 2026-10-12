import './styles/fonts.css'
import './styles/tokens.css'
import './styles/base.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'

import App from './App.vue'
import { logger } from './lib/logger'
import router from './router'
import { errorMessage, errorStack, logUnhandledRejections, pageCrashed } from './system/crash'
import { themeOptions } from './theme/preset'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(PrimeVue, { theme: themeOptions })

// the last net: an error outside the routed page (the frame itself, the login page), which the
// boundary inside the shell never sees
app.config.errorHandler = (err, _instance, info) => {
  logger.error('app error', {
    route: router.currentRoute.value.path,
    message: errorMessage(err),
    info,
    stack: errorStack(err),
  })
}
logUnhandledRejections(window, () => router.currentRoute.value.path)
// a page whose file fails to load (a deploy swapped the files under an open tab, or the network
// dropped): the navigation is cancelled, so without this the click does nothing
router.onError((err, to) => {
  logger.error('page failed to load', { route: to.path, message: errorMessage(err), stack: errorStack(err) })
  pageCrashed.value = true
})

app.mount('#app')
