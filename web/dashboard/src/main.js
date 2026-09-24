import {createApp} from 'vue'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import Tooltip from 'primevue/tooltip'
import Aura from '@primeuix/themes/aura'
import {definePreset} from '@primeuix/themes'
import 'primeicons/primeicons.css'

import App from './App.vue'
import router from './router.js'
import {initTheme} from './theme.js'
import './style.css'

const Preset = definePreset(Aura, {
    semantic: {
        primary: {
            50: '{emerald.50}', 100: '{emerald.100}', 200: '{emerald.200}', 300: '{emerald.300}',
            400: '{emerald.400}', 500: '{emerald.500}', 600: '{emerald.600}', 700: '{emerald.700}',
            800: '{emerald.800}', 900: '{emerald.900}', 950: '{emerald.950}',
        },
    },
})

initTheme()

createApp(App)
    .use(router)
    .use(PrimeVue, {theme: {preset: Preset, options: {darkModeSelector: '.app-dark'}}})
    .use(ToastService)
    .use(ConfirmationService)
    .directive('tooltip', Tooltip)
    .mount('#app')
