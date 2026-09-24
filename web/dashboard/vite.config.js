import {defineConfig, loadEnv} from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import {PrimeVueResolver} from '@primevue/auto-import-resolver'

// The dashboard is served under /dashboard/ (nginx strips the prefix; the Python server accepts both).
export default defineConfig(({mode}) => {
    const env = loadEnv(mode, process.cwd(), '')
    const apiTarget = env.DASHBOARD_API || 'http://localhost:8501'
    return {
        base: '/dashboard/',
        plugins: [
            vue(),
            Components({resolvers: [PrimeVueResolver()], dts: false}),
        ],
        server: {
            port: 5173,
            proxy: {
                '/dashboard/api': {target: apiTarget, changeOrigin: true},
            },
        },
    }
})
